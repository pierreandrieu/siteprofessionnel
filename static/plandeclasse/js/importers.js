// static/plandeclasse/js/importers.js
"use strict";

/**
 * Import unifié : CSV Pronote OU JSON d’export maison.
 * ---------------------------------------------------
 * Rôles :
 *  - Réinitialiser proprement l’état selon la source (CSV/JSON),
 *  - Remplir `state.*` (élèves, schéma, placements, contraintes…),
 *  - Re-rendre l’interface et synchroniser les boutons/états dépendants.
 *
 * Sécurité/CSP :
 *  - Aucun style inline ni HTML injecté depuis les fichiers importés.
 *  - Les données utilisateurs sont traitées de manière défensive (trim/normalisation).
 */

import {state} from "./state.js";
import {$, splitName} from "./utils.js";
import {parseCSV} from "./csv.js";
import {renderRoom, renderStudents, updateBanButtonLabel} from "./render.js";
import {renderConstraints, refreshConstraintSelectors} from "./constraints.js";
import {syncSolveButtonEnabled} from "./solver.js";
import {syncExportButtonEnabled} from "./export.js";
import {renderRowsEditor, reconcileAfterSchemaChange} from "./schema.js";

/* ==========================================================================
   Réinitialisation propre de l’état
   ========================================================================== */

/**
 * Remet à zéro salle, placements, contraintes et sélection,
 * tout en conservant `state.options` et `state.nameView`.
 */
function hardResetButKeepOptions() {
    state.schema = [];
    state.forbidden.clear();
    state.placements.clear();
    state.placedByStudent.clear();
    state.selection.studentId = null;
    state.selection.seatKey = null;
    state.constraints = [];
    // on garde state.options et state.nameView
}

/**
 * Conserve la salle + sièges interdits, mais remet à zéro :
 *  - les affectations (plan),
 *  - la sélection,
 *  - les contraintes élève/élève (on ne garde que `forbid_seat`).
 * Puis recalcule proprement les `forbid_seat` à partir de `state.forbidden`.
 */
function resetForNewStudentsKeepRoom() {
    // placements & sélection
    state.placements.clear();
    state.placedByStudent.clear();
    state.selection.studentId = null;
    state.selection.seatKey = null;

    // garde uniquement les contraintes structurelles de siège ET les exact_seat
    state.constraints = state.constraints.filter((c) => c.type === "forbid_seat" || c.type === "exact_seat");

    // recalcule les forbid_seat depuis `state.forbidden` + schéma
    reconcileAfterSchemaChange();
}

/* ==========================================================================
   Rafraîchissement UI
   ========================================================================== */

/** Post-apply : re-rendu UI + synchronisation des actions/boutons. */
function refreshAllUI() {
    // Radios d’affichage des noms (si nameView a changé)
    const prenom = /** @type {HTMLInputElement|null} */ ($("#nvPrenom"));
    const nom = /** @type {HTMLInputElement|null} */ ($("#nvNom"));
    const both = /** @type {HTMLInputElement|null} */ ($("#nvPrenomNom"));
    if (prenom && nom && both) {
        prenom.checked = state.nameView === "first";
        nom.checked = state.nameView === "last";
        both.checked = state.nameView === "both";
    }

    refreshConstraintSelectors();
    renderConstraints();
    renderStudents();
    renderRoom();
    updateBanButtonLabel();
    syncSolveButtonEnabled();
    renderRowsEditor();
}

/* ==========================================================================
   Import CSV
   ========================================================================== */

/**
 * Importe un CSV Pronote (ou compatible).
 * @param {string} csvText - contenu brut du fichier CSV
 */
function importFromCSV(csvText) {
    // Retire un éventuel BOM et normalise les fins de ligne (robustesse)
    const clean = String(csvText || "").replace(/^\uFEFF/, "");

    const rows = parseCSV(clean);
    resetForNewStudentsKeepRoom();

    // Réinitialise le nom de classe saisi dans l’UI
    const classInput = /** @type {HTMLInputElement|null} */ ($("#className"));
    if (classInput) classInput.value = "";
    // Synchronise l’état du bouton d’export (nom requis)
    syncExportButtonEnabled();

    // Construit la liste d’élèves (id séquentiel stable)
    state.students = rows.map((r, idx) => {
        const {first, last} = splitName(r.name);
        return {id: idx, name: r.name, gender: r.gender ?? null, first, last};
    });

    refreshAllUI();
}

/* ==========================================================================
   Import JSON d’export
   ========================================================================== */

/**
 * Valide la structure minimale d’un JSON d’export maison.
 * @param {any} data
 * @returns {boolean} ok
 */
function validateExportJSON(data) {
    if (!data || typeof data !== "object") return false;

    // Notre export contient "format": "plandeclasse-export" (tolérant si absent)
    if (data.format && data.format !== "plandeclasse-export") return false;

    // Champs minimaux attendus
    if (!Array.isArray(data.schema)) return false;
    if (!Array.isArray(data.students)) return false;

    return true;
}

/**
 * Importe un JSON d’export produit par l’outil.
 * @param {any} data
 */
function importFromExportJSON(data) {
    if (!validateExportJSON(data)) {
        alert("Fichier JSON non reconnu (pas un export de cet outil).");
        return;
    }

    // Reset (sauf options)
    hardResetButKeepOptions();

    // Nom de classe (UI)
    const classInput = /** @type {HTMLInputElement|null} */ ($("#className"));
    if (classInput) classInput.value = String(data.class_name || "").trim();
    syncExportButtonEnabled();

    // Mode d’affichage des noms
    if (data.name_view === "first" || data.name_view === "last" || data.name_view === "both") {
        state.nameView = data.name_view;
    }

    // Schéma (copie par valeur)
    state.schema = Array.isArray(data.schema) ? data.schema.map((row) => row.slice()) : [];

    // Élèves (tolérant : si pas de first/last, on split depuis name)
    state.students = (data.students || []).map((s, i) => {
        const id = Number.isFinite(s.id) ? Number(s.id) : i;
        const name = String(s.name || "").trim();

        let first = String(s.first || "");
        let last = String(s.last || "");
        if (!first && !last && name) {
            const parts = splitName(name);
            first = parts.first;
            last = parts.last;
        }

        const gender = s.gender === "F" || s.gender === "M" ? s.gender : null;
        return {id, name, first, last, gender};
    });

    // Contraintes (copie par valeur) — on ignore les marqueurs UI-only (_objective_)
    const rawConstraints = Array.isArray(data.constraints) ? data.constraints.slice() : [];
    state.constraints = rawConstraints.filter((c) => c?.type !== "_objective_");
    // Sièges interdits
    state.forbidden = new Set(Array.isArray(data.forbidden) ? data.forbidden : []);

    // Placements (deux index cohérents)
    state.placements.clear();
    state.placedByStudent.clear();
    const placementsObj = data.placements || {};
    for (const [seatKey, sid] of Object.entries(placementsObj)) {
        const numId = Number(sid);
        if (Number.isFinite(numId)) {
            state.placements.set(seatKey, numId);
            state.placedByStudent.set(numId, seatKey);
        }
    }

    refreshAllUI();
}

/* ==========================================================================
   Détection & wiring
   ========================================================================== */

/**
 * Détecte l’extension probable d’un fichier.
 * @param {File} f
 * @returns {"csv"|"json"|"unknown"}
 */
function guessFileKind(f) {
    const name = (f.name || "").toLowerCase();
    if (name.endsWith(".csv")) return "csv";
    if (name.endsWith(".json")) return "json";

    // MIME peut aider, mais certains navigateurs renvoient "application/octet-stream"
    const type = (f.type || "").toLowerCase();
    if (type.includes("json")) return "json";
    if (type.includes("csv") || type.includes("comma-separated")) return "csv";

    return "unknown";
}

/**
 * Branche un seul <input type="file"> pour accepter .csv et .json
 * et router automatiquement vers l’importeur adapté.
 */
export function setupUnifiedImport() {
    const input = /** @type {HTMLInputElement|null} */ ($("#csvInput"));
    if (!input) return;

    input.addEventListener("change", async () => {
        const file = input.files && input.files[0];
        if (!file) return;

        try {
            const kind = guessFileKind(file);
            const text = await file.text();

            if (kind === "csv") {
                importFromCSV(text);
                return;
            }

            // JSON explicite ou inconnu -> tentative JSON, sinon fallback CSV
            try {
                const data = JSON.parse(text);
                importFromExportJSON(data);
            } catch (_e) {
                importFromCSV(text);
            }
        } catch (err) {
            console.error(err);
            alert("Impossible de lire ce fichier. Vérifiez le format (CSV ou JSON).");
        } finally {
            // Permet de sélectionner à nouveau le même fichier si nécessaire.
            // (Décommente si tu préfères ce comportement)
            // input.value = "";
        }
    });
}
