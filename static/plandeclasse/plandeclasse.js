"use strict";

/**
 * Classroom planner – UI only (RAM), no framework.
 * - Name labels auto-fit to seat rectangle.
 * - Clicking an empty seat only (de)selects it; banning is button-driven.
 * - Auto-clear selection after placing or swapping.
 * - Forbidden seats have a hatched fill and distinct border.
 * - Thin dividers between adjacent seats on the same table.
 */

/* ========= GLOBAL STATE ========= */
const state = {
    students: [], // {id, name, gender|null, first, last}
    selection: {studentId: null, seatKey: null}, // "x,y,s"
    schema: [], // [[2,3,2], ...]
    forbidden: new Set(), // Set<"x,y,s">
    placements: new Map(), // Map<seatKey, studentId>
    placedByStudent: new Map(), // Map<studentId, seatKey>
    options: {prefer_mixage: true, prefer_alone: true},
    nameView: "first", // "first" | "last" | "both"
    constraints: [], // {type, a?, b?, x?, y?, s?, k?, d?, human, key?}
};

/* ========= HELPERS ========= */
const $ = (sel) => document.querySelector(sel);
const keyOf = (x, y, s) => `${x},${y},${s}`;

/** Split name by rule: initial run of ALL-CAPS tokens (with spaces/hyphens) = last name; remainder = first name(s). */
function splitName(full) {
    const cleaned = (full || "").trim().replace(/\s+/g, " ");
    if (!cleaned) return {first: "", last: ""};
    const tokens = cleaned.split(" ");
    const isUpperToken = (tok) => {
        const core = tok.replace(/[-'’]/g, "");
        const hasLetters = /[A-ZÀ-ÖØ-Þ]/.test(core);
        return hasLetters && core === core.toLocaleUpperCase("fr-FR");
    };
    let i = 0;
    while (i < tokens.length && isUpperToken(tokens[i])) i++;
    if (i === 0) return {first: cleaned, last: ""};
    const last = tokens.slice(0, i).join(" ");
    const first = tokens.slice(i).join(" ").trim();
    return {first, last};
}

function disambiguate(list, primaryKey, secondaryKey, format) {
    const groups = new Map();
    for (const s of list) {
        const k = primaryKey(s);
        if (!groups.has(k)) groups.set(k, []);
        groups.get(k).push(s);
    }
    const result = new Map();
    for (const [k, arr] of groups.entries()) {
        if (arr.length === 1) {
            result.set(arr[0].id, k);
        } else {
            const used = new Set();
            for (const s of arr) {
                const sec = secondaryKey(s);
                let i = 1;
                while (true) {
                    const ext = sec.slice(0, i);
                    const cand = format(k, ext);
                    if (!used.has(cand)) {
                        used.add(cand);
                        result.set(s.id, cand);
                        break;
                    }
                    i += 1;
                }
            }
        }
    }
    return result;
}

function buildDisplayMaps() {
    const firstMap = disambiguate(
        state.students,
        (s) => s.first,
        (s) => s.last,
        (p, ext) => (ext ? `${p} ${ext}.` : p),
    );
    const lastMap = disambiguate(
        state.students,
        (s) => s.last || s.first,
        (s) => s.first,
        (p, ext) => (ext ? `${p} ${ext}.` : p),
    );
    const bothMap = new Map(state.students.map((s) => [s.id, `${s.first}\n${s.last}`.trim()]));
    return {firstMap, lastMap, bothMap};
}

function computeMaxManhattan(schema) {
    const rows = schema.length;
    if (!rows) return 0;
    const maxCols = Math.max(...schema.map((r) => r.length));
    return (rows - 1) + (maxCols - 1);
}

/** Update the “ban seat” button label and enabled state according to current selection. */
function updateBanButtonLabel() {
    const btn = document.getElementById("btnToggleBan");
    if (!btn) return;

    const k = state.selection.seatKey;
    const occupied = k ? state.placements.has(k) : false;

    // No seat selected OR seat occupied → disable
    if (!k || occupied) {
        btn.disabled = true;
        btn.textContent = "le siège doit rester vide";
        return;
    }

    const forbidden = state.forbidden.has(k);
    btn.disabled = false;
    btn.textContent = forbidden ? "rendre le siège disponible" : "le siège doit rester vide";
}

/* ========= CSV ========= */
function parseCSV(text) {
    const lines = text.split(/\r?\n/).filter((l) => l.trim() !== "");
    if (!lines.length) return [];
    const sep = lines[0].includes(";") ? ";" : ",";
    const header = lines[0].split(sep).map((h) => h.trim().toLowerCase());
    let idxName = header.findIndex((h) => ["nom", "élève", "eleve", "name"].includes(h));
    if (idxName === -1) idxName = 0;

    const rows = [];
    for (let i = 1; i < lines.length; i++) {
        const cols = lines[i].split(sep);
        const raw = (cols[idxName] || "").replace(/<[^>]+>/g, "").replace(/"/g, "").trim();
        if (raw) rows.push({name: raw, gender: null});
    }
    return rows;
}

/* ========= SVG RENDERING ========= */

/** Append a <text> (with <tspan> if 2 lines) and shrink font until it fits W×H. */
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

    const paddingX = 8;
    const paddingY = 6;
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

    // Last-resort ellipsis on the last line if still too wide (rare)
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

function renderRoom() {
    const svg = $("#roomCanvas");
    if (!svg) return;
    svg.innerHTML = "";

    const rows = state.schema.length;
    if (rows === 0) {
        svg.setAttribute("viewBox", "0 0 600 200");
        return;
    }

    // Dimensions
    const padX = 20;
    const padY = 16;
    const seatW = 90;
    const tableH = 70;
    const seatGap = 6;   // horizontal gap between seats (we draw a divider inside)
    const colGap = 20;   // gap between tables (columns)
    const rowGap = 38;   // gap between rows

    // Row widths (for centering under board)
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

    // Y of each row
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

    // --- defs: diagonal hatch pattern for forbidden seats ---
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

    // Board
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

    const {firstMap, lastMap, bothMap} = buildDisplayMaps();

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
                const seatKey = keyOf(x, y, s);
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
                    (isSelectedSeat ? "seat-selected" : ""),
                );

                // Apply hatched fill for forbidden seats
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

                // Thin divider between this seat and the next (inside the seatGap)
                if (s < cap - 1) {
                    const divider = document.createElementNS(ns, "rect");
                    divider.setAttribute("x", String(sx + seatW + seatGap / 2 - 0.5));
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
                    const cx = sx + seatW / 2;
                    const cy = sy + tableH / 2;
                    appendSeatLabelFitted(svg, cx, cy, seatW, tableH, nm, seatKey);
                }
            }
            ox += tableWidth + colGap;
        }
    }
}

/* ========= INTERACTIONS ========= */
function seatClick(seatKey) {
    const occupant = state.placements.get(seatKey) ?? null;
    const selSid = state.selection.studentId;

    if (selSid != null) {
        // A student is selected → place / permute / toggle on own seat
        if (state.forbidden.has(seatKey)) return;

        const prevSeat = state.placedByStudent.get(selSid) || null;

        if (occupant == null) {
            // Move to empty seat
            if (prevSeat) state.placements.delete(prevSeat);
            state.placements.set(seatKey, selSid);
            state.placedByStudent.set(selSid, seatKey);
            // Auto-clear selection after placing
            state.selection.studentId = null;
            state.selection.seatKey = null;
        } else if (occupant === selSid) {
            // Clicked own seat → toggle (de)selection
            if (state.selection.seatKey === seatKey) {
                state.selection.studentId = null;
                state.selection.seatKey = null;
            } else {
                state.selection.seatKey = seatKey;
            }
        } else {
            // Swap with another occupant
            if (prevSeat) {
                state.placements.set(prevSeat, occupant);
                state.placedByStudent.set(occupant, prevSeat);
            } else {
                state.placedByStudent.delete(occupant);
                state.placements.delete(seatKey);
            }
            state.placements.set(seatKey, selSid);
            state.placedByStudent.set(selSid, seatKey);
            // Auto-clear selection after swap
            state.selection.studentId = null;
            state.selection.seatKey = null;
        }
        renderRoom();
        renderStudents();
        updateBanButtonLabel();
        return;
    }

    // No student selected
    if (occupant != null) {
        // Select the occupant (and its seat)
        state.selection.studentId = occupant;
        state.selection.seatKey = seatKey;
    } else {
        // FREE seat: only (de)select it; DO NOT toggle forbidden here
        state.selection.seatKey = state.selection.seatKey === seatKey ? null : seatKey;
        state.selection.studentId = null;
    }

    renderStudents();
    renderRoom();
    updateBanButtonLabel();
}

function onCanvasClick(ev) {
    const target = ev.target;
    if (!(target instanceof SVGElement)) return;
    const seatKey = target.getAttribute("data-seat");
    if (seatKey) seatClick(seatKey);
}

function toggleSelectedSeatBan() {
    const k = state.selection.seatKey;
    if (!k) return;
    if (state.placements.has(k)) {
        alert("place occupée : retirez d'abord l'élève ou permutez.");
        return;
    }
    if (state.forbidden.has(k)) {
        state.forbidden.delete(k);
        const idx = state.constraints.findIndex((c) => c.type === "forbid_seat" && keyOf(c.x, c.y, c.s) === k);
        if (idx >= 0) state.constraints.splice(idx, 1);
    } else {
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
    // Exit “ban mode”: clear selection
    state.selection.seatKey = null;
    state.selection.studentId = null;

    renderRoom();
    renderConstraints();
    updateBanButtonLabel();
}

function unassignSelected() {
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

/* ========= SCHEMA ========= */
function applySchema(rows, tablesPerRow, capacitiesStr) {
    const caps = capacitiesStr
        .split(/[,\s]+/)
        .map((s) => Number(s.trim()))
        .filter((n) => Number.isFinite(n) && n > 0);

    if (caps.length !== tablesPerRow) {
        alert(`le nombre de capacités (${caps.length}) doit = tables / rangée (${tablesPerRow}).`);
        return;
    }

    const newSchema = Array.from({length: rows}, () => caps.slice());
    const newPlacements = new Map();
    const newPlacedByStudent = new Map();

    for (const [seatKey, sid] of state.placements.entries()) {
        const [x, y, s] = seatKey.split(",").map(Number);
        if (y < newSchema.length && x < newSchema[y].length && s < newSchema[y][x]) {
            newPlacements.set(seatKey, sid);
            newPlacedByStudent.set(sid, seatKey);
        }
    }

    state.schema = newSchema;
    state.placements = newPlacements;
    state.placedByStudent = newPlacedByStudent;

    // Keep only valid forbidden seats and sync constraints
    const newForbidden = new Set();
    const newForbidConstraints = [];
    for (const k of state.forbidden) {
        const [x, y, s] = k.split(",").map(Number);
        if (y < newSchema.length && x < newSchema[y].length && s < newSchema[y][x]) {
            newForbidden.add(k);
            newForbidConstraints.push({
                type: "forbid_seat",
                x,
                y,
                s,
                human: `siège (x=${x}, y=${y}, s=${s}) doit rester vide`,
                key: k,
            });
        }
    }
    state.forbidden = newForbidden;
    state.constraints = state.constraints.filter((c) => c.type !== "forbid_seat").concat(newForbidConstraints);

    renderRoom();
    renderStudents();
    renderConstraints();
    updateBanButtonLabel();
}

/* ========= STUDENTS LIST ========= */
function renderStudents() {
    const unplaced = $("#studentsUnplaced");
    const placed = $("#studentsPlaced");
    const search = $("#studentSearch");
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

/* ========= CONSTRAINTS (UI ONLY) ========= */
function refreshConstraintSelectors() {
    const a = $("#cstStudentA");
    const b = $("#cstStudentB");
    if (!a || !b) return;
    const fill = (sel) => {
        sel.innerHTML = "";
        for (const st of state.students.slice().sort((x, y) => (x.first + x.last).localeCompare(y.first + y.last))) {
            const opt = document.createElement("option");
            opt.value = String(st.id);
            opt.textContent = `${st.first} ${st.last}`.trim();
            sel.appendChild(opt);
        }
    };
    fill(a);
    fill(b);
}

function onConstraintTypeChange() {
    const t = /** @type {HTMLSelectElement} */ ($("#constraintType")).value;
    const bWrap = $("#cstStudentBWrap");
    const pWrap = $("#cstParamWrap");
    const pLabel = $("#cstParamLabel");
    const pHelp = $("#cstParamHelp");
    const pInput = /** @type {HTMLInputElement} */ ($("#cstParam"));

    const needsB = ["same_table", "far_apart"].includes(t);
    const needsK = ["front_rows", "back_rows"].includes(t);
    const needsD = t === "far_apart";

    bWrap.hidden = !needsB;
    pWrap.hidden = !(needsK || needsD);

    if (needsK) {
        pLabel.textContent = "k (nombre de rangées)";
        pInput.placeholder = "k";
        pInput.min = "1";
        pHelp.textContent = "";
    } else if (needsD) {
        const maxD = computeMaxManhattan(state.schema);
        pLabel.textContent = "distance d (Manhattan)";
        pInput.placeholder = "d";
        pInput.min = "1";
        pInput.max = String(Math.max(1, maxD));
        pHelp.textContent = maxD > 0 ? `valeur ≤ ${maxD} selon la salle` : "";
    } else {
        pLabel.textContent = "paramètre";
        pInput.placeholder = "";
        pHelp.textContent = "";
    }
}

function addConstraint() {
    const t = /** @type {HTMLSelectElement} */ ($("#constraintType")).value;
    const a = Number(/** @type {HTMLSelectElement} */ ($("#cstStudentA")).value);
    const bSel = /** @type {HTMLSelectElement} */ ($("#cstStudentB"));
    const b = bSel && !$("#cstStudentBWrap").hidden ? Number(bSel.value) : null;
    const pInput = /** @type {HTMLInputElement} */ ($("#cstParam"));
    const pVal = pInput.value ? Number(pInput.value) : null;

    const nameOf = (sid) => {
        const s = state.students.find((x) => x.id === sid);
        return s ? `${s.first} ${s.last}`.trim() : `#${sid}`;
    };

    let human = "";
    const payload = {type: t};
    if (t === "front_rows") {
        payload.a = a;
        payload.k = pVal;
        human = `${nameOf(a)} doit être dans les premières rangées (k=${pVal ?? "?"})`;
    } else if (t === "back_rows") {
        payload.a = a;
        payload.k = pVal;
        human = `${nameOf(a)} doit être dans les dernières rangées (k=${pVal ?? "?"})`;
    } else if (t === "solo_table") {
        payload.a = a;
        human = `${nameOf(a)} ne doit pas avoir de voisins (seul à la table)`;
    } else if (t === "empty_neighbor") {
        payload.a = a;
        human = `${nameOf(a)} ne doit pas avoir de voisins (au moins un siège vide à côté)`;
    } else if (t === "same_table") {
        payload.a = a;
        payload.b = b;
        human = `${nameOf(a)} doit être à la même table que ${nameOf(b)}`;
    } else if (t === "far_apart") {
        const maxD = computeMaxManhattan(state.schema);
        const d = Math.min(Math.max(1, pVal || 1), Math.max(1, maxD));
        payload.a = a;
        payload.b = b;
        payload.d = d;
        human = `${nameOf(a)} être éloigné d’une distance d’au moins d=${d} de ${nameOf(b)}`;
    }

    payload.human = human;
    state.constraints.push(payload);
    renderConstraints();
}

function cancelConstraintForm() {
    $("#cstStudentA").selectedIndex = 0;
    $("#cstStudentB").selectedIndex = 0;
    $("#constraintType").selectedIndex = 0;
    $("#cstParam").value = "";
    onConstraintTypeChange();
}

function renderConstraints() {
    const root = $("#constraintsList");
    if (!root) return;
    root.innerHTML = "";
    for (const c of state.constraints) {
        const item = document.createElement("div");
        item.className = "constraint-pill me-2 mb-2 d-inline-flex align-items-center gap-2";
        item.textContent = c.human || JSON.stringify(c);

        const del = document.createElement("button");
        del.className = "btn btn-sm btn-outline-danger";
        del.textContent = "✕";
        del.addEventListener("click", () => {
            const idx = state.constraints.indexOf(c);
            if (idx >= 0) {
                if (c.type === "forbid_seat" && typeof c.x === "number") {
                    state.forbidden.delete(keyOf(c.x, c.y, c.s));
                    renderRoom();
                }
                state.constraints.splice(idx, 1);
                renderConstraints();
                updateBanButtonLabel();
            }
        });

        item.appendChild(del);
        root.appendChild(item);
    }
}

/* ========= INIT ========= */
function init() {
    // Attach one delegated click listener on the SVG
    const canvas = document.getElementById("roomCanvas");
    if (canvas) canvas.addEventListener("click", onCanvasClick);

    // CSV
    const csvInput = $("#csvInput");
    if (csvInput) {
        csvInput.addEventListener("change", async (ev) => {
            const f = ev.target.files && ev.target.files[0];
            if (!f) return;
            const txt = await f.text();
            const rows = parseCSV(txt);
            state.students = rows.map((r, idx) => {
                const {first, last} = splitName(r.name);
                return {id: idx, name: r.name, gender: r.gender || null, first, last};
            });
            state.selection.studentId = null;
            state.selection.seatKey = null;
            refreshConstraintSelectors();
            renderStudents();
            renderRoom();
            updateBanButtonLabel();
        });
    }

    // Schema
    $("#btnBuildRoom")?.addEventListener("click", () => {
        const rows = Number($("#rowsCount").value);
        const tpr = Number($("#tablesPerRow").value);
        const caps = $("#rowCapacities").value;
        if (!Number.isFinite(rows) || rows < 1) return;
        if (!Number.isFinite(tpr) || tpr < 1) return;
        applySchema(rows, tpr, caps);
    });

    $("#btnClearRoom")?.addEventListener("click", () => {
        state.schema = [];
        state.forbidden.clear();
        state.placements.clear();
        state.placedByStudent.clear();
        state.selection.studentId = null;
        state.selection.seatKey = null;
        renderRoom();
        renderStudents();
        renderConstraints();
        updateBanButtonLabel();
    });

    // Options
    $("#optMixage")?.addEventListener("change", (e) => (state.options.prefer_mixage = e.target.checked));
    $("#optSolo")?.addEventListener("change", (e) => (state.options.prefer_alone = e.target.checked));

    // Name view
    $("#nvPrenom")?.addEventListener("change", () => {
        state.nameView = "first";
        renderRoom();
    });
    $("#nvNom")?.addEventListener("change", () => {
        state.nameView = "last";
        renderRoom();
    });
    $("#nvPrenomNom")?.addEventListener("change", () => {
        state.nameView = "both";
        renderRoom();
    });

    // Seat actions
    $("#btnToggleBan")?.addEventListener("click", toggleSelectedSeatBan);
    $("#btnUnassign")?.addEventListener("click", unassignSelected);

    // Students search
    $("#studentSearch")?.addEventListener("input", renderStudents);

    // Constraints form
    $("#constraintType")?.addEventListener("change", onConstraintTypeChange);
    $("#btnAddConstraint")?.addEventListener("click", addConstraint);
    $("#btnCancelConstraint")?.addEventListener("click", cancelConstraintForm);

    // First renders
    renderRoom();
    renderStudents();
    refreshConstraintSelectors();
    onConstraintTypeChange();
    updateBanButtonLabel();
}

window.addEventListener("DOMContentLoaded", init);
