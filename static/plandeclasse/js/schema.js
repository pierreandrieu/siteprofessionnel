// static/plandeclasse/js/schema.js
"use strict";

/**
 * Module Schema : (re)construction du plan (rangées/tables/capacités) et
 * nettoyage des placements/interdits/cohérence avec contraintes.
 */

import {state} from "./state.js";
import {keyOf} from "./utils.js";
import {renderRoom, renderStudents, updateBanButtonLabel} from "./render.js";
import {renderConstraints} from "./constraints.js";

export function applySchema(rows /**: number */, tablesPerRow /**: number */, capacitiesStr /**: string */) {
    const caps = capacitiesStr
        .split(/[,\s]+/)
        .map((s) => Number(s.trim()))
        .filter((n) => Number.isFinite(n) && n > 0);

    if (caps.length !== tablesPerRow) {
        alert(`le nombre de capacités (${caps.length}) doit = tables / rangée (${tablesPerRow}).`);
        return;
    }

    const newSchema = Array.from({length: rows}, () => caps.slice());
    const newPlacements = new Map();
    const newPlacedByStudent = new Map();

    for (const [seatKey, sid] of state.placements.entries()) {
        const [x, y, s] = seatKey.split(",").map(Number);
        if (y < newSchema.length && x < newSchema[y].length && s < newSchema[y][x]) {
            newPlacements.set(seatKey, sid);
            newPlacedByStudent.set(sid, seatKey);
        }
    }

    state.schema = newSchema;
    state.placements = newPlacements;
    state.placedByStudent = newPlacedByStudent;

    const newForbidden = new Set();
    const newForbidConstraints = [];
    for (const k of state.forbidden) {
        const [x, y, s] = k.split(",").map(Number);
        if (y < newSchema.length && x < newSchema[y].length && s < newSchema[y][x]) {
            newForbidden.add(k);
            newForbidConstraints.push({
                type: "forbid_seat",
                x, y, s,
                human: `siège (x=${x}, y=${y}, s=${s}) doit rester vide`,
                key: k,
            });
        }
    }
    state.forbidden = newForbidden;
    state.constraints = state.constraints.filter((c) => c.type !== "forbid_seat").concat(newForbidConstraints);

    renderRoom();
    renderStudents();
    renderConstraints();
    updateBanButtonLabel();
}
