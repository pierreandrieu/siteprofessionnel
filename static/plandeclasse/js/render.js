// static/plandeclasse/js/render.js
"use strict";

/**
 * Module Render : gère le SVG de la salle, les cartes élèves et quelques refresh UI.
 * Dépend de l’état et des utils, mais pas des interactions.
 */

import {state} from "./state.js";
import {$, buildDisplayMaps, compareByLastThenFirst, norm} from "./utils.js";

/* ==========================================================================
   Dimensions & compaction
   ========================================================================== */

/**
 * Calcule des dimensions “compactes” pour l’UI.
 * On réduit légèrement hauteur/espacement quand il y a beaucoup de rangées,
 * tout en gardant une largeur raisonnable pour laisser respirer les noms.
 *
 * @param {number[][]} schema - matrice des capacités par rangée
 * @returns {{
 *   padX:number,padY:number,seatW:number,tableH:number,
 *   seatGap:number,colGap:number,rowGap:number,boardH:number
 * }}
 */
function computeDims(schema) {
    const rows = schema.length;

    // Base UI : valeurs confort
    const base = {
        padX: 16,
        padY: 12,
        seatW: 80,  // largeur d’un siège (UI)
        tableH: 30, // hauteur d’une table (UI)
        seatGap: 4, // séparateur fin entre sièges
        colGap: 16, // écart entre tables d’une même rangée
        rowGap: 22, // écart vertical entre rangées
        boardH: 18, // bandeau "tableau"
    };

    // Plus de rangées = compacter un peu en vertical (sans écraser).
    // Exemple : à partir de 5 rangées, on réduit de ~7% par rangée (min 72%).
    const vFactor = Math.max(0.72, 1 - Math.max(0, rows - 4) * 0.07);

    // En horizontal, réduction très légère après 6 rangées.
    const hFactor = Math.max(0.88, 1 - Math.max(0, rows - 6) * 0.02);

    return {
        padX: base.padX,
        padY: base.padY,
        seatW: Math.round(base.seatW * hFactor),         // ex: 80 → ~74
        tableH: Math.round(base.tableH * vFactor),       // ex: 46 → ~36 avec bcp de rangées
        seatGap: base.seatGap,
        colGap: base.colGap,
        rowGap: Math.round(base.rowGap * vFactor),       // ex: 22 → ~16
        boardH: base.boardH,
    };
}

/* ==========================================================================
   UI : boutons & texte
   ========================================================================== */

/**
 * Met à jour l'état des actions liées au siège sélectionné :
 * - Bouton « le siège doit rester vide » :
 *     • activé uniquement si un siège VIDE est sélectionné ;
 *     • libellé bascule en « rendre le siège disponible » si ce siège est déjà interdit.
 *     • désactivé s’il n’y a pas de sélection ou si le siège est occupé.
 * - Bouton « retirer l’élève » :
 *     • activé uniquement si un siège OCCUPÉ est sélectionné.
 */
export function updateBanButtonLabel() {
    // Actions concernées
    const btnBan = document.getElementById("btnToggleBan");
    const btnUnassign = document.getElementById("btnUnassign");

    // Sélection courante
    const k = state.selection.seatKey;
    const hasSelection = !!k;
    const isOccupied = hasSelection ? state.placements.has(k) : false;

    // --- Bouton « bannir le siège » ---
    if (btnBan) {
        if (!hasSelection || isOccupied) {
            // Pas de siège / siège occupé → pas d'interdiction directement possible
            btnBan.disabled = true;
            btnBan.textContent = "le siège doit rester vide";
        } else {
            // Siège vide sélectionné → on (dé)bloque le bannissement
            const isForbidden = state.forbidden.has(k);
            btnBan.disabled = false;
            btnBan.textContent = isForbidden
                ? "rendre le siège disponible"
                : "le siège doit rester vide";
        }
    }

    // --- Bouton « retirer l’élève » ---
    if (btnUnassign) {
        // Actif seulement lorsqu'un siège occupé est sélectionné
        btnUnassign.disabled = !isOccupied;
    }
}


/**
 * Ajoute un <text>/<tspan> et ajuste la police pour tenir dans le rectangle.
 * @param {SVGSVGElement} svg
 * @param {number} cx
 * @param {number} cy
 * @param {number} seatW
 * @param {number} seatH
 * @param {string} text
 * @param {string} seatKey
 */
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

    // Ellipse ultime si trop large
    const bbox2 = textEl.getBBox();
    if (bbox2.width > maxWidth && tspans.length) {
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

/* ==========================================================================
   Rendu du SVG salle
   ========================================================================== */

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

    // Dimensions (compactes) calculées selon le schéma
    const {padX, padY, seatW, tableH, seatGap, colGap, rowGap, boardH} = computeDims(state.schema);

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

    // Y de départ pour chaque rangée
    const rowOriginsY = [];
    let curY = boardY + boardH + 10;
    for (let y = 0; y < rows; y++) {
        rowOriginsY.push(curY);
        curY += tableH + rowGap;
    }

    const totalWidth = padX * 2 + maxRowW;
    const totalHeight = (rowOriginsY.at(-1) || (padY + 32)) + tableH + padY;

    svg.setAttribute("viewBox", `0 0 ${totalWidth} ${totalHeight}`);
    svg.style.minWidth = totalWidth + "px";
    // Laisse le conteneur .room-scroll gérer la hauteur; on évite de forcer ici.
    svg.style.minHeight = Math.min(800, totalHeight) + "px";

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
    boardLabel.textContent = "TABLEAU";
    svg.appendChild(boardLabel);

    const {firstMap, lastMap, bothMap} = buildDisplayMaps(state.students);

    for (let y = 0; y < rows; y++) {
        const caps = state.schema[y];
        const tablesW = caps.reduce((sum, cap) => sum + cap * seatW + (cap - 1) * seatGap, 0);
        const between = (caps.length - 1) * colGap;
        const rowW = tablesW + between;
        let ox = padX + (maxRowW - rowW) / 2;
        const oy = rowOriginsY[y];

        for (let x = 0; x < caps.length; x++) {
            const cap = caps[x];
            const tableWidth = cap * seatW + (cap - 1) * seatGap;

            const rect = document.createElementNS(ns, "rect");
            rect.setAttribute("x", String(ox));
            rect.setAttribute("y", String(oy));
            rect.setAttribute("width", String(tableWidth));
            rect.setAttribute("height", String(tableH));
            rect.setAttribute("rx", "10");
            rect.setAttribute("class", "table-rect");
            svg.appendChild(rect);

            for (let s = 0; s < cap; s++) {
                const sx = ox + s * (seatW + seatGap);
                const sy = oy;
                const seatKey = `${x},${y},${s}`;
                const occupant = state.placements.get(seatKey) ?? null;
                const isForbidden = state.forbidden.has(seatKey);
                const isSelectedSeat = state.selection.seatKey === seatKey;

                const seatRect = document.createElementNS(ns, "rect");
                seatRect.setAttribute("x", String(sx));
                seatRect.setAttribute("y", String(sy));
                seatRect.setAttribute("width", String(seatW));
                seatRect.setAttribute("height", String(tableH));
                seatRect.setAttribute("data-seat", seatKey);
                seatRect.setAttribute(
                    "class",
                    "seat-cell " +
                    (isForbidden ? "seat-forbidden " : occupant != null ? "seat-occupied " : "seat-free ") +
                    (isSelectedSeat ? "seat-selected" : "")
                );

                if (isForbidden) {
                    seatRect.setAttribute("fill", "url(#forbidPattern)");
                    seatRect.setAttribute("stroke-width", "2");
                } else {
                    seatRect.removeAttribute("fill");
                    seatRect.removeAttribute("stroke-width");
                }
                svg.appendChild(seatRect);

                // Croisillon d’overlay sur les sièges interdits
                if (isForbidden) {
                    const cross = document.createElementNS(ns, "path");
                    const pad = 8;
                    const x1 = sx + pad, y1 = sy + pad;
                    const x2 = sx + seatW - pad, y2 = sy + tableH - pad;
                    const x3 = sx + pad, y3 = sy + tableH - pad;
                    const x4 = sx + seatW - pad, y4 = sy + pad;
                    cross.setAttribute("d", `M${x1},${y1} L${x2},${y2} M${x3},${y3} L${x4},${y4}`);
                    cross.setAttribute("class", "seat-forbidden-cross");
                    svg.appendChild(cross);
                }

                // Séparateur fin entre sièges
                if (s < cap - 1) {
                    const divider = document.createElementNS(ns, "rect");
                    divider.setAttribute("x", String(sx + seatW + seatGap / 2 - 0.5));
                    divider.setAttribute("y", String(sy + 6));
                    divider.setAttribute("width", "1");
                    divider.setAttribute("height", String(tableH - 12));
                    divider.setAttribute("class", "seat-divider");
                    svg.appendChild(divider);
                }

                // Label prénom/nom
                if (occupant != null) {
                    const nm =
                        state.nameView === "first"
                            ? firstMap.get(occupant) || ""
                            : state.nameView === "last"
                                ? lastMap.get(occupant) || ""
                                : bothMap.get(occupant) || "";
                    const cx = sx + seatW / 2;
                    const cy = sy + tableH / 2;
                    appendSeatLabelFitted(svg, cx, cy, seatW, tableH, nm, seatKey);
                }
            }

            ox += tableWidth + colGap;
        }
    }
}

/* ==========================================================================
   Rendu de la liste élèves
   ========================================================================== */

/** Rendu liste élèves (non placés/placés) + gestion de la sélection d’élève. */
export function renderStudents() {
    const unplaced = /** @type {HTMLElement|null} */ ($("#studentsUnplaced"));
    const placed = /** @type {HTMLElement|null} */ ($("#studentsPlaced"));
    const search = /** @type {HTMLInputElement|null} */ ($("#studentSearch"));
    if (!unplaced || !placed) return;

    const q = norm(search?.value || "");
    unplaced.innerHTML = "";
    placed.innerHTML = "";

// Tri : NOM puis prénom (collator FR)
    const items = [...state.students].sort(compareByLastThenFirst);

    for (const st of items) {
        // Recherche tolérante : nom, prénom, "prénom nom" ou "nom prénom"
        const f = norm(st.first);
        const l = norm(st.last);
        const fl = (f + " " + l).trim();
        const lf = (l + " " + f).trim();

        if (q && !(fl.includes(q) || lf.includes(q) || f.includes(q) || l.includes(q))) {
            continue;
        }

        const card = document.createElement("div");
        card.className = "student" + (state.selection.studentId === st.id ? " selected" : "");
        card.dataset.sid = String(st.id);
        card.innerHTML = `
    <div class="d-flex flex-column">
      <span class="student-name">${st.first}</span>
      <span class="student-sub">${st.last}</span>
    </div>
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
