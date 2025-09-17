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

import {clearSelection, clearTableNudgeDraft, state} from "plandeclasse/state";
import {renderRoom, renderStudents, updateBanButtonLabel} from "plandeclasse/render";
import {renderConstraints} from "plandeclasse/constraints";

/** Déplacement unitaire du ghost (en unités SVG). */
const NUDGE_STEP = 12;


/* ==========================================================================
   Déplacement clavier (nudge)
   ========================================================================== */

/**
 * Retourne toutes les boîtes englobantes (x,y,w,h) des tables actuelles,
 * en unités SVG, lues directement dans le DOM (donc offsets déjà pris en compte).
 * @returns {Array<{key:string,x:number,y:number,w:number,h:number}>}
 */
function readCurrentTableBoxes() {
    const svg = /** @type {SVGSVGElement|null} */ (document.getElementById("roomCanvas"));
    if (!svg) return [];
    const out = [];
    svg.querySelectorAll("g[data-table]").forEach((g) => {
        const key = g.getAttribute("data-table") || "";
        // rect de la table à l’intérieur du groupe
        const rect = g.querySelector("rect.table-rect");
        if (!rect) return;
        // on lit la translation du groupe
        const tf = g.getAttribute("transform") || "";
        const m = /translate\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)/.exec(tf);
        const tx = m ? Number(m[1]) : 0;
        const ty = m ? Number(m[2]) : 0;

        const w = Number(rect.getAttribute("width") || "0");
        const h = Number(rect.getAttribute("height") || "0");
        const x = tx + Number(rect.getAttribute("x") || "0"); // rect est à 0 dans notre rendu
        const y = ty + Number(rect.getAttribute("y") || "0");
        out.push({key, x, y, w, h});
    });
    return out;
}

/**
 * Teste le chevauchement entre deux boîtes (axis-aligned).
 * @param {{x:number,y:number,w:number,h:number}} a
 * @param {{x:number,y:number,w:number,h:number}} b
 */
function boxesOverlap(a, b) {
    return !(a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + a.h <= b.y || b.y + b.h <= a.y);
}

/**
 * Met à jour l’état du ghost (draft) en appliquant dx/dy puis recalcule “invalid”
 * selon les collisions avec les autres tables (via DOM).
 * @param {number} ddx
 * @param {number} ddy
 */
function nudgeDraftBy(ddx, ddy) {
    const sel = state.selection.tableKey;
    if (!sel) return;

    // initialise le draft si besoin
    if (!state.uiDraft.nudge || state.uiDraft.nudge.tableKey !== sel) {
        state.uiDraft.nudge = {tableKey: sel, dx: 0, dy: 0, invalid: false};
    }
    const d = state.uiDraft.nudge;
    d.dx += ddx;
    d.dy += ddy;

    // collision check
    const boxes = readCurrentTableBoxes();
    const me = boxes.find((b) => b.key === sel);
    if (!me) {
        d.invalid = true;
        return;
    }
    const moved = {x: me.x + d.dx, y: me.y + d.dy, w: me.w, h: me.h};
    d.invalid = boxes.some((b) => b.key !== sel && boxesOverlap(moved, b));
}

/**
 * Valide le draft courant : ajoute (dx,dy) dans state.tableOffsets pour la table sélectionnée.
 * Si `invalid` est vrai, on ignore.
 */
function commitDraftIfValid() {
    const d = state.uiDraft.nudge;
    const sel = state.selection.tableKey;
    if (!d || !sel || d.invalid) return;
    const cur = state.tableOffsets.get(sel) || {dx: 0, dy: 0};
    state.tableOffsets.set(sel, {dx: cur.dx + d.dx, dy: cur.dy + d.dy});
    clearTableNudgeDraft();
}

/**
 * Gestionnaire global des touches :
 *  - flèches / z q s d : création/ajustement du ghost
 *  - Enter : commit
 *  - Escape : annuler
 * Réécrit pour n’affecter que la sélection “table”.
 * @param {KeyboardEvent} ev
 */
export function onGlobalKeydown(ev) {
    // on évite de gêner la saisie dans des champs
    const target = /** @type {HTMLElement|null} */ (ev.target);
    const tag = (target?.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || target?.isContentEditable) return;

    const sel = state.selection.tableKey;
    if (!sel) return;

    const k = ev.key.toLowerCase();
    let handled = false;

    if (k === "arrowleft" || k === "q") {
        nudgeDraftBy(-NUDGE_STEP, 0);
        handled = true;
    } else if (k === "arrowright" || k === "d") {
        nudgeDraftBy(NUDGE_STEP, 0);
        handled = true;
    } else if (k === "arrowup" || k === "z") {
        nudgeDraftBy(0, -NUDGE_STEP);
        handled = true;
    } else if (k === "arrowdown" || k === "s") {
        nudgeDraftBy(0, NUDGE_STEP);
        handled = true;
    } else if (k === "enter") {
        commitDraftIfValid();
        handled = true;
    } else if (k === "escape") {
        clearTableNudgeDraft();
        handled = true;
    }

    if (handled) {
        ev.preventDefault();
        renderRoom(); // le ghost est dessiné dans renderRoom()
    }
}

// Auto-wiring : ce module écoute le clavier dès qu’il est importé.
if (typeof window !== "undefined") {
    window.addEventListener("keydown", onGlobalKeydown, {passive: false});
}

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
    if (cur) {
        cur.x = x;
        cur.y = y;
        cur.s = s;
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
 * Recherche d’un seatKey ET/OU d’un tableKey en remontant la chaîne des parents.
 * Retourne les deux si disponibles (utile pour Alt-clic).
 * @param {EventTarget|null} start
 * @returns {{seatKey:string|null, tableKey:string|null}}
 */
function hitTestSeatOrTable(start) {
    let el = /** @type {any} */ (start);
    let seatKey = null;
    let tableKey = null;

    while (el) {
        if (el instanceof SVGElement) {
            if (!seatKey) {
                const sk = el.getAttribute("data-seat");
                if (sk) seatKey = sk;
            }
            if (!tableKey) {
                const tk = el.getAttribute("data-table");
                if (tk) tableKey = tk;
            }
        }
        // @ts-ignore
        el = el.parentNode;
    }
    return {seatKey, tableKey};
}

/**
 * Clic sur le canvas :
 *  - Alt-clic → sélectionne la TABLE même si l’on clique sur un siège
 *  - Clic normal sur un siège → logique siège habituelle (seatClick)
 *  - Clic sur la zone "grab strip" de la table → sélectionne la table
 * @param {MouseEvent} ev
 */
export function onCanvasClick(ev) {
    const {seatKey, tableKey} = hitTestSeatOrTable(ev.target);

    // Alt-clic : forcer la sélection de table si identifiable
    if (ev.altKey && tableKey) {
        clearSelection();
        state.selection.tableKey = tableKey;
        clearTableNudgeDraft();
        renderRoom();
        updateBanButtonLabel();
        return;
    }

    // Clic "classique" : priorité au siège si présent
    if (seatKey) {
        // On oublie une éventuelle sélection de table et on délègue à seatClick
        state.selection.tableKey = null;
        seatClick(seatKey);
        return;
    }

    // Sinon, clic sur la table (fond ou "grab strip")
    if (tableKey) {
        clearSelection();
        state.selection.tableKey = tableKey;
        clearTableNudgeDraft();
        renderRoom();
        updateBanButtonLabel();
        return;
    }

    // Clic dans le vide : rien à faire
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
