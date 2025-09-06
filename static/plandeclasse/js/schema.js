// static/plandeclasse/js/schema.js
"use strict";


/**
 * Module Schema : (re)construction du plan (rangées/tables/capacités) et
 * nettoyage des placements/interdits/cohérence avec contraintes.
 */

import {state} from "./state.js";
import {renderRoom, renderStudents, updateBanButtonLabel} from "./render.js";
import {renderConstraints} from "./constraints.js";


/**
 * Recalage des placements/interdits/contraintes après un changement de schéma
 * (sans reconstruire state.schema). Les capacités négatives sont des "trous".
 */
export function reconcileAfterSchemaChange() {
    const newPlacements = new Map();
    const newPlacedByStudent = new Map();

    for (const [seatKey, sid] of state.placements.entries()) {
        const [x, y, s] = seatKey.split(",").map(Number);
        if (y < state.schema.length && x < state.schema[y].length) {
            const cap = state.schema[y][x];
            if (cap > 0 && s < cap) {
                newPlacements.set(seatKey, sid);
                newPlacedByStudent.set(sid, seatKey);
            }
        }
    }
    state.placements = newPlacements;
    state.placedByStudent = newPlacedByStudent;

    const newForbidden = new Set();
    const newForbidConstraints = [];
    for (const k of state.forbidden) {
        const [x, y, s] = k.split(",").map(Number);
        if (y < state.schema.length && x < state.schema[y].length) {
            const cap = state.schema[y][x];
            if (cap > 0 && s < cap) {
                newForbidden.add(k);
                newForbidConstraints.push({
                    type: "forbid_seat",
                    x, y, s,
                    human: `siège (x=${x}, y=${y}, s=${s}) doit rester vide`,
                    key: k,
                });
            }
        }
    }
    state.forbidden = newForbidden;
    state.constraints = state.constraints
        .filter((c) => c.type !== "forbid_seat")
        .concat(newForbidConstraints);

    renderRoom();
    renderStudents();
    renderConstraints();
    updateBanButtonLabel();
}


export function applySchema(rows /**: number */, capacitiesStr /**: string */) {
    const caps = capacitiesStr
        .split(/[,\s]+/)
        .map((s) => Number(s.trim()))
        .filter((n) => Number.isFinite(n) && n !== 0);

    //  reconstruit toutes les rangées à l’identique
    const newSchema = Array.from({length: rows}, () => caps.slice());
    state.schema = newSchema;

    // recale le reste sans toucher de nouveau au schéma
    reconcileAfterSchemaChange();
}

/**
 * Réinitialise la **salle** (schéma) et recale l’état dépendant.
 *
 * Effets :
 * - Vide le schéma (state.schema = [])
 * - Recalage via reconcileAfterSchemaChange() : nettoie placements et
 *   reconstruit proprement l’état “sièges interdits/contraintes de siège”
 * - Efface la sélection courante
 * - Re-rend l’UI (salle/élèves/contraintes) + met à jour les boutons
 *
 * Conserve :
 * - Les contraintes non structurelles (unaires/binaires) restent telles quelles
 *   (inutiles avec une salle vide, mais on n’efface pas la “liste de souhaits”)
 */
export function resetRoomSchema() {
    // Vide le schéma
    state.schema = [];

    // La sélection n’a plus de sens
    state.selection.studentId = null;
    state.selection.seatKey = null;

    // Recalage général (purge placements + reclasse les “forbid_seat” au propre)
    reconcileAfterSchemaChange();

    // (reconcileAfterSchemaChange fait déjà les render + updateBanButtonLabel)
}
