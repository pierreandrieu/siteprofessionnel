// static/plandeclasse/js/ui-steps.js
// UI des étapes : nom du fichier, badges "OK/à faire", auto pour étapes 3 & 4
(function () {
    "use strict";

    /** -----------------------------------------------------------------------
     *  Helpers d’accès DOM (retourne null si absent)
     *  --------------------------------------------------------------------- */
    const $id = (id) => /** @type {HTMLElement|null} */ (document.getElementById(id));

    /** -----------------------------------------------------------------------
     *  Références DOM (toutes optionnelles : le script reste tolérant)
     *  --------------------------------------------------------------------- */
    const inputCSV = /** @type {HTMLInputElement|null} */ ($id("csvInput"));
    const nomFichier = $id("csvFilename");
    const btnRazSalle = $id("btnClearRoom");

    const badgeEtape1 = $id("step1Status");
    const badgeEtape2 = $id("step2Status");
    const badgeEtape3 = $id("step3Status");
    const badgeEtape4 = $id("step4Status");

    const listePlaces = $id("studentsPlaced");
    const listeContraintes = $id("constraintsList");

    const canvas = /** @type {HTMLElement|null} */ ($id("roomCanvas"));

    /** -----------------------------------------------------------------------
     *  Badges : "OK" / "facultatif" / "à faire"
     *  --------------------------------------------------------------------- */
    /**
     * Met à jour un badge d’étape.
     * @param {HTMLElement|null} el - le badge (peut être null si absent dans le template)
     * @param {true|"opt"|false} etat
     */
    function setBadge(el, etat) {
        if (!el) return;
        el.classList.remove("text-bg-secondary", "text-bg-success");
        let texte = "à faire";
        if (etat === true) {
            el.classList.add("text-bg-success");
            texte = "OK";
        } else if (etat === "opt") {
            el.classList.add("text-bg-secondary");
            texte = "facultatif";
        } else {
            el.classList.add("text-bg-secondary");
            texte = "à faire";
        }
        el.textContent = texte;
        el.setAttribute("aria-label", `état : ${texte}`);
    }

    /** -----------------------------------------------------------------------
     *  Étape 1 : fichier chargé
     *  --------------------------------------------------------------------- */
    if (inputCSV) {
        inputCSV.addEventListener("change", () => {
            const f = inputCSV.files && inputCSV.files[0];
            if (nomFichier) nomFichier.textContent = f ? f.name : "Aucun fichier";
            setBadge(badgeEtape1, !!f);
        });
    }

    /** -----------------------------------------------------------------------
     *  Étape 2 : au moins une table rendue dans le SVG (#roomCanvas)
     *  - On observe les mutations du SVG et on recalcule l’état.
     *  - Petit throttle via rAF : si ça bouge beaucoup, on ne calcule qu’une fois
     *    par trame.
     *  --------------------------------------------------------------------- */
    let rafToken = 0;

    function computeSallePrete() {
        // Re-requête volontaire : si le canvas a été recréé, on récupère le bon nœud
        const c = /** @type {HTMLElement|null} */ ($id("roomCanvas"));
        const aDesTables = !!c && !!c.querySelector(".table-rect");
        setBadge(badgeEtape2, aDesTables ? true : false);
    }

    function planifierComputeSallePrete() {
        if (rafToken) return;
        rafToken = requestAnimationFrame(() => {
            rafToken = 0;
            computeSallePrete();
        });
    }

    if (canvas) {
        const obsSalle = new MutationObserver(planifierComputeSallePrete);
        obsSalle.observe(canvas, {childList: true, subtree: true});
        // État initial
        computeSallePrete();

        // Si le canvas disparaît du DOM, on coupe l’observer proprement
        const obsPresence = new MutationObserver(() => {
            const encoreLa = document.body.contains(canvas);
            if (!encoreLa) obsSalle.disconnect();
        });
        obsPresence.observe(document.body, {childList: true, subtree: true});
    }

    // RAZ salle : remet l’étape 3 en "facultatif" et recalcule l’étape 2
    if (btnRazSalle) {
        btnRazSalle.addEventListener("click", () => {
            setBadge(badgeEtape3, "opt");
            // Laisse le temps au DOM de se mettre à jour
            setTimeout(computeSallePrete, 0);
        });
    }

    /** -----------------------------------------------------------------------
     *  Étape 3 : au moins un élève est "placé"
     *  --------------------------------------------------------------------- */
    if (listePlaces && badgeEtape3) {
        const computePlaces = () => {
            const nb = (listePlaces.children && listePlaces.children.length) || 0;
            setBadge(badgeEtape3, nb > 0 ? true : "opt");
        };
        computePlaces();
        new MutationObserver(computePlaces).observe(listePlaces, {childList: true, subtree: false});
    }

    /** -----------------------------------------------------------------------
     *  Étape 4 : au moins une contrainte
     *  --------------------------------------------------------------------- */
    if (listeContraintes && badgeEtape4) {
        const computeContraintes = () => {
            const nb = (listeContraintes.children && listeContraintes.children.length) || 0;
            setBadge(badgeEtape4, nb > 0 ? true : "opt");
        };
        computeContraintes();
        new MutationObserver(computeContraintes).observe(listeContraintes, {childList: true, subtree: false});
    }

    /** -----------------------------------------------------------------------
     *  Valeurs initiales (avant tout événement utilisateur)
     *  --------------------------------------------------------------------- */
    setBadge(badgeEtape1, false);
    setBadge(badgeEtape2, false);
    setBadge(badgeEtape3, "opt");
    setBadge(badgeEtape4, "opt");
})();
