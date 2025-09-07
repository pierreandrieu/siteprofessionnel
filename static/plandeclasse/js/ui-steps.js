// UI des étapes : nom du fichier, badges "OK/à faire", auto pour étapes 3 & 4
(function () {
    const csvInput = document.getElementById('csvInput');
    const csvNameEl = document.getElementById('csvFilename');

    const btnClear = document.getElementById('btnClearRoom');

    const step1Badge = document.getElementById('step1Status');
    const step2Badge = document.getElementById('step2Status');
    const step3Badge = document.getElementById('step3Status');
    const step4Badge = document.getElementById('step4Status');

    const placedList = document.getElementById('studentsPlaced');
    const cstList = document.getElementById('constraintsList');

    function setBadge(el, state /* true|"opt"|false */) {
        if (!el) return;
        el.classList.remove('text-bg-secondary', 'text-bg-success');
        if (state === true) {
            el.classList.add('text-bg-success');
            el.textContent = 'OK';
        } else if (state === 'opt') {
            el.classList.add('text-bg-secondary');
            el.textContent = 'facultatif';
        } else {
            el.classList.add('text-bg-secondary');
            el.textContent = 'à faire';
        }
    }

    // Étape 1 : fichier
    if (csvInput) {
        csvInput.addEventListener('change', () => {
            const f = csvInput.files && csvInput.files[0];
            if (csvNameEl) csvNameEl.textContent = f ? f.name : 'Aucun fichier';
            setBadge(step1Badge, !!f);
        });
    }

    // Étape 2 : "OK" dès qu'il y a au moins une table rendue dans le canvas
    function computeRoomReady() {
        const canvas = document.getElementById('roomCanvas');
        const hasTables = !!canvas && !!canvas.querySelector('.table-rect');
        setBadge(step2Badge, hasTables ? true : false);
    }
        // Observe les changements du SVG (rendu/clear de la salle)
    const canvas = document.getElementById('roomCanvas');

    if (canvas) {
        const obs = new MutationObserver(() => computeRoomReady());
        obs.observe(canvas, {childList: true, subtree: true});
        computeRoomReady();
    }
    // Si on clique "réinitialiser la salle", force le recompute
    if (btnClear) btnClear.addEventListener('click', () => {
        setBadge(step3Badge, 'opt');
        setTimeout(computeRoomReady, 0);
    });

    // Étape 3 : passe en OK si au moins un élève est "placé"
    if (placedList && step3Badge) {
        const computePlaced = () => {
            const hasPlaced = placedList.children && placedList.children.length > 0;
            setBadge(step3Badge, hasPlaced ? true : 'opt');
        };
        // initial + observe
        computePlaced();
        new MutationObserver(computePlaced).observe(placedList, {childList: true, subtree: false});
    }

    // Étape 4 : passe en OK s’il y a au moins une contrainte
    if (cstList && step4Badge) {
        const computeConstraints = () => {
            const hasOne = cstList.children && cstList.children.length > 0;
            setBadge(step4Badge, hasOne ? true : 'opt');
        };
        computeConstraints();
        new MutationObserver(computeConstraints).observe(cstList, {childList: true, subtree: false});
    }

    // Valeurs initiales par défaut
    setBadge(step1Badge, false);
    setBadge(step2Badge, false);
    setBadge(step3Badge, 'opt');
    setBadge(step4Badge, 'opt');
})();
