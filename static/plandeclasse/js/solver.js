// static/plandeclasse/js/solver.js
"use strict";

/**
 * Module Solver :
 * - sérialisation du payload,
 * - démarrage du calcul côté backend,
 * - polling de l'état,
 * - application de la solution et exposition des liens d'export,
 * - gestion de l’activation du bouton "générer" selon l’état (élèves + schéma).
 *
 * Sécurité/CSP : pas d’HTML injecté, pas de style inline.
 */

import {state as etat} from "plandeclasse/state";
import {
    renderRoom as rendreSalle,
    renderStudents as rendreEleves,
    updateBanButtonLabel as majBoutonBan
} from "plandeclasse/render";

/* ==========================================================================
   Préconditions (btn "générer")
   ========================================================================== */

/** Retourne true si le schéma contient au moins une table réelle (>0). */
function schemaPret() {
    const sch = etat.schema;
    if (!Array.isArray(sch) || sch.length === 0) return false;
    for (const rangee of sch) {
        if (!Array.isArray(rangee) || rangee.length === 0) return false;
        const aUneTable = rangee.some((cap) => Number.isFinite(cap) && cap > 0);
        if (!aUneTable) return false;
    }
    return true;
}

/** Retourne true si au moins 1 élève est chargé. */
function elevesCharges() {
    return Array.isArray(etat.students) && etat.students.length > 0;
}

/**
 * Met à jour l’état enabled/disabled du bouton #btnSolve + tooltip explicatif.
 * À appeler après tout changement CSV/schéma/reset.
 */
export function syncSolveButtonEnabled() {
    /** @type {HTMLButtonElement|null} */
    const btn = document.getElementById("btnSolve");
    /** @type {HTMLElement|null} */
    const wrap = document.getElementById("solveBtnWrap");
    if (!btn) return;

    const okEleves = elevesCharges();
    const okSchema = schemaPret();
    const pret = okEleves && okSchema;
    btn.disabled = !pret;

    if (wrap && window.bootstrap?.Tooltip) {
        const tip = bootstrap.Tooltip.getOrCreateInstance(wrap, {
            trigger: "hover focus",
            placement: "top",
            title: wrap.getAttribute("title") || "",
        });

        if (!pret) {
            let msg = "Préparez le calcul : ";
            if (!okEleves && !okSchema) msg += "chargez un CSV/JSON et appliquez un schéma de salle.";
            else if (!okEleves) msg += "chargez un CSV/JSON d’élèves.";
            else msg += "appliquez un schéma de salle.";

            if (typeof tip.setContent === "function") {
                tip.setContent({".tooltip-inner": msg});
            } else {
                wrap.setAttribute("title", msg);
                tip.update();
            }
            tip.enable();
            wrap.classList.remove("pe-none");
        } else {
            try {
                tip.hide();
            } catch {
            }
            tip.disable();
            wrap.classList.remove("pe-none");
            wrap.removeAttribute("title");
        }

        if (!wrap.dataset.wired) {
            wrap.dataset.wired = "1";
            wrap.addEventListener("click", (ev) => {
                if (btn.disabled) {
                    ev.preventDefault();
                    try {
                        tip.show();
                        setTimeout(() => {
                            try {
                                tip.hide();
                            } catch {
                            }
                        }, 1400);
                    } catch {
                    }
                }
            });
        }
    }
}

/** À appeler au chargement pour initialiser l’état et le tooltip. */
export function setupSolveUI() {
    syncSolveButtonEnabled();
}

function sanitizeConstraintsForSolver(list) {
    const out = [];
    for (const c of list || []) {
        if (!c || c.type === "_batch_marker_" || c.type === "_objective_") continue;
        if (c.type === "forbid_seat") continue; // déjà porté par `forbidden`

        // On conserve metric / en_pixels si présents
        const {
            type, a, b, x, y, s, k, d,
            metric, en_pixels, seat // seat toléré (exact_seat)
        } = c;

        const cc = {type, a, b, x, y, s, k, d};
        if (seat != null && cc.s == null) cc.seat = seat;
        if (metric != null) cc.metric = String(metric).trim().toLowerCase();
        if (en_pixels != null) cc.en_pixels = !!en_pixels;

        out.push(cc);
    }
    return out;
}


/* ==========================================================================
   Payload solveur
   ========================================================================== */


/**
 * Construit le payload envoyé au backend pour résoudre.
 * - Si etat.options.lock_placements est vrai, on envoie les placements actuels
 *   pour qu’ils soient verrouillés côté solveur (exact_seat).
 */
export function buildSolvePayload() {
    const candidates = [
        etat.placements,
        etat.fixedPlacements,
        etat.pinned,
        etat.lockedSeats,
        etat.placedByStudent
            ? new Map(Array.from(etat.placedByStudent, ([sid, seat]) => [seat, Number(sid)]))
            : null,
    ].filter(Boolean);

    let source = candidates.find(m => m && m.size) || new Map();
    let lockedPlacements = Object.fromEntries(source);

    const hasExact = etat.constraints.some((c) => c.type === "exact_seat");
    if (hasExact) lockedPlacements = {};

    const lockFromState = Object.prototype.hasOwnProperty.call(etat.options, "lock_placements")
        ? !!etat.options.lock_placements
        : true;
    const lock_placements = hasExact ? false : (lockFromState || Object.keys(lockedPlacements).length > 0);

    //  ordre visuel des rangées (haut -> bas)
    const visual_row_order = computeVisualRowOrder(); // déjà là
    const visual_row_map = computeVisualRowMap();     // NEW

    const solverChoice = visual_row_order && visual_row_order.length ? "cpsat" : (etat.options.solver || "asp");

    return {
        schema: etat.schema,
        students: etat.students.map(s => ({
            id: Number(s.id),
            name: s.name,
            first: s.first,
            last: s.last,
            gender: s.gender ?? null
        })),
        options: {
            ...etat.options,
            solver: solverChoice,
            lock_placements,
            visual_row_order: visual_row_order || null
        },
        constraints: sanitizeConstraintsForSolver(etat.constraints),
        forbidden: Array.from(etat.forbidden),
        placements: lockedPlacements,
        name_view: etat.nameView,
        visual_row_map: visual_row_map || null,
    };
}
    /* ==========================================================================
       Démarrage + polling
       ========================================================================== */

// États "en cours" côté backend
const ETATS_EN_COURS = new Set(["PENDING", "RECEIVED", "STARTED", "RETRY"]);

// Garde-fous runtime
let _pollHandle /**: number|null */ = null;
let _aborteur /**: AbortController|null */ = null;
let _solveEnCours = false;

/** Nettoyage commun (fin de polling et réactivation bouton). */
function nettoyerApresSolve() {
    if (_pollHandle) {
        clearTimeout(_pollHandle);
        _pollHandle = null;
    }
    if (_aborteur) {
        try {
            _aborteur.abort();
        } catch {
        }
        _aborteur = null;
    }
    _solveEnCours = false;
    const btn = document.getElementById("btnSolve");
    if (btn) btn.removeAttribute("disabled");
}

/**
 * Applique une affectation renvoyée par le solveur au state + rerendu.
 * @param {Record<string, number>} assignmentObj - mapping "x,y,s" -> studentId
 */
export function applyAssignment(assignmentObj) {
    etat.placements.clear();
    etat.placedByStudent.clear();
    for (const [cleSiege, sid] of Object.entries(assignmentObj)) {
        const idNum = Number(sid);
        etat.placements.set(cleSiege, idNum);
        etat.placedByStudent.set(idNum, cleSiege);
    }
    rendreSalle();
    rendreEleves();
    majBoutonBan();
}

/**
 * Démarre le solve côté serveur et gère le polling jusqu’à succès/échec/time-out.
 * Backoff progressif (800 → 2000 ms).
 */
export async function startSolve() {
    const btn = document.getElementById("btnSolve");
    const statutEl = document.getElementById("solveStatus");
    const blocDl = document.getElementById("solveDownloads");
    const lienPNG = document.getElementById("dlPNG");
    const lienPDF = document.getElementById("dlPDF");
    const lienSVG = document.getElementById("dlSVG");
    const lienTXT = document.getElementById("dlTXT");

    // Évite les solves concurrents
    if (_solveEnCours) return;

    // Préconditions
    if (!elevesCharges() || !schemaPret()) {
        syncSolveButtonEnabled();
        return;
    }

    // Réinit UI / états
    _solveEnCours = true;
    if (_pollHandle) {
        clearTimeout(_pollHandle);
        _pollHandle = null;
    }
    if (blocDl) blocDl.classList.add("d-none");
    if (btn) btn.setAttribute("disabled", "true");
    if (statutEl) statutEl.textContent = "envoi...";

    const payload = JSON.stringify(buildSolvePayload());

    try {
        // 1) Démarrage du job
        const r = await fetch("/plandeclasse/solve/start", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: payload,
        });
        if (!r.ok) throw new Error("start failed");

        const {task_id} = await r.json();
        if (statutEl) statutEl.textContent = "calcul en cours…";

        // 2) Polling avec backoff et délai max
        const debut = Date.now();
        const budgetMs = Number(etat.options?.time_budget_ms) || 60000;
        const delaiMaxMs = Math.max(2000, budgetMs + 5000); // petite marge de grâce
        let attenteMs = 800; // backoff de départ

        _aborteur = new AbortController();

        const pollUneFois = async () => {
            // Time-out global
            if (Date.now() - debut > delaiMaxMs) {
                if (statutEl) statutEl.textContent = "échec : délai dépassé";
                nettoyerApresSolve();
                return;
            }

            try {
                const rr = await fetch(`/plandeclasse/solve/status/${task_id}`, {
                    signal: _aborteur.signal,
                });
                const data = await rr.json();

                // Toujours en cours ?
                if (data.status && ETATS_EN_COURS.has(data.status)) {
                    // Replanifie avec backoff plafonné
                    attenteMs = Math.min(2000, Math.floor(attenteMs * 1.25));
                    _pollHandle = setTimeout(pollUneFois, attenteMs);
                    return;
                }

                // Fini (succès/échec)
                if (btn) btn.removeAttribute("disabled");

                if (data.status === "SUCCESS") {
                    // Applique l’affectation
                    applyAssignment(data.assignment || {});
                    // Renseigne les liens si présents
                    if (data.download && lienPNG && lienPDF && lienSVG && lienTXT && blocDl) {
                        // @ts-ignore : éléments sont des <a>
                        lienPNG.href = data.download.png || "#";
                        // @ts-ignore
                        lienPDF.href = data.download.pdf || "#";
                        // @ts-ignore
                        lienSVG.href = data.download.svg || "#";
                        // @ts-ignore
                        lienTXT.href = data.download.txt || "#";
                        blocDl.classList.remove("d-none");
                    }
                    if (statutEl) statutEl.textContent = "terminé ✔";
                } else {
                    const msg = data.error ? String(data.error) : "aucune solution";
                    if (statutEl) statutEl.textContent = `échec : ${msg}`;
                }
                nettoyerApresSolve();
            } catch (_e) {
                // Erreur réseau ou abort → on stoppe proprement
                if (btn) btn.removeAttribute("disabled");
                if (statutEl) statutEl.textContent = "erreur de polling";
                nettoyerApresSolve();
            }
        };

        // Première itération
        _pollHandle = setTimeout(pollUneFois, attenteMs);
    } catch (_e) {
        if (statutEl) statutEl.textContent = "erreur d’envoi";
        nettoyerApresSolve();
    }
}

// solver.js
function mediane(nums) {
    const a = [...nums].sort((x, y) => x - y);
    const m = Math.floor(a.length / 2);
    return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2;
}

function computeVisualRowOrder() {
    const svg = document.getElementById("roomCanvas");
    if (!svg) return null;

    const rows = new Map(); // y -> [centresY]
    svg.querySelectorAll("g[data-table]").forEach(g => {
        const tk = g.getAttribute("data-table");
        if (!tk) return;
        const [, yStr] = tk.split(",");
        const y = Number(yStr);
        const m = /translate\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)/.exec(g.getAttribute("transform") || "");
        const ty = m ? Number(m[2]) : 0;
        const rect = g.querySelector("rect.table-rect");
        const h = rect ? Number(rect.getAttribute("height") || "0") : 0;
        const cy = ty + h / 2;
        if (!rows.has(y)) rows.set(y, []);
        rows.get(y).push(cy);
    });

    const infos = Array.from(rows.entries()).map(([y, arr]) => ({y, med: mediane(arr)}));
    if (!infos.length) return null;
    infos.sort((a, b) => a.med - b.med);
    return infos.map(r => r.y);
}


// mappe chaque table (x,y) vers une "rangée visuelle" 0..R-1.
// Idée : on trie toutes les tables par leur Y-centre courant, puis on
// partitionne ce tri global en groupes de tailles identiques aux rangées
// du schéma (on conserve donc le nombre de tables par rangée).
function computeVisualRowMap() {
    const svg = document.getElementById("roomCanvas");
    if (!svg) return null;

    // 1) Collecte centres Y des tables affichées
    const tables = []; // {tk:"x,y", x,y, cy}
    svg.querySelectorAll("g[data-table]").forEach(g => {
        const tk = g.getAttribute("data-table") || "";
        const [xs, ys] = tk.split(",");
        const x = Number(xs), y = Number(ys);
        const m = /translate\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)/.exec(g.getAttribute("transform") || "");
        const ty = m ? Number(m[2]) : 0;
        const rect = g.querySelector("rect.table-rect");
        const h = rect ? Number(rect.getAttribute("height") || "0") : 0;
        const cy = ty + h / 2;
        tables.push({tk, x, y, cy});
    });
    if (!tables.length) return null;

    // 2) Tailles des rangées (en nombre de tables réelles, cap>0)
    const tailles = etat.schema.map(r => r.filter(c => c > 0).length);
    const total = tailles.reduce((a, b) => a + b, 0);
    if (total !== tables.length) return null; // garde-fou

    // 3) Tri global haut -> bas
    tables.sort((a, b) => a.cy - b.cy);

    // 4) Partition séquentielle selon tailles (conserve la "cardinalité" des rangées)
    const visMap = {}; // "x,y" -> rangéeVisuelle
    let i = 0;
    for (let r = 0; r < tailles.length; r++) {
        const n = tailles[r];
        for (let k = 0; k < n; k++, i++) {
            const t = tables[i];
            if (t) visMap[t.tk] = r;
        }
    }
    return visMap;
}

