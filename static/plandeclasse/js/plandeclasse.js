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
import {onCanvasClick, resetPlanKeepRoom, toggleSelectedSeatBan, unassignSelected} from "./interactions.js";
import {applySchema, reconcileAfterSchemaChange, resetRoomSchema} from "./schema.js";
import {setupExportUI, startExport} from "./export.js";
import {setupSolveUI, syncSolveButtonEnabled, startSolve} from "./solver.js";
import {setupUnifiedImport} from "./importers.js";


/**
 * Réinitialise le plan de classe SANS toucher à la salle :
 * - supprime toutes les affectations (placements + index inverse),
 * - nettoie la sélection,
 * - met l'UI à jour.
 */
function resetPlanOnly() {
    state.placements.clear();
    state.placedByStudent.clear();
    state.selection.studentId = null;
    state.selection.seatKey = null;

    renderRoom();
    renderStudents();
    renderConstraints();
    updateBanButtonLabel();
    // Si les badges/tooltip de "générer" dépendent de l'état : on resynchronise
    syncSolveButtonEnabled();
}


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

    $("#btnAddRow")?.addEventListener("click", () => {
        const capsStr = (/** @type {HTMLInputElement} */($("#rowCapacities"))).value;
        const caps = capsStr.split(/[,\s]+/)
            .map(s => Number(s.trim()))
            .filter(n => Number.isFinite(n) && n !== 0);
        if (caps.length === 0) return;

        // Nombre de rangées identiques à ajouter (défaut 1)
        const nInput = /** @type {HTMLInputElement|null} */ ($("#rowsCount"));
        const n = Math.max(1, Number(nInput?.value ?? 1) || 1);

        // Empile n fois sans toucher aux rangées existantes
        for (let k = 0; k < n; k++) {
            state.schema.push(caps.slice());
        }

        // Recalage (placements/interdits/contraintes) sans reconstruire le schéma
        reconcileAfterSchemaChange();
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

    (/** @type {HTMLInputElement} */($("#optLockPlacements")))
        ?.addEventListener("change", (e) => (state.options.lock_placements = e.target.checked));
    state.options.lock_placements = !!document.getElementById("optLockPlacements")?.checked;

    document.getElementById("btnCancelConstraint")?.addEventListener("click", cancelConstraintForm);
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

    const btnResetPlan = document.getElementById("btnResetPlan");
    if (btnResetPlan && !btnResetPlan.dataset.wired) {
        btnResetPlan.dataset.wired = "1";
        btnResetPlan.addEventListener("click", (ev) => {
            ev.preventDefault();
            resetPlanKeepRoom();
        });
    }

    // Réinitialiser la **salle** (schéma)
    const btnResetRoomSchema = document.getElementById("btnResetRoomSchema");
    if (btnResetRoomSchema && !btnResetRoomSchema.dataset.wired) {
        btnResetRoomSchema.dataset.wired = "1";
        btnResetRoomSchema.addEventListener("click", (ev) => {
            ev.preventDefault();
            resetRoomSchema();
            // Après une salle vide, le bouton "générer" ne doit pas permettre un solve
            syncSolveButtonEnabled();
        });
    }

    const optMix = /** @type {HTMLInputElement|null} */ (document.getElementById("optMixage"));
    const optSolo = /** @type {HTMLInputElement|null} */ (document.getElementById("optSolo"));
    if (optMix) state.options.prefer_mixage = !!optMix.checked;
    if (optSolo) state.options.prefer_alone = !!optSolo.checked;
}

window.addEventListener("DOMContentLoaded", init);
