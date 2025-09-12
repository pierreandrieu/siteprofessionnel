// static/plandeclasse/js/interactions.js
"use strict";

/**
 * Module Interactions
 * -------------------
 * Gère les interactions utilisateur côté UI :
 *  - clic sur un siège (sélection / affectation / permutation),
 *  - bannir/débannir un siège,
 *  - désaffecter un élève de son siège,
 *  - reset du plan sans toucher au schéma de la salle.
 *
 *  Responsabilités :
 *  - Ne contient pas de logique de rendu : délègue à render.js / constraints.js.
 *  - Maintient la cohérence de `state.selection`, `state.placements`,
 *    `state.placedByStudent`, `state.forbidden` et des contraintes locales.
 *
 *  CSP-friendly : aucun style inline, aucun HTML injecté ici.
 */

import {state} from "./state.js";
import {renderRoom, renderStudents, updateBanButtonLabel} from "./render.js";
import {renderConstraints} from "./constraints.js";

/* ==========================================================================
   Aides locales (rafraîchis l'UI après mutation d'état)
   ========================================================================== */

/** Rafraîchit les vues dépendantes du plan + boutons de contexte. */
function refreshPlanUI() {
    renderRoom();
    renderStudents();
    updateBanButtonLabel();
}

/** Rafraîchit les contraintes visibles (liste des « pills »). */
function refreshConstraintsUI() {
    renderConstraints();
}

/** Trouve une contrainte exact_seat par élève. */
function findExactSeatConstraint(sid) {
        return state.constraints.find((c) => c.type === "exact_seat" && Number(c.a) === Number(sid)) || null;
}

/** Ajoute ou met à jour la contrainte exact_seat pour sid -> seatKey. */
function upsertExactSeatConstraint(sid, seatKey) {
    const [x, y, s] = seatKey.split(",").map(Number);
    const cur = findExactSeatConstraint(sid);
    const human = ` ${x}, ${y}, ${s}`;
    if (cur) {
        cur.x = x;
        cur.y = y;
        cur.s = s;
        cur.human = `${cur.human || ""}`.trim();
    } else {
        state.constraints.push({type: "exact_seat", a: Number(sid), x, y, s});
    }
    refreshConstraintsUI();
}

/** Supprime la contrainte exact_seat pour cet élève (s’il y en a une). */
function removeExactSeatConstraint(sid) {
    const idx = state.constraints.findIndex((c) => c.type === "exact_seat" && Number(c.a) === Number(sid));
    if (idx >= 0)
        state.constraints.splice(idx, 1);
    refreshConstraintsUI();
}

/* ==========================================================================
+   Ré-application des placements "pinnés" (exact_seat) depuis les contraintes
+   ========================================================================== */
function reapplyExactSeatsFromConstraints() {
    // pour des checks rapides
    const validIds = new Set(state.students.map((s) => s.id));
        /** Util : construit une seatKey fiable depuis une contrainte. */
    const keyFromC = (c) => {
        if (typeof c.key === "string" && c.key.includes(",")) return c.key;
        const x = Number(c.x ?? c.X);
        const y = Number(c.y ?? c.Y);
        const s = Number(c.s ?? c.seat);
        if ([x, y, s].every(Number.isFinite)) return `${x},${y},${s}`;
        return null;
    };
    for (const c of state.constraints) {
        if (c.type !== "exact_seat") continue;
            // tolérant : a | studentId | eleve (numérique côté UI)
        const sid = Number(c.a ?? c.studentId ?? c.eleve);
        if (!Number.isFinite(sid) || !validIds.has(sid)) continue;
        const k = keyFromC(c);
        if (!k) continue;
            // existence du siège dans le schéma
        const [x, y, s] = k.split(",").map(Number);
        if (!(y >= 0 && y < state.schema.length)) continue;
        if (!(x >= 0 && x < state.schema[y].length)) continue;
        const cap = state.schema[y][x];
        if (!(cap > 0 && s >= 0 && s < cap)) continue;
            // on évite de poser sur un siège explicitement interdit
        if (state.forbidden.has(k)) continue;
        // place (en supposant reset → personne n'est encore posé)
        if (!state.placements.has(k)) {
            state.placements.set(k, sid);
            state.placedByStudent.set(sid, k);
        }
    }
}


/* ==========================================================================
   Réinitialisation du plan (sans toucher à la salle)
   ========================================================================== */

/**
 * Réinitialise **uniquement** le plan de classe (affectations).
 *
 * Effets :
 * - Vide `state.placements` et `state.placedByStudent`
 * - Efface la sélection courante (élève/siège)
 * - Met à jour l'UI (salle, élèves, boutons, contraintes inchangées)
 *
 * Ne modifie PAS :
 * - Le schéma de salle (`state.schema`)
 * - Les contraintes (`state.constraints`)
 * - Les sièges explicitement interdits (`state.forbidden`)
 */
export function resetPlanKeepRoom() {
    state.placements.clear();
    state.placedByStudent.clear();
    state.selection.studentId = null;
    state.selection.seatKey = null;

    reapplyExactSeatsFromConstraints();
    // Re-rendu + synchro des boutons de contexte
    refreshPlanUI();
    // Affiche toujours la liste des contraintes (inchangée)
    refreshConstraintsUI();
}

/** Construit "x,y,s" à partir d'une contrainte exact_seat (tolérante). */
function keyFromExactSeatConstraint(c) {
    if (typeof c?.key === "string" && c.key.includes(",")) return c.key;
    const x = Number(c?.x ?? c?.X);
    const y = Number(c?.y ?? c?.Y);
    const s = Number(c?.s ?? c?.seat);
    return [x, y, s].every(Number.isFinite) ? `${x},${y},${s}` : null;
}

/** Supprime la contrainte exact_seat qui fixe `sid` sur `seatKey` (s’il y en a une). */
function removeExactSeatConstraintFor(sid, seatKey) {
    let changed = false;
    state.constraints = state.constraints.filter((c) => {
        if (c?.type !== "exact_seat") return true;
        const cSid = Number(c.a ?? c.studentId ?? c.eleve);
        if (!Number.isFinite(cSid) || cSid !== Number(sid)) return true;
        const k = keyFromExactSeatConstraint(c);
        if (k !== seatKey) return true;
        changed = true;            // on retire cette contrainte
        return false;
    });
    if (changed) renderConstraints();
}


/* ==========================================================================
   Clic sur un siège (sélection / affectation / permutation)
   ========================================================================== */

/**
 * Traite un clic sur un siège.
 *
 * Cas gérés si un élève est sélectionné :
 *  - Si le siège est interdit → ignore.
 *  - Si le siège est vide     → place l'élève (en retirant sa place précédente si besoin).
 *  - Si le siège contient le même élève :
 *      • 1er clic : sélectionne le siège (mise en évidence)
 *      • 2e clic sur le même siège : désélectionne l'élève+siège
 *  - Si le siège contient un autre élève :
 *      • permute si l'élève sélectionné avait déjà une place,
 *      • sinon, déplace l'autre élève (libère le siège) puis place l'élève sélectionné.
 *
 * Cas gérés si aucun élève n'est sélectionné :
 *  - Siège occupé   → sélectionne cet élève + le siège.
 *  - Siège non occupé → toggle de la sélection du siège seul.
 *
 * @param {string} seatKey - clé canonique "x,y,s"
 */
export function seatClick(seatKey) {
    const occupant = state.placements.get(seatKey) ?? null;
    const selSid = state.selection.studentId;

    // --- Un élève est sélectionné : tentative de placement/permutation
    if (selSid != null) {
        // impossible de poser sur un siège interdit
        if (state.forbidden.has(seatKey)) return;

        const prevSeat = state.placedByStudent.get(selSid) || null;

        if (occupant == null) {
            // Siège vide → placer l'élève
            if (prevSeat) state.placements.delete(prevSeat);
            state.placements.set(seatKey, selSid);
            state.placedByStudent.set(selSid, seatKey);
            // Action manuelle : contrainte/maj exact_seat pour l'élève sélectionné
            upsertExactSeatConstraint(selSid, seatKey);
            // nettoyage de la sélection
            state.selection.studentId = null;
            state.selection.seatKey = null;
        } else if (occupant === selSid) {
            // Clic sur sa propre place : toggle de la sélection du siège
            if (state.selection.seatKey === seatKey) {
                state.selection.studentId = null;
                state.selection.seatKey = null;
            } else {
                state.selection.seatKey = seatKey;
            }
        } else {
            // Siège occupé par un autre élève → permutation / déplacement
            if (prevSeat) {
                // Permutation : l'autre élève va sur l'ancienne place du sélectionné
                state.placements.set(prevSeat, occupant);
                state.placedByStudent.set(occupant, prevSeat);
            } else {
                // Pas d'ancienne place → libère le siège pour l'autre élève
                state.placedByStudent.delete(occupant);
                state.placements.delete(seatKey);
            }
            // Place l'élève sélectionné sur le siège cliqué
            state.placements.set(seatKey, selSid);
            state.placedByStudent.set(selSid, seatKey);
            // Contrainte exacte mise à jour uniquement pour l’élève que l’utilisateur manipule
            upsertExactSeatConstraint(selSid, seatKey);
            state.selection.studentId = null;
            state.selection.seatKey = null;
        }

        refreshPlanUI();
        return;
    }

    // --- Aucun élève sélectionné : on joue sur la sélection (élève/siège)
    if (occupant != null) {
        state.selection.studentId = occupant;
        state.selection.seatKey = seatKey;
    } else {
        state.selection.seatKey = state.selection.seatKey === seatKey ? null : seatKey;
        state.selection.studentId = null;
    }

    refreshPlanUI();
}

/* ==========================================================================
   Délégué de clic sur le canvas
   ========================================================================== */

/**
 * Handler délégué pour le clic dans le SVG (#roomCanvas).
 * Ne réagit que si la cible porte `data-seat`.
 *
 * @param {MouseEvent} ev
 */
export function onCanvasClick(ev) {
    const target = ev.target;
    if (!(target instanceof SVGElement)) return;
    const seatKey = target.getAttribute("data-seat");
    if (seatKey) seatClick(seatKey);
}

/* ==========================================================================
   Bannir / débannir le siège sélectionné
   ========================================================================== */

/**
 * Bascule l'état "interdit" du siège actuellement sélectionné.
 * - Refuse si le siège est occupé (message explicite).
 * - Met à jour `state.forbidden` et synchronise une contrainte `forbid_seat`.
 * - Nettoie la sélection (pas de siège/élève actif après l'opération).
 */
export function toggleSelectedSeatBan() {
    const k = state.selection.seatKey;
    if (!k) return;

    if (state.placements.has(k)) {
        alert("place occupée : retirez d'abord l'élève ou permutez.");
        return;
    }

    if (state.forbidden.has(k)) {
        // Débannit + retire la contrainte correspondante
        state.forbidden.delete(k);
        const idx = state.constraints.findIndex(
            (c) => c.type === "forbid_seat" && `${c.x},${c.y},${c.s}` === k,
        );
        if (idx >= 0) state.constraints.splice(idx, 1);
    } else {
        // Bannit + ajoute la contrainte `forbid_seat`
        state.forbidden.add(k);
        const [x, y, s] = k.split(",").map(Number);
        state.constraints.push({
            type: "forbid_seat",
            x,
            y,
            s,
            human: `siège (x=${x}, y=${y}, s=${s}) doit rester vide`,
            key: k,
        });
    }

    // Nettoie la sélection
    state.selection.seatKey = null;
    state.selection.studentId = null;

    // UI : salle + contraintes + boutons
    renderRoom();
    refreshConstraintsUI();
    updateBanButtonLabel();
}

/* ==========================================================================
   Désaffecter l'élève du siège sélectionné
   ========================================================================== */

/**
 * Retire l'affectation du siège actuellement sélectionné (si occupé).
 * Nettoie la sélection et rafraîchit l'UI.
 */
export function unassignSelected() {
    const k = state.selection.seatKey;
    if (!k) return;

    const sid = state.placements.get(k);
    if (sid == null) return; // rien à retirer

    removeExactSeatConstraintFor(sid, k);
    // Supprime l’affectation (les deux index)
    state.placements.delete(k);
    state.placedByStudent.delete(sid);

    // Côté spec : "si on vide l'élève de son siège ⇒ contrainte retirée"
    removeExactSeatConstraint(sid);

    // Désélectionne tout (élève + siège)
    state.selection.studentId = null;
    state.selection.seatKey = null;

    // Re-rendu + synchro des boutons
    refreshPlanUI();
    renderConstraints();
}
