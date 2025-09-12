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

import {state as etat} from "./state.js";
import {
    renderRoom as rendreSalle,
    renderStudents as rendreEleves,
    updateBanButtonLabel as majBoutonBan
} from "./render.js";

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

/* ==========================================================================
   Payload solveur
   ========================================================================== */


/**
 * Construit le payload envoyé au backend pour résoudre.
 * - Si etat.options.lock_placements est vrai, on envoie les placements actuels
 *   pour qu’ils soient verrouillés côté solveur (exact_seat).
 */
export function buildSolvePayload() {
    // 1) Récupère la source la plus fournie des placements
    //    (selon tes versions : placements, fixedPlacements, pinned, lockedSeats, placedByStudent)
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

    // 2) Objet plat "x,y,s": id
    const lockedPlacements = Object.fromEntries(source);

    // 3) Verrouillage : par défaut true, et de toute façon true s’il y a au moins 1 placement
    const lockFromState = Object.prototype.hasOwnProperty.call(etat.options, "lock_placements")
        ? !!etat.options.lock_placements
        : true;

    const lock_placements = lockFromState || Object.keys(lockedPlacements).length > 0;

    // (debug temporaire)
    console.log("[solve] lock_placements=", lock_placements,
        "nb placements=", Object.keys(lockedPlacements).length,
        lockedPlacements);

    return {
        schema: etat.schema,
        students: etat.students.map(s => ({
            id: Number(s.id),
            name: s.name,
            first: s.first,
            last: s.last,
            gender: s.gender ?? null,
        })),
        options: {...etat.options, lock_placements},   // <-- clé attendue côté backend
        constraints: etat.constraints,
        forbidden: Array.from(etat.forbidden),
        placements: lockedPlacements,
        name_view: etat.nameView,
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
