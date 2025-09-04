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
    const sel = /** @type {HTMLSelectElement|null} */ ($("#cstStudents"));
    if (!sel) return;

    const previous = new Set(Array.from(sel.selectedOptions).map(o => o.value));
    const studentsSorted = getStudentsSorted();

    sel.innerHTML = "";
    for (const st of studentsSorted) {
        const opt = document.createElement("option");
        opt.value = String(st.id);
        opt.textContent = `${st.first} ${st.last}`.trim();
        if (previous.has(opt.value)) opt.selected = true;
        sel.appendChild(opt);
    }

    // Par défaut, si rien de sélectionné, on ne force pas : l’utilisateur choisira.
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

/* ==========================================================================
   Ajout de contrainte(s) à partir d’un groupe
   ========================================================================== */

/**
 * Ajoute un ou plusieurs éléments dans state.constraints selon :
 * - contrainte unaire : 1 entrée / élève sélectionné,
 * - contrainte binaire : 1 entrée / paire du groupe.
 *
 * Chaque entrée reçoit un 'batch_id' commun pour l’affichage groupé et la suppression.
 */
export function addConstraint() {
    const t = /** @type {HTMLSelectElement} */ ($("#constraintType")).value;
    const sel = /** @type {HTMLSelectElement} */ ($("#cstStudents"));
    const paramInput = /** @type {HTMLInputElement} */ ($("#cstParam"));

    if (!sel) return;

    // Récupère les ids sélectionnés (en nombres)
    const selectedIds = Array.from(sel.selectedOptions).map(o => Number(o.value)).filter(Number.isFinite);

    // Contrôle minimal
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

    // Paramètre éventuel (k ou d)
    const pValRaw = paramInput?.value ? Number(paramInput.value) : null;
    const maxD = computeMaxManhattan(state.schema);
    const d = (t === "far_apart")
        ? Math.min(Math.max(1, pValRaw || 1), Math.max(1, maxD))
        : null;

    const k = (t === "front_rows" || t === "back_rows")
        ? (pValRaw ?? null)
        : null;

    // Batch id + libellé pluriel pour la UI
    const batch_id = newBatchId();
    const namesPlural = formatNamesList(selectedIds);
    let batch_human = "";

    if (t === "front_rows") {
        batch_human = `${namesPlural} doivent être dans les premières rangées (k=${k ?? "?"})`;
    } else if (t === "back_rows") {
        batch_human = `${namesPlural} doivent être dans les dernières rangées (k=${k ?? "?"})`;
    } else if (t === "solo_table") {
        batch_human = `${namesPlural} doi(ven)t être isolé(s) sur une table`;
    } else if (t === "empty_neighbor") {
        batch_human = `${namesPlural} doi(ven)t avoir au moins un siège vide à côté`;
    } else if (t === "same_table") {
        batch_human = `${namesPlural} doivent être à la même table`;
    } else if (t === "far_apart") {
        batch_human = `${namesPlural} doivent être éloignés d’une distance d’au moins d=${d ?? "?"} entre eux`;
    }

    // Expansion : crée les contraintes réelles
    const payloads = [];

    if (isUnary) {
        for (const a of selectedIds) {
            const c = /** @type {any} */ ({type: t, a, batch_id});
            if (k != null) c.k = k;
            c.human = ""; // libellé géré par le lot
            payloads.push(c);
        }
    } else if (isBinary) {
        for (const [a, b] of pairs(selectedIds)) {
            const c = /** @type {any} */ ({type: t, a, b, batch_id});
            if (d != null) c.d = d;
            c.human = ""; // libellé géré par le lot
            payloads.push(c);
        }
    }

    // Ajout au state
    for (const p of payloads) state.constraints.push(p);

    // Enregistre un “marqueur” de lot via un élément synthétique (UI only)
    // Astuce : pas envoyé au backend (on filtre dans build payload côté solveur/export si besoin)
    state.constraints.push({
        type: "_batch_marker_",
        batch_id,
        human: batch_human,
        count: payloads.length,
    });

    // Refresh UI
    renderConstraints();
}

/** Réinitialise le formulaire. */
export function cancelConstraintForm() {
    /** @type {HTMLSelectElement} */ ($("#cstStudents")).selectedIndex = -1;
    /** @type {HTMLSelectElement} */ ($("#constraintType")).selectedIndex = 0;
    /** @type {HTMLInputElement} */ ($("#cstParam")).value = "";
    onConstraintTypeChange();
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