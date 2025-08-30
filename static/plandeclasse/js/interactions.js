// static/plandeclasse/js/interactions.js
"use strict";

/**
 * Module Interactions : clique sur sièges, bannir/débannir via bouton,
 * désaffecter, sélection élève/siège. Pas de logique de rendu ici,
 * on délègue aux fonctions de render/constraints.
 */

import {state} from "./state.js";
import {renderRoom, renderStudents, updateBanButtonLabel} from "./render.js";
import {renderConstraints} from "./constraints.js";

export function seatClick(seatKey /**: string */) {
    const occupant = state.placements.get(seatKey) ?? null;
    const selSid = state.selection.studentId;

    if (selSid != null) {
        if (state.forbidden.has(seatKey)) return;

        const prevSeat = state.placedByStudent.get(selSid) || null;

        if (occupant == null) {
            if (prevSeat) state.placements.delete(prevSeat);
            state.placements.set(seatKey, selSid);
            state.placedByStudent.set(selSid, seatKey);
            state.selection.studentId = null;
            state.selection.seatKey = null;
        } else if (occupant === selSid) {
            if (state.selection.seatKey === seatKey) {
                state.selection.studentId = null;
                state.selection.seatKey = null;
            } else {
                state.selection.seatKey = seatKey;
            }
        } else {
            if (prevSeat) {
                state.placements.set(prevSeat, occupant);
                state.placedByStudent.set(occupant, prevSeat);
            } else {
                state.placedByStudent.delete(occupant);
                state.placements.delete(seatKey);
            }
            state.placements.set(seatKey, selSid);
            state.placedByStudent.set(selSid, seatKey);
            state.selection.studentId = null;
            state.selection.seatKey = null;
        }
        renderRoom();
        renderStudents();
        updateBanButtonLabel();
        return;
    }

    if (occupant != null) {
        state.selection.studentId = occupant;
        state.selection.seatKey = seatKey;
    } else {
        state.selection.seatKey = state.selection.seatKey === seatKey ? null : seatKey;
        state.selection.studentId = null;
    }

    renderStudents();
    renderRoom();
    updateBanButtonLabel();
}

export function onCanvasClick(ev /**: MouseEvent */) {
    const target = ev.target;
    if (!(target instanceof SVGElement)) return;
    const seatKey = target.getAttribute("data-seat");
    if (seatKey) seatClick(seatKey);
}

export function toggleSelectedSeatBan() {
    const k = state.selection.seatKey;
    if (!k) return;
    if (state.placements.has(k)) {
        alert("place occupée : retirez d'abord l'élève ou permutez.");
        return;
    }
    if (state.forbidden.has(k)) {
        state.forbidden.delete(k);
        const idx = state.constraints.findIndex((c) => c.type === "forbid_seat" && `${c.x},${c.y},${c.s}` === k);
        if (idx >= 0) state.constraints.splice(idx, 1);
    } else {
        state.forbidden.add(k);
        const [x, y, s] = k.split(",").map(Number);
        state.constraints.push({
            type: "forbid_seat",
            x, y, s,
            human: `siège (x=${x}, y=${y}, s=${s}) doit rester vide`,
            key: k,
        });
    }
    state.selection.seatKey = null;
    state.selection.studentId = null;

    renderRoom();
    renderConstraints();
    updateBanButtonLabel();
}

export function unassignSelected() {
    const k = state.selection.seatKey;
    if (!k) return;
    const sid = state.placements.get(k);
    if (sid != null) {
        state.placements.delete(k);
        state.placedByStudent.delete(sid);
        renderRoom();
        renderStudents();
        updateBanButtonLabel();
    }
}
