// static/plandeclasse/js/solver.js
"use strict";

/**
 * Module Solver : sérialisation du payload, démarrage du job, polling,
 * application de la solution (assignments), affichage liens d’export.
 */

import {state} from "./state.js";
import {renderRoom, renderStudents, updateBanButtonLabel} from "./render.js";

export function buildSolvePayload() {
    return {
        schema: state.schema,
        students: state.students.map(s => ({
            id: s.id,
            name: s.name,
            first: s.first,
            last: s.last,
            gender: s.gender || null
        })),
        options: state.options,
        constraints: state.constraints,
        forbidden: Array.from(state.forbidden),
        placements: Object.fromEntries(state.placements),
        name_view: state.nameView,
    };
}

let _pollTimer /**: number|null */ = null;

export async function startSolve() {
    // -- Récupération tolérante des éléments UI (peuvent ne pas exister)
    const btn = /** @type {HTMLButtonElement|null} */ (document.getElementById("btnSolve"));
    const statusEl = /** @type {HTMLElement|null} */        (document.getElementById("solveStatus"));

    // Bloc "anciens" téléchargements (peut être absent selon ton HTML actuel)
    const dl = /** @type {HTMLElement|null} */           (document.getElementById("solveDownloads"));
    const dlPNG = /** @type {HTMLAnchorElement|null} */     (document.getElementById("dlPNG"));
    const dlPDF = /** @type {HTMLAnchorElement|null} */     (document.getElementById("dlPDF"));
    const dlSVG = /** @type {HTMLAnchorElement|null} */     (document.getElementById("dlSVG"));
    const dlTXT = /** @type {HTMLAnchorElement|null} */     (document.getElementById("dlTXT"));

    // -- UI : état initial
    if (statusEl) statusEl.textContent = "envoi...";
    dl?.classList.add("d-none"); // n'agit que si le bloc existe
    if (_pollTimer) {
        clearInterval(_pollTimer);
        _pollTimer = null;
    }

    const body = JSON.stringify(buildSolvePayload());

    try {
        const r = await fetch("/plandeclasse/solve/start", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body
        });
        if (!r.ok) throw new Error("start failed");
        const {task_id} = await r.json();
        if (statusEl) statusEl.textContent = "calcul en cours…";
        if (btn) btn.disabled = true;

        // -- Polling
        _pollTimer = setInterval(async () => {
            try {
                const rr = await fetch(`/plandeclasse/solve/status/${task_id}`);
                const data = await rr.json();

                if (data.status && ["PENDING", "RECEIVED", "STARTED", "RETRY"].includes(data.status)) {
                    return; // encore en cours
                }

                clearInterval(_pollTimer);
                _pollTimer = null;
                if (btn) btn.disabled = false;

                if (data.status === "SUCCESS") {
                    // 1) appliquer l’affectation renvoyée par le solveur
                    applyAssignment(data.assignment || {});

                    // 2) afficher les liens de téléchargement si le bloc est présent
                    if (data.download && dl) {
                        if (dlPNG && data.download.png) dlPNG.href = data.download.png;
                        if (dlPDF && data.download.pdf) dlPDF.href = data.download.pdf;
                        if (dlSVG && data.download.svg) dlSVG.href = data.download.svg;
                        if (dlTXT && data.download.txt) dlTXT.href = data.download.txt;
                        dl.classList.remove("d-none");
                    }
                    if (statusEl) statusEl.textContent = "terminé ✔";
                } else {
                    if (statusEl) statusEl.textContent = `échec : ${data.error || "aucune solution"}`;
                }
            } catch (_e) {
                clearInterval(_pollTimer);
                _pollTimer = null;
                if (btn) btn.disabled = false;
                if (statusEl) statusEl.textContent = "erreur de polling";
            }
        }, 1000);
    } catch (_e) {
        if (statusEl) statusEl.textContent = "erreur d’envoi";
    }
}

/** Applique une affectation renvoyée par le solveur. */
export function applyAssignment(assignmentObj /**: Record<string,number> */) {
    state.placements.clear();
    state.placedByStudent.clear();
    for (const [seatKey, sid] of Object.entries(assignmentObj)) {
        state.placements.set(seatKey, Number(sid));
        state.placedByStudent.set(Number(sid), seatKey);
    }
    renderRoom();
    renderStudents();
    updateBanButtonLabel();
}
