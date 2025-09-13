// static/plandeclasse/js/index.js
"use strict";

/**
 * @file Point d’entrée de l’application "plan de classe".
 * Branche les écouteurs d’événements et déclenche les premiers rendus.
 * Ce module est le SEUL chargé dans le template (type="module").
 *
 */

import {state as etat} from "plandeclasse/state";
import {$} from "plandeclasse/utils";

// Rendus & UI
import {
    renderRoom as rendreSalle,
    renderStudents as rendreEleves,
    updateBanButtonLabel as majBoutonBan,
} from "plandeclasse/render";

// Contraintes
import {
    refreshConstraintSelectors as rafraichirSelecteursContraintes,
    onConstraintTypeChange as surChangementTypeContrainte,
    addConstraint as ajouterContrainte,
    cancelConstraintForm as annulerFormContrainte,
    renderConstraints as rendreContraintes,
} from "plandeclasse/constraints";

// Interactions (clics, bannissement, désaffectation)
import {
    onCanvasClick as surClicCanvas,
    resetPlanKeepRoom as reinitialiserPlanSeulement,
    toggleSelectedSeatBan as basculerSiegeInterdit,
    unassignSelected as desaffecterSelection,
} from "plandeclasse/interactions";

// Schéma de salle
import {
    applySchema as appliquerSchema,                // (importé si besoin ailleurs)
    reconcileAfterSchemaChange as recalerApresSchema,
    renderRowsEditor as rendreEditeurRangees,
    resetRoomSchema as reinitialiserSchemaSalle,
} from "plandeclasse/schema";

// Export
import {
    setupExportUI as preparerUIExport,
    startExport as demarrerExport,
} from "plandeclasse/export";

// Solveur
import {
    setupSolveUI as preparerUISolveur,
    syncSolveButtonEnabled as syncBoutonSolve,
    startSolve as demarrerSolve,
} from "plandeclasse/solver";

// Import CSV/JSON unifié
import {setupUnifiedImport as preparerImportUnifie} from "plandeclasse/importers";

/**
 * Réinitialise le plan de classe SANS toucher au schéma de salle.
 * - Supprime toutes les affectations (seatKey -> studentId) et l’index inverse.
 * - Efface la sélection courante (élève/siège).
 * - Rafraîchit l’UI et l’état des boutons dépendants.
 *
 * Utile si l’on veut repartir d’un plan vierge en gardant la salle telle quelle.
 */
function reinitialiserPlanInterne() {
    etat.placements.clear();
    etat.placedByStudent.clear();
    etat.selection.studentId = null;
    etat.selection.seatKey = null;

    rendreSalle();
    rendreEleves();
    rendreContraintes();
    majBoutonBan();
    // Si des tooltips / badges dépendent de l’état, on resynchronise.
    syncBoutonSolve();
}

/**
 * Initialise l’application :
 * - Branche tous les écouteurs,
 * - Prépare les UIs auxiliaires (export, solveur, import),
 * - Lance les rendus initiaux.
 */
function initialiser() {
    // --- Solveur : démarrage du calcul
    const boutonSolve = document.getElementById("btnSolve");
    boutonSolve?.addEventListener("click", demarrerSolve);

    // --- Ouverture/fermeture de la colonne Élèves
    document.getElementById("toggleStudentsPanel")?.addEventListener("click", () => {
        document.getElementById("pc-root")?.classList.toggle("students-hidden");
        // Le viewport dépend de la largeur dispo : on rerend la salle.
        rendreSalle();
    });

    // --- Canvas SVG (délégation de clic vers gestionnaire)
    const canvas = document.getElementById("roomCanvas");
    if (canvas) canvas.addEventListener("click", surClicCanvas);

    // --- Import unifié (CSV Pronote / JSON d’export)
    preparerImportUnifie();

    // --- Ajout de rangées (éditeur rapide)
    $("#btnAddRow")?.addEventListener("click", (ev) => {
        ev.preventDefault();

        const saisieCapacites = /** @type {HTMLInputElement} */ ($("#rowCapacities"));
        const texteCaps = saisieCapacites?.value ?? "";
        const capacites = texteCaps
            .split(/[,\s]+/)
            .map((s) => Number(s.trim()))
            .filter((n) => Number.isFinite(n) && n !== 0);

        if (capacites.length === 0) return;

        const champNb = /** @type {HTMLInputElement|null} */ ($("#rowsCount"));
        const nb = Math.max(1, Number(champNb?.value ?? 1) || 1);

        for (let k = 0; k < nb; k++) etat.schema.push(capacites.slice());

        recalerApresSchema();
        syncBoutonSolve();
    });

    // --- Nettoyage total de la salle (schéma + états dépendants)
    $("#btnClearRoom")?.addEventListener("click", () => {
        etat.schema = [];
        etat.forbidden.clear();
        etat.placements.clear();
        etat.placedByStudent.clear();
        etat.selection.studentId = null;
        etat.selection.seatKey = null;

        rendreSalle();
        rendreEleves();
        rendreContraintes();
        majBoutonBan();
        syncBoutonSolve();
        rendreEditeurRangees();
    });

    // --- Options de solveur
    (/** @type {HTMLInputElement} */ ($("#optMixage")))?.addEventListener(
        "change",
        (e) => (etat.options.prefer_mixage = e.target.checked),
    );
    (/** @type {HTMLInputElement} */ ($("#optSolo")))?.addEventListener(
        "change",
        (e) => (etat.options.prefer_alone = e.target.checked),
    );

    // --- Affichage des noms (prénom / nom / les deux)
    (/** @type {HTMLInputElement} */ ($("#nvPrenom")))?.addEventListener("change", () => {
        etat.nameView = "first";
        rendreSalle();
    });
    (/** @type {HTMLInputElement} */ ($("#nvNom")))?.addEventListener("change", () => {
        etat.nameView = "last";
        rendreSalle();
    });
    (/** @type {HTMLInputElement} */ ($("#nvPrenomNom")))?.addEventListener("change", () => {
        etat.nameView = "both";
        rendreSalle();
    });

    // --- Actions liées au siège sélectionné
    $("#btnToggleBan")?.addEventListener("click", basculerSiegeInterdit);
    $("#btnUnassign")?.addEventListener("click", desaffecterSelection);

    // --- Recherche d’élèves
    $("#studentSearch")?.addEventListener("input", rendreEleves);

    // --- Formulaire de contraintes (type + ajout + reset)
    $("#constraintType")?.addEventListener("change", surChangementTypeContrainte);
    $("#btnAddConstraint")?.addEventListener("click", ajouterContrainte);
    document.getElementById("btnCancelConstraint")?.addEventListener("click", annulerFormContrainte);

    // Verrouillage des placements (option)
    (/** @type {HTMLInputElement} */ ($("#optLockPlacements")))
        ?.addEventListener("change", (e) => (etat.options.lock_placements = e.target.checked));
    etat.options.lock_placements = !!document.getElementById("optLockPlacements")?.checked;

    // --- Export
    document.getElementById("btnExport")?.addEventListener("click", demarrerExport);
    preparerUIExport();

    // --- Solveur : helpers (activation + tooltip)
    preparerUISolveur();
    syncBoutonSolve();

    // --- Rendus initiaux (salle + élèves + contraintes + éditeur de rangées)
    rendreSalle();
    rendreEleves();
    try {
        rafraichirSelecteursContraintes();
        surChangementTypeContrainte(); // sécurisé si un id manque
    } catch (e) {
        console.error("init constraints failed", e);
    }
    rendreEditeurRangees();

    // --- Tooltips Bootstrap (progressifs)
    document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach((el) => {
        // @ts-ignore bootstrap global
        new bootstrap.Tooltip(el);
    });

    // --- Bouton : réinitialiser uniquement le plan (garde le schéma)
    const boutonResetPlan = document.getElementById("btnResetPlan");
    if (boutonResetPlan && !boutonResetPlan.dataset.wired) {
        boutonResetPlan.dataset.wired = "1";
        boutonResetPlan.addEventListener("click", (ev) => {
            ev.preventDefault();
            reinitialiserPlanSeulement(); // garde la cohérence avec interactions.js
        });
    }

    // --- Bouton : réinitialiser le schéma de salle (vide la salle)
    const boutonResetSchema = document.getElementById("btnResetRoomSchema");
    if (boutonResetSchema && !boutonResetSchema.dataset.wired) {
        boutonResetSchema.dataset.wired = "1";
        boutonResetSchema.addEventListener("click", (ev) => {
            ev.preventDefault();
            reinitialiserSchemaSalle();
            // Après une salle vide, on ne doit plus pouvoir lancer un solve tant que non prête
            syncBoutonSolve();
            rendreEditeurRangees();
        });
    }

    // --- Bouton : vider toutes les contraintes (et synchroniser forbidden/placements liés)
    const btnClearCst = document.getElementById("btnClearConstraints");
    if (btnClearCst && !btnClearCst.dataset.wired) {
        btnClearCst.dataset.wired = "1";
        btnClearCst.addEventListener("click", (ev) => {
            ev.preventDefault();
            if (!confirm("Supprimer toutes les contraintes ?")) return;
            // Retire forbids du Set + désaffecte les élèves qui avaient un exact_seat
            for (const c of etat.constraints) {
                if (c.type === "forbid_seat") {
                    const k = `${c.x},${c.y},${c.s}`;
                    etat.forbidden.delete(k);
                }
                if (c.type === "exact_seat") {
                    const prev = etat.placedByStudent.get(c.a);
                    if (prev) {
                        etat.placedByStudent.delete(c.a);
                        etat.placements.delete(prev);
                    }
                }
            }
            etat.constraints = [];
            +rendreSalle();
            rendreEleves();
            rendreContraintes();
            majBoutonBan();
        });
    }

    // --- Synchronisation initiale des options mixage/solo (selon checkboxes)
    const optMix = /** @type {HTMLInputElement|null} */ (document.getElementById("optMixage"));
    const optSolo = /** @type {HTMLInputElement|null} */ (document.getElementById("optSolo"));
    if (optMix) etat.options.prefer_mixage = !!optMix.checked;
    if (optSolo) etat.options.prefer_alone = !!optSolo.checked;
}

// Démarrage une fois le DOM prêt
window.addEventListener("DOMContentLoaded", initialiser);

