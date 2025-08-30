// static/plandeclasse/js/render.js
"use strict";

/**
 * Module Render : gère le SVG de la salle, les cartes élèves et quelques refresh UI.
 * Dépend de l’état et des utils, mais pas des interactions.
 */

import {state} from "./state.js";
import {$, buildDisplayMaps} from "./utils.js";

/** Met à jour le libellé/disponibilité du bouton « bannir le siège » selon la sélection. */
export function updateBanButtonLabel() {
    const btn = document.getElementById("btnToggleBan");
    if (!btn) return;

    const k = state.selection.seatKey;
    const occupied = k ? state.placements.has(k) : false;

    if (!k || occupied) {
        btn.disabled = true;
        btn.textContent = "le siège doit rester vide";
        return;
    }
    const forbidden = state.forbidden.has(k);
    btn.disabled = false;
    btn.textContent = forbidden ? "rendre le siège disponible" : "le siège doit rester vide";
}

/** Ajoute un <text>/<tspan> et ajuste la police pour tenir dans le rectangle. */
function appendSeatLabelFitted(svg, cx, cy, seatW, seatH, text, seatKey) {
    const lines = String(text || "").split("\n");
    const ns = "http://www.w3.org/2000/svg";

    const textEl = document.createElementNS(ns, "text");
    textEl.setAttribute("text-anchor", "middle");
    textEl.setAttribute("class", "seat-name");
    textEl.setAttribute("data-seat", seatKey);
    svg.appendChild(textEl);

    const tspans = [];
    for (let i = 0; i < lines.length; i++) {
        const tspan = document.createElementNS(ns, "tspan");
        tspan.setAttribute("x", String(cx));
        tspan.textContent = lines[i];
        tspans.push(tspan);
        textEl.appendChild(tspan);
    }

    const paddingX = 8, paddingY = 6;
    const maxWidth = seatW - paddingX * 2;
    const maxHeight = seatH - paddingY * 2;

    let size = 22;
    const minSize = 9;

    while (size >= minSize) {
        textEl.setAttribute("style", `font-size:${size}px;`);
        const lineHeight = size * 1.1;
        if (tspans.length === 1) {
            textEl.setAttribute("x", String(cx));
            textEl.setAttribute("y", String(cy));
            tspans[0].setAttribute("dy", "0");
        } else {
            const totalH = lineHeight * 2;
            const yTop = cy - totalH / 2 + lineHeight * 0.8;
            textEl.setAttribute("y", String(yTop));
            tspans[0].setAttribute("dy", "0");
            tspans[1].setAttribute("x", String(cx));
            tspans[1].setAttribute("dy", String(lineHeight));
        }

        const bbox = textEl.getBBox();
        if (bbox.width <= maxWidth && bbox.height <= maxHeight) break;
        size -= 1;
    }

    const bbox = textEl.getBBox();
    if (bbox.width > maxWidth && tspans.length) {
        const last = tspans[tspans.length - 1];
        const original = last.textContent || "";
        if (original.length > 3) {
            let cut = original.length - 1;
            while (cut > 3) {
                last.textContent = original.slice(0, cut) + "…";
                if (textEl.getBBox().width <= maxWidth) break;
                cut -= 1;
            }
        }
    }
}

/** Rendu du SVG de la salle (tables, sièges, bordures, hatch des interdits, labels). */
export function renderRoom() {
    const svg = /** @type {SVGSVGElement|null} */ ($("#roomCanvas"));
    if (!svg) return;
    svg.innerHTML = "";

    const rows = state.schema.length;
    if (rows === 0) {
        svg.setAttribute("viewBox", "0 0 600 200");
        return;
    }

    // Dimensions
    const padX = 20, padY = 16;
    const seatW = 90, tableH = 70;
    const seatGap = 6, colGap = 20, rowGap = 38;

    // Largeurs de rangée (centrage)
    const rowWidths = state.schema.map((caps) => {
        const tablesW = caps.reduce((sum, cap) => sum + cap * seatW + (cap - 1) * seatGap, 0);
        const between = (caps.length - 1) * colGap;
        return tablesW + between;
    });
    const maxRowW = Math.max(...rowWidths);
    const boardW = Math.max(maxRowW, 600);

    const boardX = padX + (maxRowW - boardW) / 2;
    const boardY = padY;
    const boardH = 16;

    // Y de départ pour chaque rangée
    const rowOriginsY = [];
    let curY = boardY + boardH + 14;
    for (let y = 0; y < rows; y++) {
        rowOriginsY.push(curY);
        curY += tableH + rowGap;
    }

    const totalWidth = padX * 2 + maxRowW;
    const totalHeight = (rowOriginsY.at(-1) || (padY + 32)) + tableH + padY;

    svg.setAttribute("viewBox", `0 0 ${totalWidth} ${totalHeight}`);
    svg.style.minWidth = totalWidth + "px";
    svg.style.minHeight = Math.min(900, totalHeight) + "px";

    const ns = "http://www.w3.org/2000/svg";

    // motif hatch pour sièges interdits
    const defs = document.createElementNS(ns, "defs");
    const pattern = document.createElementNS(ns, "pattern");
    pattern.setAttribute("id", "forbidPattern");
    pattern.setAttribute("patternUnits", "userSpaceOnUse");
    pattern.setAttribute("width", "8");
    pattern.setAttribute("height", "8");

    const pBg = document.createElementNS(ns, "rect");
    pBg.setAttribute("width", "8");
    pBg.setAttribute("height", "8");
    pBg.setAttribute("fill", "#f3f4f6");
    pattern.appendChild(pBg);

    const pLines = document.createElementNS(ns, "path");
    pLines.setAttribute("d", "M0,8 l8,-8 M-2,2 l4,-4 M6,10 l4,-4");
    pLines.setAttribute("stroke", "#cbd5e1");
    pLines.setAttribute("stroke-width", "1");
    pattern.appendChild(pLines);

    defs.appendChild(pattern);
    svg.appendChild(defs);

    // Tableau
    const board = document.createElementNS(ns, "rect");
    board.setAttribute("x", String(boardX));
    board.setAttribute("y", String(boardY));
    board.setAttribute("width", String(boardW));
    board.setAttribute("height", String(boardH));
    board.setAttribute("class", "board-rect");
    svg.appendChild(board);

    const boardLabel = document.createElementNS(ns, "text");
    boardLabel.setAttribute("x", String(boardX + boardW / 2));
    boardLabel.setAttribute("y", String(boardY - 4));
    boardLabel.setAttribute("text-anchor", "middle");
    boardLabel.setAttribute("class", "board-label");
    boardLabel.textContent = "tableau";
    svg.appendChild(boardLabel);

    const {firstMap, lastMap, bothMap} = buildDisplayMaps(state.students);

    for (let y = 0; y < rows; y++) {
        const caps = state.schema[y];
        const tablesW = caps.reduce((sum, cap) => sum + cap * 90 + (cap - 1) * 6, 0);
        const between = (caps.length - 1) * 20;
        const rowW = tablesW + between;
        let ox = padX + (maxRowW - rowW) / 2;
        const oy = rowOriginsY[y];

        for (let x = 0; x < caps.length; x++) {
            const cap = caps[x];
            const tableWidth = cap * 90 + (cap - 1) * 6;

            const rect = document.createElementNS(ns, "rect");
            rect.setAttribute("x", String(ox));
            rect.setAttribute("y", String(oy));
            rect.setAttribute("width", String(tableWidth));
            rect.setAttribute("height", String(tableH));
            rect.setAttribute("rx", "10");
            rect.setAttribute("class", "table-rect");
            svg.appendChild(rect);

            for (let s = 0; s < cap; s++) {
                const sx = ox + s * (90 + 6);
                const sy = oy;
                const seatKey = `${x},${y},${s}`;
                const occupant = state.placements.get(seatKey) ?? null;
                const isForbidden = state.forbidden.has(seatKey);
                const isSelectedSeat = state.selection.seatKey === seatKey;

                const seatRect = document.createElementNS(ns, "rect");
                seatRect.setAttribute("x", String(sx));
                seatRect.setAttribute("y", String(sy));
                seatRect.setAttribute("width", "90");
                seatRect.setAttribute("height", String(tableH));
                seatRect.setAttribute("data-seat", seatKey);
                seatRect.setAttribute(
                    "class",
                    "seat-cell " +
                    (isForbidden ? "seat-forbidden " : occupant != null ? "seat-occupied " : "seat-free ") +
                    (isSelectedSeat ? "seat-selected" : ""),
                );

                if (isForbidden) {
                    seatRect.setAttribute("fill", "url(#forbidPattern)");
                    seatRect.setAttribute("stroke-width", "2");
                } else {
                    seatRect.removeAttribute("fill");
                    seatRect.removeAttribute("stroke-width");
                }
                svg.appendChild(seatRect);

                if (isForbidden) {
                    const cross = document.createElementNS(ns, "path");
                    const pad = 8;
                    const x1 = sx + pad, y1 = sy + pad;
                    const x2 = sx + 90 - pad, y2 = sy + tableH - pad;
                    const x3 = sx + pad, y3 = sy + tableH - pad;
                    const x4 = sx + 90 - pad, y4 = sy + pad;
                    cross.setAttribute("d", `M${x1},${y1} L${x2},${y2} M${x3},${y3} L${x4},${y4}`);
                    cross.setAttribute("class", "seat-forbidden-cross");
                    svg.appendChild(cross);
                }

                if (s < cap - 1) {
                    const divider = document.createElementNS(ns, "rect");
                    divider.setAttribute("x", String(sx + 90 + 6 / 2 - 0.5));
                    divider.setAttribute("y", String(sy + 6));
                    divider.setAttribute("width", "1");
                    divider.setAttribute("height", String(tableH - 12));
                    divider.setAttribute("class", "seat-divider");
                    svg.appendChild(divider);
                }

                if (occupant != null) {
                    const nm =
                        state.nameView === "first"
                            ? firstMap.get(occupant) || ""
                            : state.nameView === "last"
                                ? lastMap.get(occupant) || ""
                                : bothMap.get(occupant) || "";
                    const cx = sx + 90 / 2;
                    const cy = sy + tableH / 2;
                    appendSeatLabelFitted(svg, cx, cy, 90, tableH, nm, seatKey);
                }
            }
            ox += tableWidth + 20;
        }
    }
}

/** Rendu liste élèves (non placés/placés) + sélection d’élève. */
export function renderStudents() {
    const unplaced = /** @type {HTMLElement|null} */ ($("#studentsUnplaced"));
    const placed = /** @type {HTMLElement|null} */ ($("#studentsPlaced"));
    const search = /** @type {HTMLInputElement|null} */ ($("#studentSearch"));
    if (!unplaced || !placed) return;

    const q = (search?.value || "").toLowerCase();
    unplaced.innerHTML = "";
    placed.innerHTML = "";

    const items = state.students.slice().sort((a, b) => {
        const aKey = (a.first + " " + a.last).toLowerCase();
        const bKey = (b.first + " " + b.last).toLowerCase();
        return aKey.localeCompare(bKey);
    });

    for (const st of items) {
        if (q && !(st.first + " " + st.last).toLowerCase().includes(q)) continue;
        const card = document.createElement("div");
        card.className = "student" + (state.selection.studentId === st.id ? " selected" : "");
        card.dataset.sid = String(st.id);
        card.innerHTML = `
      <div class="d-flex flex-column">
        <span class="student-name">${st.first}</span>
        <span class="student-sub">${st.last}</span>
      </div>
      <span class="badge text-bg-light">${state.placedByStudent.has(st.id) ? "placé" : "libre"}</span>
    `;
        card.addEventListener("click", () => {
            if (state.selection.studentId === st.id) {
                state.selection.studentId = null;
                state.selection.seatKey = null;
            } else {
                state.selection.studentId = st.id;
                state.selection.seatKey = state.placedByStudent.get(st.id) || null;
            }
            renderStudents();
            renderRoom();
            updateBanButtonLabel();
        });

        if (state.placedByStudent.has(st.id)) placed.appendChild(card);
        else unplaced.appendChild(card);
    }
}
