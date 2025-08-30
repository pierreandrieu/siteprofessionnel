// static/plandeclasse/js/importers.js
"use strict";

/**
 * Import unifié : CSV Pronote OU JSON d’export maison.
 * - Réinitialise proprement l’état,
 * - Remplit state.*,
 * - Re-rend l’interface et synchronise les boutons.
 */

import {state} from "./state.js";
import {$, splitName} from "./utils.js";   // <- parseCSV n'est pas ici
import {parseCSV} from "./csv.js";         // <- parseCSV est bien dans csv.js
import {renderRoom, renderStudents, updateBanButtonLabel} from "./render.js";
import {renderConstraints, refreshConstraintSelectors} from "./constraints.js";
import {syncSolveButtonEnabled} from "./solver.js";
import {syncExportButtonEnabled} from "./export.js";

/* =======================================================================
   Réinitialisation propre de l’état
   ======================================================================= */

/** Remet à zéro la salle, les placements, les contraintes et la sélection. */
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

/** Post-apply : re-rendu UI + synchronisation des actions. */
function refreshAllUI() {
    // Radios d’affichage des noms (si nameView a changé)
    const prenom = /** @type {HTMLInputElement|null} */ ($("#nvPrenom"));
    const nom = /** @type {HTMLInputElement|null} */ ($("#nvNom"));
    const both = /** @type {HTMLInputElement|null} */ ($("#nvPrenomNom"));
    if (prenom && nom && both) {
        prenom.checked = (state.nameView === "first");
        nom.checked = (state.nameView === "last");
        both.checked = (state.nameView === "both");
    }

    refreshConstraintSelectors();
    renderConstraints();
    renderStudents();
    renderRoom();
    updateBanButtonLabel();
    syncSolveButtonEnabled();
}

/* =======================================================================
   Import CSV
   ======================================================================= */

/**
 * Importe un CSV Pronote (ou compatible).
 * @param {string} csvText
 */
function importFromCSV(csvText) {
    const rows = parseCSV(csvText);
    hardResetButKeepOptions();

    const classInput = /** @type {HTMLInputElement|null} */ ($("#className"));
    if (classInput) classInput.value = "";  // on efface le nom
    syncExportButtonEnabled();              // ← NEW : refléter l’état côté bouton

    state.students = rows.map((r, idx) => {
        const {first, last} = splitName(r.name);
        return {id: idx, name: r.name, gender: r.gender ?? null, first, last};
    });

    refreshAllUI();
}

/* =======================================================================
   Import JSON d’export
   ======================================================================= */

/**
 * Valide et normalise un JSON d’export.
 * @param {any} data
 * @returns {boolean} ok
 */
function validateExportJSON(data) {
    if (!data || typeof data !== "object") return false;

    // Notre export contient "format": "plandeclasse-export"
    if (data.format && data.format !== "plandeclasse-export") return false;

    // Champs attendus (on reste tolérant)
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
    if (classInput) classInput.value = (data.class_name || "").trim();
    syncExportButtonEnabled();
    // Vue noms
    if (data.name_view === "first" || data.name_view === "last" || data.name_view === "both") {
        state.nameView = data.name_view;
    }

    // Schéma
    state.schema = Array.isArray(data.schema) ? data.schema.map(row => row.slice()) : [];

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
        const gender = (s.gender === "F" || s.gender === "M") ? s.gender : null;
        return {id, name, first, last, gender};
    });

    // Contraintes
    state.constraints = Array.isArray(data.constraints) ? data.constraints.slice() : [];

    // Sièges interdits
    state.forbidden = new Set(Array.isArray(data.forbidden) ? data.forbidden : []);

    // Placements
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

/* =======================================================================
   Détection & wiring
   ======================================================================= */

/**
 * Détecte l’extension probable.
 * @param {File} f
 * @returns {"csv"|"json"|"unknown"}
 */
function guessFileKind(f) {
    const name = (f.name || "").toLowerCase();
    if (name.endsWith(".csv")) return "csv";
    if (name.endsWith(".json")) return "json";
    // MIME peut aider, mais certains navigateurs mettent "application/octet-stream"
    const type = (f.type || "").toLowerCase();
    if (type.includes("json")) return "json";
    if (type.includes("csv") || type.includes("comma-separated")) return "csv";
    return "unknown";
}

/**
 * Handler principal : un seul input accepte .csv et .json
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
            // Permet de re-sélectionner le même fichier derrière
            input.value = "";
        }
    });
}
