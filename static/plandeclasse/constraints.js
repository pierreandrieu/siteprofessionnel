// static/plandeclasse/js/constraints.js
"use strict";

/**
 * Module Constraints : formulaires, puces lisibles, suppression, sélecteurs.
 */

import {state} from "./state.js";
import {$, computeMaxManhattan, keyOf} from "./utils.js";
import {renderRoom, renderStudents, updateBanButtonLabel} from "./render.js";

export function refreshConstraintSelectors() {
    const a = /** @type {HTMLSelectElement|null} */ ($("#cstStudentA"));
    const b = /** @type {HTMLSelectElement|null} */ ($("#cstStudentB"));
    if (!a || !b) return;
    const fill = (sel) => {
        sel.innerHTML = "";
        for (const st of state.students.slice().sort((x, y) => (x.first + x.last).localeCompare(y.first + y.last))) {
            const opt = document.createElement("option");
            opt.value = String(st.id);
            opt.textContent = `${st.first} ${st.last}`.trim();
            sel.appendChild(opt);
        }
    };
    fill(a);
    fill(b);
}

export function onConstraintTypeChange() {
    const t = /** @type {HTMLSelectElement} */ ($("#constraintType")).value;
    const bWrap = $("#cstStudentBWrap");
    const pWrap = $("#cstParamWrap");
    const pLabel = $("#cstParamLabel");
    const pHelp = $("#cstParamHelp");
    const pInput = /** @type {HTMLInputElement} */ ($("#cstParam"));

    const needsB = ["same_table", "far_apart"].includes(t);
    const needsK = ["front_rows", "back_rows"].includes(t);
    const needsD = t === "far_apart";

    bWrap.hidden = !needsB;
    pWrap.hidden = !(needsK || needsD);

    if (needsK) {
        pLabel.textContent = "k (nombre de rangées)";
        pInput.value = "1";
        pInput.min = "1";
        pHelp.textContent = "";
    } else if (needsD) {
        const maxD = computeMaxManhattan(state.schema);
        pLabel.textContent = "distance d (Manhattan)";
        pInput.value = "2";
        pInput.min = "2";
        pInput.max = String(Math.max(2, maxD));
        pHelp.textContent = maxD > 0 ? `valeur ≤ ${maxD} selon la salle` : "";
    } else {
        pLabel.textContent = "paramètre";
        pInput.placeholder = "";
        pHelp.textContent = "";
    }
}

export function addConstraint() {
    const t = /** @type {HTMLSelectElement} */ ($("#constraintType")).value;
    const a = Number(/** @type {HTMLSelectElement} */ ($("#cstStudentA")).value);
    const bSel = /** @type {HTMLSelectElement} */ ($("#cstStudentB"));
    const b = bSel && !$("#cstStudentBWrap").hidden ? Number(bSel.value) : null;
    const pInput = /** @type {HTMLInputElement} */ ($("#cstParam"));
    const pVal = pInput.value ? Number(pInput.value) : null;

    const nameOf = (sid) => {
        const s = state.students.find((x) => x.id === sid);
        return s ? `${s.first} ${s.last}`.trim() : `#${sid}`;
    };

    let human = "";
    const payload = /** @type {any} */ ({type: t});

    if (t === "front_rows") {
        payload.a = a;
        payload.k = pVal;
        human = `${nameOf(a)} doit être dans les premières rangées (k=${pVal ?? "?"})`;
    } else if (t === "back_rows") {
        payload.a = a;
        payload.k = pVal;
        human = `${nameOf(a)} doit être dans les dernières rangées (k=${pVal ?? "?"})`;
    } else if (t === "solo_table") {
        payload.a = a;
        human = `${nameOf(a)} ne doit pas avoir de voisins (seul à la table)`;
    } else if (t === "empty_neighbor") {
        payload.a = a;
        human = `${nameOf(a)} ne doit pas avoir de voisins (au moins un siège vide à côté)`;
    } else if (t === "same_table") {
        payload.a = a;
        payload.b = b;
        human = `${nameOf(a)} doit être à la même table que ${nameOf(b)}`;
    } else if (t === "far_apart") {
        const maxD = computeMaxManhattan(state.schema);
        const d = Math.min(Math.max(1, pVal || 1), Math.max(1, maxD));
        payload.a = a;
        payload.b = b;
        payload.d = d;
        human = `${nameOf(a)} être éloigné d’une distance d’au moins d=${d} de ${nameOf(b)}`;
    }

    payload.human = human;
    state.constraints.push(payload);
    renderConstraints();
}

/** Réinitialise le formulaire d’ajout de contrainte. */
export function cancelConstraintForm() {
    /** @type {HTMLSelectElement} */ ($("#cstStudentA")).selectedIndex = 0;
    /** @type {HTMLSelectElement} */ ($("#cstStudentB")).selectedIndex = 0;
    /** @type {HTMLSelectElement} */ ($("#constraintType")).selectedIndex = 0;
    /** @type {HTMLInputElement} */ ($("#cstParam")).value = "";
    onConstraintTypeChange();
}

/** Affiche la liste des contraintes + suppression. */
export function renderConstraints() {
    const root = /** @type {HTMLElement|null} */ ($("#constraintsList"));
    if (!root) return;
    root.innerHTML = "";
    for (const c of state.constraints) {
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
