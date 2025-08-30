// static/plandeclasse/js/index.js
"use strict";

/**
 * Point d’entrée : branche les listeners et effectue les premiers rendus.
 * Ce fichier est le seul référencé dans le template (type="module").
 */

import {state} from "./state.js";
import {$} from "./utils.js";
import {renderRoom, renderStudents, updateBanButtonLabel} from "./render.js";
import {
    refreshConstraintSelectors,
    onConstraintTypeChange,
    addConstraint,
    cancelConstraintForm,
    renderConstraints
} from "./constraints.js";
import {onCanvasClick, toggleSelectedSeatBan, unassignSelected} from "./interactions.js";
import {applySchema} from "./schema.js";
import {setupExportUI, startExport} from "./export.js";
import {setupSolveUI, syncSolveButtonEnabled, startSolve} from "./solver.js";
import {setupUnifiedImport} from "./importers.js";

function init() {
    // Solve
    const btnSolve = document.getElementById("btnSolve");
    btnSolve?.addEventListener("click", startSolve);

    // Colonne élèves (toggle)
    document.getElementById("toggleStudentsPanel")?.addEventListener("click", () => {
        document.getElementById("pc-root")?.classList.toggle("students-hidden");
        renderRoom(); // recalcule le viewport après changement de layout
    });

    // Canvas SVG (délégué)
    const canvas = document.getElementById("roomCanvas");
    if (canvas) canvas.addEventListener("click", onCanvasClick);

    // >>> Import unifié (CSV ou JSON)
    setupUnifiedImport();

    // Schéma (on a supprimé l’ancien champ "tables par rangée", appliSchema(rows, capacities))
    $("#btnBuildRoom")?.addEventListener("click", () => {
        const rows = Number((/** @type {HTMLInputElement} */($("#rowsCount"))).value);
        const caps = (/** @type {HTMLInputElement} */($("#rowCapacities"))).value;
        if (!Number.isFinite(rows) || rows < 1) return;
        applySchema(rows, caps);
        syncSolveButtonEnabled();
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
        syncSolveButtonEnabled();
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

    // Export
    document.getElementById("btnExport")?.addEventListener("click", startExport);
    setupExportUI();

    // Solve UI helpers (enable/tooltip)
    setupSolveUI();
    syncSolveButtonEnabled();

    // Rendus initiaux
    renderRoom();
    renderStudents();
    refreshConstraintSelectors();
    onConstraintTypeChange();
    updateBanButtonLabel();

    // Bootstrap tooltips
    document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => {
        // @ts-ignore: bootstrap global
        new bootstrap.Tooltip(el);
    });
}

window.addEventListener("DOMContentLoaded", init);
