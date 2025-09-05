"use strict";

/**
 * Module Constraints (version groupe) :
 * - Sélection multiple d’élèves (#cstStudents) pour créer des contraintes en lot.
 * - Contraintes unaires : appliquées à chaque élève sélectionné.
 * - Contraintes binaires : appliquées à chaque paire du groupe (combinaisons).
 * - Affichage groupé : une « pill » par lot avec libellé au pluriel.
 *   → suppression en un clic : retire toutes les contraintes du lot.
 *
 * Remarque : chaque contrainte réelle porte un 'batch_id' facultatif,
 * utilisé uniquement côté UI pour grouper/retirer. Côté solveur/export,
 * on envoie la liste “flattened” telle quelle (inchangé pour le backend).
 */
import {state} from "./state.js";
import {$, compareByLastThenFirst, computeMaxManhattan, keyOf} from "./utils.js";
import {renderRoom, renderStudents, updateBanButtonLabel} from "./render.js";


function getStudentsSorted() {
    return [...state.students].sort(compareByLastThenFirst);
}

/**
 * Retourne la sélection d'élèves en tenant compte du fallback mobile.
 * - Desktop (≥ sm) : lit le <select multiple>
 * - Mobile (< sm) : lit les <input type="checkbox"> générés dans #cstStudentsMobile
 */
function getSelectedStudentIds() {
    const isMobile = window.matchMedia("(max-width: 575.98px)").matches;
    if (isMobile) {
        const inputs = document.querySelectorAll("#cstStudentsMobile input[type=checkbox]:checked");
        return Array.from(inputs).map(i => Number(i.value));
    }
    const sel = /** @type {HTMLSelectElement|null} */ (document.getElementById("cstStudents"));
    if (!sel) return [];
    return Array.from(sel.selectedOptions).map(o => Number(o.value));
}

/** Réinitialise le formulaire de création de contraintes (desktop + mobile). */
export function cancelConstraintForm() {
    // Desktop: <select multiple>
    const sel = /** @type {HTMLSelectElement|null} */ (document.getElementById("cstStudents"));
    if (sel) sel.selectedIndex = -1;

    // Mobile: checkboxes
    const mob = /** @type {HTMLElement|null} */ (document.getElementById("cstStudentsMobile"));
    if (mob) {
        mob.querySelectorAll('input[type="checkbox"]').forEach((i) => {
            /** @type {HTMLInputElement} */ (i).checked = false;
        });
    }

    // Type de contrainte ↩︎ première option
    const typeSel = /** @type {HTMLSelectElement|null} */ (document.getElementById("constraintType"));
    if (typeSel) typeSel.selectedIndex = 0;

    // Paramètre (k/d) vidé puis UI remise à jour
    const p = /** @type {HTMLInputElement|null} */ (document.getElementById("cstParam"));
    if (p) p.value = "";

    // Recalcule “k / d / aide” selon le type par défaut
    onConstraintTypeChange();

    // Focus ergonomique
    (sel ?? typeSel)?.focus();
}


/** Formate une liste de noms "A, B et C". */
function formatNamesList(ids /**: number[] */) /**: string */ {
    const byId = new Map(state.students.map(s => [s.id, s]));
    const names = ids
        .map(id => byId.get(id))
        .filter(Boolean)
        .map(s => `${s.first} ${s.last}`.trim());

    if (names.length <= 1) return names[0] || "";
    const head = names.slice(0, -1).join(", ");
    return `${head} et ${names[names.length - 1]}`;
}

/** Produit les combinaisons non ordonnées de 2 éléments parmi un tableau d’ids. */
function pairs(ids /**: number[] */) /**: Array<[number,number]> */ {
    const out = [];
    for (let i = 0; i < ids.length; i++) {
        for (let j = i + 1; j < ids.length; j++) {
            out.push([ids[i], ids[j]]);
        }
    }
    return out;
}

/** Génère un identifiant de lot simple (unique assez pour l’UI). */
function newBatchId() {
    return "b" + Date.now().toString(36) + Math.floor(Math.random() * 1e6).toString(36);
}

export function refreshConstraintSelectors() {
    // Desktop select multiple
    const sel = /** @type {HTMLSelectElement|null} */ (document.getElementById("cstStudents"));
    // Mobile list-group with checkboxes
    const mob = /** @type {HTMLElement|null} */ (document.getElementById("cstStudentsMobile"));

    const studentsSorted = [...state.students].sort(compareByLastThenFirst);

    // Mémoriser la sélection courante (desktop ou mobile) pour la restaurer
    const previouslySelected = new Set(getSelectedStudentIds());

    // ---- Desktop : <select multiple>
    if (sel) {
        sel.innerHTML = "";
        for (const st of studentsSorted) {
            const opt = document.createElement("option");
            opt.value = String(st.id);
            opt.textContent = `${st.first} ${st.last}`.trim();
            if (previouslySelected.has(st.id)) opt.selected = true;
            sel.appendChild(opt);
        }
    }

    // ---- Mobile : cases à cocher
    if (mob) {
        mob.innerHTML = "";
        for (const st of studentsSorted) {
            const id = String(st.id);

            const wrap = document.createElement("label");
            wrap.className = "list-group-item d-flex align-items-center gap-2 py-2";

            const input = document.createElement("input");
            input.type = "checkbox";
            input.className = "form-check-input m-0";
            input.value = id;
            input.checked = previouslySelected.has(st.id);

            const txt = document.createElement("span");
            txt.className = "flex-grow-1";
            txt.textContent = `${st.first} ${st.last}`.trim();

            wrap.appendChild(input);
            wrap.appendChild(txt);
            mob.appendChild(wrap);
        }
    }
}


export function onConstraintTypeChange() {
    const t = /** @type {HTMLSelectElement} */ ($("#constraintType")).value;
    const pWrap = $("#cstParamWrap");
    const pLabel = $("#cstParamLabel");
    const pHelp = $("#cstParamHelp");
    const pInput = /** @type {HTMLInputElement} */ ($("#cstParam"));

    const needsK = ["front_rows", "back_rows"].includes(t);
    const needsD = t === "far_apart";

    pWrap.hidden = !(needsK || needsD);

    if (needsK) {
        pLabel.textContent = "k (nombre de rangées)";
        pInput.value = "1";
        pInput.min = "1";
        pInput.removeAttribute("max");
        pHelp.textContent = "";
    } else if (needsD) {
        const maxD = computeMaxManhattan(state.schema);
        pLabel.textContent = "distance d (Manhattan)";
        pInput.value = "2";
        pInput.min = "2";
        pInput.max = String(Math.max(2, maxD));
        pHelp.textContent = maxD > 0 ? `valeur ≤ ${maxD} pour cette salle` : "";
    } else {
        pLabel.textContent = "paramètre";
        pInput.placeholder = "";
        pHelp.textContent = "";
    }
}

/**
 * Ajoute un ou plusieurs éléments dans state.constraints à partir d’un GROUPE.
 *
 * - Contraintes unaires  : 1 entrée / élève sélectionné
 * - Contraintes binaires : 1 entrée / paire du groupe (C(n,2))
 *
 * Un "batch_id" commun est affecté à toutes les entrées générées.
 * On pousse aussi un "marqueur" _batch_marker_ (UI only) pour l’affichage/suppression groupés.
 */
export function addConstraint() {
    const t = /** @type {HTMLSelectElement} */ (document.getElementById("constraintType")).value;
    const selectedIds = getSelectedStudentIds();

    const isUnary = ["front_rows", "back_rows", "solo_table", "empty_neighbor"].includes(t);
    const isBinary = ["same_table", "far_apart"].includes(t);

    if (isUnary && selectedIds.length === 0) {
        alert("Sélectionnez au moins un élève pour cette contrainte.");
        return;
    }
    if (isBinary && selectedIds.length < 2) {
        alert("Sélectionnez au moins deux élèves pour cette contrainte.");
        return;
    }

    const pInput = /** @type {HTMLInputElement|null} */ (document.getElementById("cstParam"));
    const pValRaw = pInput?.value ? Number(pInput.value) : null;

    const maxD = computeMaxManhattan(state.schema);
    const d = (t === "far_apart") ? Math.min(Math.max(2, pValRaw || 2), Math.max(2, maxD)) : null; // min 2 cohérent avec le label
    const k = (t === "front_rows" || t === "back_rows") ? Math.max(1, pValRaw ?? 1) : null;

    const batch_id = newBatchId();
    const namesPlural = formatNamesList(selectedIds);
    let batch_human = "";
    switch (t) {
        case "front_rows":
            batch_human = `${namesPlural} doivent être dans les premières rangées (k=${k ?? "?"})`;
            break;
        case "back_rows":
            batch_human = `${namesPlural} doivent être dans les dernières rangées (k=${k ?? "?"})`;
            break;
        case "solo_table":
            batch_human = `${namesPlural} doivent être isolé·e·s sur une table`;
            break;
        case "empty_neighbor":
            batch_human = `${namesPlural} doivent avoir au moins un siège vide à côté`;
            break;
        case "same_table":
            batch_human = `${namesPlural} doivent être à la même table`;
            break;
        case "far_apart":
            batch_human = `${namesPlural} doivent être éloigné·e·s d’une distance d’au moins d=${d ?? "?"} entre eux/elles`;
            break;
    }

    const payloads = [];
    if (isUnary) {
        for (const a of selectedIds) {
            const c = /** @type {any} */ ({type: t, a, batch_id, human: ""});
            if (k != null) c.k = k;
            payloads.push(c);
        }
    } else {
        for (let i = 0; i < selectedIds.length; i++) {
            for (let j = i + 1; j < selectedIds.length; j++) {
                const a = selectedIds[i], b = selectedIds[j];
                const c = /** @type {any} */ ({type: t, a, b, batch_id, human: ""});
                if (d != null) c.d = d;
                payloads.push(c);
            }
        }
    }

    for (const p of payloads) state.constraints.push(p);
    state.constraints.push({type: "_batch_marker_", batch_id, human: batch_human, count: payloads.length});

    renderConstraints();
}


/* ==========================================================================
   Rendu + suppression (gère les lots)
   ========================================================================== */

/**
 * Affiche la liste des contraintes :
 * - Les éléments marqués "_batch_marker_" représentent un lot (affichage au pluriel).
 * - Le clic "✕" sur un lot supprime toutes les contraintes partageant batch_id + le marqueur.
 * - Les contraintes unitaires "forbid_seat" restent individuelles (inchangé).
 */
export function renderConstraints() {
    const root = /** @type {HTMLElement|null} */ ($("#constraintsList"));
    if (!root) return;
    root.innerHTML = "";

    // 1) Rendre d’abord les lots (marqueurs)
    const markers = state.constraints.filter(c => c.type === "_batch_marker_");
    for (const m of markers) {
        const item = document.createElement("div");
        item.className = "constraint-pill me-2 mb-2 d-inline-flex align-items-center gap-2";
        item.textContent = m.human || "(lot)";

        const del = document.createElement("button");
        del.className = "btn btn-sm btn-outline-danger";
        del.textContent = "✕";
        del.addEventListener("click", () => {
            // supprime toutes les contraintes du lot + le marqueur
            const bid = m.batch_id;
            state.constraints = state.constraints.filter(c => c.batch_id !== bid && c !== m);
            renderConstraints();
            updateBanButtonLabel();
            renderRoom(); // au cas où certaines contraintes influencent un futur rendu
        });

        item.appendChild(del);
        root.appendChild(item);
    }

    // 2) Afficher les contraintes “simples” (non lot, y compris forbid_seat)
    for (const c of state.constraints) {
        if (c.type === "_batch_marker_") continue; // déjà rendu
        if (c.batch_id) continue; // masqué car représenté par le marqueur

        const item = document.createElement("div");
        item.className = "constraint-pill me-2 mb-2 d-inline-flex align-items-center gap-2";
        item.textContent = c.human || JSON.stringify(c);

        const del = document.createElement("button");
        del.className = "btn btn-sm btn-outline-danger";
        del.textContent = "✕";
        del.addEventListener("click", () => {
            const idx = state.constraints.indexOf(c);
            if (idx >= 0) {
                if (c.type === "forbid_seat" && typeof c.x === "number") {
                    state.forbidden.delete(keyOf(c.x, c.y, c.s));
                    renderRoom();
                }
                state.constraints.splice(idx, 1);
                renderConstraints();
                updateBanButtonLabel();
            }
        });

        item.appendChild(del);
        root.appendChild(item);
    }
}