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
    const btn = document.getElementById("btnSolve");
    const statusEl = document.getElementById("solveStatus");
    const dl = document.getElementById("solveDownloads");
    const dlPNG = document.getElementById("dlPNG");
    const dlPDF = document.getElementById("dlPDF");
    const dlSVG = document.getElementById("dlSVG");
    const dlTXT = document.getElementById("dlTXT");

    statusEl.textContent = "envoi...";
    dl.classList.add("d-none");
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
        statusEl.textContent = "calcul en cours…";
        btn.disabled = true;

        _pollTimer = setInterval(async () => {
            try {
                const rr = await fetch(`/plandeclasse/solve/status/${task_id}`);
                const data = await rr.json();
                if (data.status && ["PENDING", "RECEIVED", "STARTED", "RETRY"].includes(data.status)) {
                    return;
                }
                clearInterval(_pollTimer);
                _pollTimer = null;
                btn.disabled = false;

                if (data.status === "SUCCESS") {
                    applyAssignment(data.assignment || {});
                    if (data.download) {
                        dlPNG.href = data.download.png;
                        dlPDF.href = data.download.pdf;
                        dlSVG.href = data.download.svg;
                        dlTXT.href = data.download.txt;
                        dl.classList.remove("d-none");
                    }
                    statusEl.textContent = "terminé ✔";
                } else {
                    statusEl.textContent = `échec : ${data.error || "aucune solution"}`;
                }
            } catch (_e) {
                clearInterval(_pollTimer);
                _pollTimer = null;
                btn.disabled = false;
                statusEl.textContent = "erreur de polling";
            }
        }, 1000);
    } catch (_e) {
        statusEl.textContent = "erreur d’envoi";
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
