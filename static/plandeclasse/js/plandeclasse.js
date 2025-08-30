// static/plandeclasse/js/index.js
"use strict";

/**
 * Point d’entrée : branche les listeners et effectue les premiers rendus.
 * Ce fichier est le seul référencé dans le template (type="module").
 */

import {state} from "./state.js";
import {$, splitName} from "./utils.js";
import {parseCSV} from "./csv.js";
import {renderRoom, renderStudents, updateBanButtonLabel} from "./render.js";
import {
    refreshConstraintSelectors,
    onConstraintTypeChange,
    addConstraint,
    cancelConstraintForm,
    renderConstraints
} from "./constraints.js";
import {seatClick, onCanvasClick, toggleSelectedSeatBan, unassignSelected} from "./interactions.js";
import {applySchema} from "./schema.js";
import {startSolve} from "./solver.js";

function init() {
    // Solve
    document.getElementById("btnSolve")?.addEventListener("click", startSolve);

    // Colonne élèves (toggle)
    document.getElementById("toggleStudentsPanel")?.addEventListener("click", () => {
        // On applique la classe sur #pc-root pour que le CSS puisse masquer la carte complète
        document.getElementById("pc-root")?.classList.toggle("students-hidden");
        // Recalcule le SVG après changement de layout
        renderRoom();
    });

    // Canvas SVG (délégué)
    const canvas = document.getElementById("roomCanvas");
    if (canvas) canvas.addEventListener("click", onCanvasClick);

    // CSV
    const csvInput = /** @type {HTMLInputElement|null} */ ($("#csvInput"));
    if (csvInput) {
        csvInput.addEventListener("change", async (ev) => {
            const f = /** @type {HTMLInputElement} */(ev.target).files?.[0];
            if (!f) return;
            const txt = await f.text();
            const rows = parseCSV(txt);
            state.students = rows.map((r, idx) => {
                const {first, last} = splitName(r.name);
                return {id: idx, name: r.name, gender: r.gender || null, first, last};
            });
            state.selection.studentId = null;
            state.selection.seatKey = null;
            refreshConstraintSelectors();
            renderStudents();
            renderRoom();
            updateBanButtonLabel();
        });
    }

    // Schéma
    $("#btnBuildRoom")?.addEventListener("click", () => {
        const rows = Number((/** @type {HTMLInputElement} */($("#rowsCount"))).value);
        const tpr = Number((/** @type {HTMLInputElement} */($("#tablesPerRow"))).value);
        const caps = (/** @type {HTMLInputElement} */($("#rowCapacities"))).value;
        if (!Number.isFinite(rows) || rows < 1) return;
        if (!Number.isFinite(tpr) || tpr < 1) return;
        applySchema(rows, tpr, caps);
    });

    $("#btnClearRoom")?.addEventListener("click", () => {
        state.schema = [];
        state.forbidden.clear();
        state.placements.clear();
        state.placedByStudent.clear();
        state.selection.studentId = null;
        state.selection.seatKey = null;
        renderRoom();
        renderStudents();
        renderConstraints();
        updateBanButtonLabel();
    });

    // Options solveur
    (/** @type {HTMLInputElement} */($("#optMixage")))?.addEventListener("change", (e) => (state.options.prefer_mixage = e.target.checked));
    (/** @type {HTMLInputElement} */($("#optSolo")))?.addEventListener("change", (e) => (state.options.prefer_alone = e.target.checked));

    // Affichage des noms
    (/** @type {HTMLInputElement} */($("#nvPrenom")))?.addEventListener("change", () => {
        state.nameView = "first";
        renderRoom();
    });
    (/** @type {HTMLInputElement} */($("#nvNom")))?.addEventListener("change", () => {
        state.nameView = "last";
        renderRoom();
    });
    (/** @type {HTMLInputElement} */($("#nvPrenomNom")))?.addEventListener("change", () => {
        state.nameView = "both";
        renderRoom();
    });

    // Actions siège
    $("#btnToggleBan")?.addEventListener("click", toggleSelectedSeatBan);
    $("#btnUnassign")?.addEventListener("click", unassignSelected);

    // Recherche élève
    $("#studentSearch")?.addEventListener("input", renderStudents);

    // Formulaire contraintes
    $("#constraintType")?.addEventListener("change", onConstraintTypeChange);
    $("#btnAddConstraint")?.addEventListener("click", addConstraint);
    $("#btnCancelConstraint")?.addEventListener("click", cancelConstraintForm);

    // Rendus initiaux
    renderRoom();
    renderStudents();
    refreshConstraintSelectors();
    onConstraintTypeChange();
    updateBanButtonLabel();
}

window.addEventListener("DOMContentLoaded", init);
