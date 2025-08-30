// static/plandeclasse/js/solver.js
"use strict";

/**
 * Module Solver :
 * - sérialisation du payload, démarrage du job, polling,
 * - application de la solution (assignments),
 * - affichage liens d’export (géré ailleurs),
 * - + gestion de l’activation du bouton "générer" selon l’état (élèves + schéma).
 */

import {state} from "./state.js";
import {renderRoom, renderStudents, updateBanButtonLabel} from "./render.js";

/* ==========================================================================
   Eligibility (bouton "générer le plan")
   ========================================================================== */

/** Retourne true si un schéma est défini et cohérent (≥1 rangée, ≥1 table/rangée, capacités >0). */
function schemaIsReady() {
    const sch = state.schema;
    if (!Array.isArray(sch) || sch.length === 0) return false;
    for (const row of sch) {
        if (!Array.isArray(row) || row.length === 0) return false;
        for (const cap of row) {
            if (!Number.isFinite(cap) || cap <= 0) return false;
        }
    }
    return true;
}

/** Retourne true si au moins 1 élève est chargé. */
function studentsAreLoaded() {
    return Array.isArray(state.students) && state.students.length > 0;
}

/**
 * Met à jour l’état enabled/disabled du bouton #btnSolve + tooltip d’explication sur #solveBtnWrap.
 * Appeler cette fonction après chaque modification du CSV, du schéma, ou reset.
 */
export function syncSolveButtonEnabled() {
    const btn = /** @type {HTMLButtonElement|null} */ (document.getElementById("btnSolve"));
    const wrap = /** @type {HTMLElement|null} */ (document.getElementById("solveBtnWrap"));
    if (!btn) return;

    const hasStudents = studentsAreLoaded();
    const hasSchema = schemaIsReady();
    const ready = hasStudents && hasSchema;

    btn.disabled = !ready;

    // Gestion du tooltip avec Bootstrap (si présent)
    if (wrap && window.bootstrap?.Tooltip) {
        const tip = bootstrap.Tooltip.getOrCreateInstance(wrap, {
            trigger: "hover focus",
            placement: "top",
            title: wrap.getAttribute("title") || "",
        });

        if (!ready) {
            let msg = "Préparez le calcul : ";
            if (!hasStudents && !hasSchema) {
                msg += "chargez un CSV d'élèves et appliquez un schéma de salle.";
            } else if (!hasStudents) {
                msg += "chargez un CSV d'élèves.";
            } else {
                msg += "appliquez un schéma de salle.";
            }

            // Bootstrap 5.3 : setContent si dispo, sinon fallback title+update
            if (typeof tip.setContent === "function") {
                tip.setContent({".tooltip-inner": msg});
            } else {
                wrap.setAttribute("title", msg);
                tip.update();
            }
            tip.enable();
            wrap.classList.remove("pe-none"); // clickable pour déclencher le tooltip si disabled
        } else {
            try {
                tip.hide();
            } catch {
            }
            tip.disable();
            wrap.classList.add("pe-none"); // évite de cliquer le wrapper quand actif
        }

        // Clic sur le wrapper : si disabled, montrer brièvement le tooltip (feedback user-friendly)
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
   Solveur : payload + start + polling + application
   ========================================================================== */

export function buildSolvePayload() {
    return {
        schema: state.schema,
        students: state.students.map((s) => ({
            id: s.id,
            name: s.name,
            first: s.first,
            last: s.last,
            gender: s.gender || null,
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

    // Sécurité : si non prêt, on ne lance pas (cas de course éventuel)
    if (!studentsAreLoaded() || !schemaIsReady()) {
        syncSolveButtonEnabled();
        return;
    }

    const dl = document.getElementById("solveDownloads");
    const dlPNG = document.getElementById("dlPNG");
    const dlPDF = document.getElementById("dlPDF");
    const dlSVG = document.getElementById("dlSVG");
    const dlTXT = document.getElementById("dlTXT");

    statusEl && (statusEl.textContent = "envoi...");
    if (dl) dl.classList.add("d-none");
    if (_pollTimer) {
        clearInterval(_pollTimer);
        _pollTimer = null;
    }

    const body = JSON.stringify(buildSolvePayload());

    try {
        const r = await fetch("/plandeclasse/solve/start", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body,
        });
        if (!r.ok) throw new Error("start failed");
        const {task_id} = await r.json();
        statusEl && (statusEl.textContent = "calcul en cours…");
        if (btn) btn.setAttribute("disabled", "true");

        _pollTimer = setInterval(async () => {
            try {
                const rr = await fetch(`/plandeclasse/solve/status/${task_id}`);
                const data = await rr.json();
                if (data.status && ["PENDING", "RECEIVED", "STARTED", "RETRY"].includes(data.status)) {
                    return;
                }
                clearInterval(_pollTimer);
                _pollTimer = null;
                if (btn) btn.removeAttribute("disabled");

                if (data.status === "SUCCESS") {
                    applyAssignment(data.assignment || {});
                    if (data.download && dlPNG && dlPDF && dlSVG && dlTXT && dl) {
                        dlPNG.href = data.download.png;
                        dlPDF.href = data.download.pdf;
                        dlSVG.href = data.download.svg;
                        dlTXT.href = data.download.txt;
                        dl.classList.remove("d-none");
                    }
                    statusEl && (statusEl.textContent = "terminé ✔");
                } else {
                    statusEl && (statusEl.textContent = `échec : ${data.error || "aucune solution"}`);
                }
            } catch (_e) {
                clearInterval(_pollTimer);
                _pollTimer = null;
                if (btn) btn.removeAttribute("disabled");
                statusEl && (statusEl.textContent = "erreur de polling");
            }
        }, 1000);
    } catch (_e) {
        statusEl && (statusEl.textContent = "erreur d’envoi");
    }
}

/** Applique une affectation renvoyée par le solveur. */
export function applyAssignment(assignmentObj /*: Record<string,number> */) {
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
