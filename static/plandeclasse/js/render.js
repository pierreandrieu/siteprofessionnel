// static/plandeclasse/js/render.js
"use strict";

/**
 * Module Render : gère le SVG de la salle, les cartes élèves et quelques refresh UI.
 * Dépend de l’état et des utils, mais pas des interactions.
 *
 * Sécurité (CSP) :
 *  - Aucun style inline n’est posé (pas d’attribut "style").
 *  - Toutes les personnalisations passent par des attributs SVG (ex: font-size)
 *    ou des classes CSS définies dans un fichier .css séparé.
 */

import {state} from "plandeclasse/state";
import {$, buildDisplayMaps, compareByLastThenFirst, norm} from "plandeclasse/utils";

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
// Facteur d’échelle global de l’UI
const UI_SCALE = 1.75;

function computeDims(schema) {
    const nbRangees = schema.length;

    const s = UI_SCALE;
    // Base UI : valeurs confort
    const base = {
        padX: 16*s,
        padY: 12*s,
        seatW: 80*s,  // largeur d’un siège (UI)
        tableH: 30*s, // hauteur d’une table (UI)
        seatGap: 4*s, // séparateur fin entre sièges
        colGap: 16*s, // écart entre tables d’une même rangée
        rowGap: 22*s, // écart vertical entre rangées
        boardH: 18*s, // bandeau "tableau"
    };

    // Plus de rangées = compacter un peu en vertical (sans écraser).
    const facteurV = Math.max(0.72, 1 - Math.max(0, nbRangees - 4) * 0.07);
    // En horizontal, réduction très légère après 6 rangées.
    const facteurH = Math.max(0.88, 1 - Math.max(0, nbRangees - 6) * 0.02);

    return {
        padX: base.padX,
        padY: base.padY,
        seatW: Math.round(base.seatW * facteurH),
        tableH: Math.round(base.tableH * facteurV),
        seatGap: base.seatGap,
        colGap: base.colGap,
        rowGap: Math.round(base.rowGap * facteurV),
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
    const btnBan = document.getElementById("btnToggleBan");
    const btnUnassign = document.getElementById("btnUnassign");

    const cle = state.selection.seatKey;
    const aSelection = !!cle;
    const estOccupe = aSelection ? state.placements.has(cle) : false;

    if (btnBan) {
        if (!aSelection || estOccupe) {
            btnBan.disabled = true;
            btnBan.textContent = "le siège doit rester vide";
        } else {
            const estInterdit = state.forbidden.has(cle);
            btnBan.disabled = false;
            btnBan.textContent = estInterdit
                ? "rendre le siège disponible"
                : "le siège doit rester vide";
        }
    }

    if (btnUnassign) {
        btnUnassign.disabled = !estOccupe;
    }
}

/**
 * Ajoute un label <text>/<tspan> centré dans un siège :
 * - ajuste dynamiquement la taille de police pour tenir en largeur/hauteur ;
 * - en dernier recours, ellipse PAR LIGNE ("…") si trop long ;
 * - ne pose PAS de style inline (utilise l’attribut SVG "font-size").
 *
 * @param {SVGSVGElement} svg - racine du SVG
 * @param {number} cx - centre X du siège
 * @param {number} cy - centre Y du siège
 * @param {number} seatW - largeur du siège (px)
 * @param {number} seatH - hauteur du siège (px)
 * @param {string} texte - "Prénom", "NOM" ou "Prénom\nNOM"
 * @param {string} seatKey - clé du siège (pour data-seat)
 */

/**
 * Ajoute un label <text>/<tspan> centré et ajusté dans un siège.
 * (identique au tien, conservé – sans style inline)
 */
/**
 * Ajoute un label <text>/<tspan> centré et ajusté dans un siège.
 * CSP-friendly : pas d'attribut style ; on utilise font-size et pointer-events.
 */
function appendSeatLabelFitted(parent, cx, cy, seatW, seatH, texte, seatKey) {
    const paddingX = Math.round(8 * UI_SCALE);
    const paddingY = Math.round(6 * UI_SCALE);
    const interligne = 1.12;
    const policeMin = Math.max(8, Math.round(8 * UI_SCALE));
    const policeDepart = Math.floor(Math.min(22 * UI_SCALE, seatW * 0.28, seatH * 0.70));

    const lignes = String(texte || "").split("\n").slice(0, 2);
    const ns = "http://www.w3.org/2000/svg";

    const textEl = document.createElementNS(ns, "text");
    textEl.setAttribute("text-anchor", "middle");
    textEl.setAttribute("class", "seat-name");
    // Laisse passer le clic vers le <rect data-seat> en dessous
    textEl.setAttribute("pointer-events", "none");

    parent.appendChild(textEl);

    const tspans = lignes.map((l) => {
        const t = document.createElementNS(ns, "tspan");
        t.setAttribute("x", String(cx));
        t.setAttribute("pointer-events", "none"); // sécurité : pas d'interception par <tspan>
        t.textContent = l;
        textEl.appendChild(t);
        return t;
    });

    const largeurMax = seatW - paddingX * 2;
    const hauteurMax = seatH - paddingY * 2;

    function positionnerSelonTaille(taille) {
        const lh = taille * interligne;
        if (tspans.length === 1) {
            textEl.setAttribute("x", String(cx));
            textEl.setAttribute("y", String(cy));
            tspans[0].setAttribute("dy", "0");
        } else {
            const totalH = lh * tspans.length;
            const yTop = cy - totalH / 2 + taille * 0.8;
            textEl.setAttribute("y", String(yTop));
            tspans.forEach((ts, i) => {
                ts.setAttribute("x", String(cx));
                ts.setAttribute("dy", i === 0 ? "0" : String(lh));
            });
        }
    }

    function tientEnLargeur() {
        return tspans.every((ts) => ts.getComputedTextLength() <= largeurMax);
    }

    let taille = policeDepart;
    while (taille >= policeMin) {
        textEl.setAttribute("font-size", String(taille));
        positionnerSelonTaille(taille);
        const lh = taille * interligne;
        const totalH = lh * tspans.length;
        const okH = totalH <= hauteurMax;
        const okW = tientEnLargeur();
        if (okH && okW) break;
        taille -= 1;
    }

    if (!tientEnLargeur()) {
        const ellipsiser = (ts) => {
            const original = ts.textContent || "";
            const chars = Array.from(original);
            let cut = original;
            while (ts.getComputedTextLength() > largeurMax && /\s/.test(cut)) {
                cut = cut.replace(/\s+\S+$/u, "");
                ts.textContent = cut + "…";
                if (cut.length <= 1) break;
            }
            if (ts.getComputedTextLength() > largeurMax) {
                let n = chars.length - 1;
                while (n > 3) {
                    ts.textContent = chars.slice(0, n).join("") + "…";
                    if (ts.getComputedTextLength() <= largeurMax) break;
                    n -= 1;
                }
            }
        };
        tspans.forEach(ellipsiser);
        positionnerSelonTaille(taille);
    }
}

/* ==========================================================================
   Rendu du SVG salle
   ========================================================================== */

/**
 * Rendu du SVG de la salle (tables, sièges, bordures, croisillons, labels).
 * Respecte la CSP (pas d’attribut "style" posé).
 */
/**
 * Rendu du SVG de la salle (tables, sièges, labels).
 * CSP-friendly : pas de style inline.
 * Gère les offsets persistants + le “draft” (fantôme) d’une table en déplacement clavier.
 * Ajoute data-table="x,y" sur chaque groupe pour la sélection d’une table.
 */
/**
 * Rendu du SVG de la salle (tables, sièges, labels).
 * CSP-friendly : pas de style inline.
 * Gère les offsets persistants + le “draft” (fantôme) d’une table en déplacement clavier.
 * Ajoute data-table="x,y" sur chaque groupe pour la sélection d’une table.
 */
export function renderRoom() {
    const svg = /** @type {SVGSVGElement|null} */ ($("#roomCanvas"));
    if (!svg) return;
    svg.innerHTML = "";

    const nbRangees = state.schema.length;
    const {padX, padY, seatW, tableH, seatGap, colGap, rowGap, boardH} = computeDims(state.schema);

    if (nbRangees === 0) {
        svg.setAttribute("viewBox", `0 0 ${Math.round(600 * UI_SCALE)} ${Math.round(200 * UI_SCALE)}`);
        svg.setAttribute("width", String(Math.round(600 * UI_SCALE)));
        svg.setAttribute("height", String(Math.round(200 * UI_SCALE)));
        return;
    }

    // Largeurs de rangée (centrage)
    const rowWidths = state.schema.map((caps) => {
        const tablesW = caps.reduce((sum, cap) => {
            const c = Math.abs(cap);
            return sum + c * seatW + (c - 1) * seatGap;
        }, 0);
        return tablesW + (caps.length - 1) * colGap;
    });
    const maxRowW = Math.max(...rowWidths);
    const boardW = Math.max(maxRowW, 600 * UI_SCALE);
    const xBoard = padX + (maxRowW - boardW) / 2;
    const yBoard = padY;

    // Origines Y
    const originsY = [];
    let yCur = yBoard + boardH + Math.round(10 * UI_SCALE);
    for (let y = 0; y < nbRangees; y++) {
        originsY.push(yCur);
        yCur += tableH + rowGap;
    }

    const totalW = padX * 2 + maxRowW;
    const totalH = (originsY.at(-1) || padY + 32) + tableH + padY;

    svg.setAttribute("viewBox", `0 0 ${totalW} ${totalH}`);
    svg.setAttribute("width", String(totalW));
    svg.setAttribute("height", String(Math.min(800, totalH)));

    const ns = "http://www.w3.org/2000/svg";

    // defs pour le pattern “forbid”
    const defs = document.createElementNS(ns, "defs");
    const pattern = document.createElementNS(ns, "pattern");
    pattern.setAttribute("id", "forbidPattern");
    pattern.setAttribute("patternUnits", "userSpaceOnUse");
    const patS = UI_SCALE;
    pattern.setAttribute("width", String(8 * patS));
    pattern.setAttribute("height", String(8 * patS));
    const pBg = document.createElementNS(ns, "rect");
    pBg.setAttribute("width", String(8 * patS));
    pBg.setAttribute("height", String(8 * patS));
    pBg.setAttribute("fill", "#f3f4f6");
    pattern.appendChild(pBg);
    const pLines = document.createElementNS(ns, "path");
    pLines.setAttribute("d", "M0,8 l8,-8 M-2,2 l4,-4 M6,10 l4,-4");
    pLines.setAttribute("stroke", "#cbd5e1");
    pLines.setAttribute("stroke-width", "1");
    pLines.setAttribute("transform", `scale(${patS})`);
    pattern.appendChild(pLines);
    defs.appendChild(pattern);
    svg.appendChild(defs);

    // Tableau
    const rectBoard = document.createElementNS(ns, "rect");
    rectBoard.setAttribute("x", String(xBoard));
    rectBoard.setAttribute("y", String(yBoard));
    rectBoard.setAttribute("width", String(boardW));
    rectBoard.setAttribute("height", String(boardH));
    rectBoard.setAttribute("class", "board-rect");
    svg.appendChild(rectBoard);

    const labelBoard = document.createElementNS(ns, "text");
    labelBoard.setAttribute("x", String(xBoard + boardW / 2));
    labelBoard.setAttribute("y", String(yBoard + boardH / 2));
    labelBoard.setAttribute("text-anchor", "middle");
    labelBoard.setAttribute("dominant-baseline", "middle");
    labelBoard.setAttribute("class", "board-label");
    labelBoard.setAttribute("pointer-events", "none");
    labelBoard.textContent = "TABLEAU";
    svg.appendChild(labelBoard);

    const {firstMap, lastMap, bothMap} = buildDisplayMaps(state.students);

    // Fantôme actif ?
    const draft = state.uiDraft.nudge; // {tableKey, dx, dy, invalid} | null
    const draftKey = draft?.tableKey || null;

    for (let y = 0; y < nbRangees; y++) {
        const caps = state.schema[y];

        // largeur de la rangée (y)
        const tablesW = caps.reduce((sum, cap) => {
            const c = Math.abs(cap);
            return sum + c * seatW + (c - 1) * seatGap;
        }, 0);
        const rowW = tablesW + (caps.length - 1) * colGap;

        let ox = padX + (maxRowW - rowW) / 2; // origine X de la rangée centrée
        const oy = originsY[y];

        for (let x = 0; x < caps.length; x++) {
            const cap = caps[x];
            const absCap = Math.abs(cap);
            const tableW = absCap * seatW + (absCap - 1) * seatGap;

            if (cap < 0) {
                ox += tableW + colGap;
                continue;
            }

            // Offset persistant éventuellement présent
            const tKey = `${x},${y}`;
            const off = state.tableOffsets.get(tKey) || {dx: 0, dy: 0};

            const isDrafted = draftKey === tKey;

            // Groupe table (position persistante)
            const g = document.createElementNS(ns, "g");
            g.setAttribute("data-table", tKey);
            g.setAttribute("transform", `translate(${ox + off.dx}, ${oy + off.dy})`);
            svg.appendChild(g);

            // Table (rect principal)
            const rectTable = document.createElementNS(ns, "rect");
            rectTable.setAttribute("x", "0");
            rectTable.setAttribute("y", "0");
            rectTable.setAttribute("width", String(tableW));
            rectTable.setAttribute("height", String(tableH));
            rectTable.setAttribute("rx", String(Math.round(10 * UI_SCALE)));
            rectTable.setAttribute(
                "class",
                "table-rect" + (state.selection.tableKey === tKey ? " table-selected" : "")
            );
            g.appendChild(rectTable);

            // Si un ghost est actif pour cette table, on le dessine au-dessus
            if (isDrafted) {
                const ghost = document.createElementNS(ns, "rect");
                ghost.setAttribute("x", String(draft.dx));
                ghost.setAttribute("y", String(draft.dy));
                ghost.setAttribute("width", String(tableW));
                ghost.setAttribute("height", String(tableH));
                ghost.setAttribute("rx", String(Math.round(10 * UI_SCALE)));
                ghost.setAttribute("class", "table-ghost" + (draft.invalid ? " table-ghost-invalid" : ""));
                g.appendChild(ghost);
            }

            // Sièges de la table
            for (let s = 0; s < cap; s++) {
                const sx = s * (seatW + seatGap);
                const sy = 0;
                const seatKey = `${x},${y},${s}`;
                const occ = state.placements.get(seatKey) ?? null;
                const isForbidden = state.forbidden.has(seatKey);
                const isSelectedSeat = state.selection.seatKey === seatKey;

                const rSeat = document.createElementNS(ns, "rect");
                rSeat.setAttribute("x", String(sx));
                rSeat.setAttribute("y", String(sy));
                rSeat.setAttribute("width", String(seatW));
                rSeat.setAttribute("height", String(tableH));
                rSeat.setAttribute("data-seat", seatKey);
                rSeat.setAttribute(
                    "class",
                    "seat-cell " +
                    (isForbidden ? "seat-forbidden " : occ != null ? "seat-occupied " : "seat-free ") +
                    (isSelectedSeat ? "seat-selected" : "")
                );
                if (isForbidden) {
                    rSeat.setAttribute("fill", "url(#forbidPattern)");
                    rSeat.setAttribute("stroke-width", "2");
                } else {
                    rSeat.removeAttribute("fill");
                    rSeat.removeAttribute("stroke-width");
                }
                g.appendChild(rSeat);

                // séparateur entre sièges (ne capte pas les clics)
                if (s < cap - 1) {
                    const divider = document.createElementNS(ns, "rect");
                    const dividerW = Math.max(1, Math.round(1 * UI_SCALE));
                    const dividerYPad = Math.round(6 * UI_SCALE);
                    divider.setAttribute("x", String(sx + seatW + seatGap / 2 - dividerW / 2));
                    divider.setAttribute("y", String(sy + dividerYPad));
                    divider.setAttribute("width", String(dividerW));
                    divider.setAttribute("height", String(tableH - 2 * dividerYPad));
                    divider.setAttribute("class", "seat-divider");
                    divider.setAttribute("pointer-events", "none");
                    g.appendChild(divider);
                }

                // Label prénom/nom si occupé
                if (occ != null) {
                    const nm =
                        state.nameView === "first"
                            ? firstMap.get(occ) || ""
                            : state.nameView === "last"
                                ? lastMap.get(occ) || ""
                                : bothMap.get(occ) || "";

                    const cx = sx + seatW / 2;
                    const cy = sy + tableH / 2;
                    appendSeatLabelFitted(g, cx, cy, seatW, tableH, nm, seatKey);
                }
            }

            // --- Grab strip (bandeau de sélection table)
            // Bandeau au-dessus de la table : cliquable, quasi invisible.
            const grabH = Math.max(10, Math.round(8 * UI_SCALE));
            const grab = document.createElementNS(ns, "rect");
            grab.setAttribute("x", "0");
            grab.setAttribute("y", String(-grabH)); // au-dessus de la table
            grab.setAttribute("width", String(tableW));
            grab.setAttribute("height", String(grabH));
            grab.setAttribute("data-table", tKey);
            grab.setAttribute("class", "table-handle");
            // invisible mais "peint" pour que les events SVG le prennent comme cible
            grab.setAttribute("fill", "#000");
            grab.setAttribute("fill-opacity", "0.001");
            g.appendChild(grab);

            // Avance le curseur horizontal pour la table suivante
            ox += tableW + colGap;
        }
    }
}


/* ==========================================================================
   Rendu de la liste élèves
   ========================================================================== */

/** Rendu liste élèves (non placés/placés) + gestion de la sélection d’élève. */
export function renderStudents() {
    const listeNonPlaces = /** @type {HTMLElement|null} */ ($("#studentsUnplaced"));
    const listePlaces = /** @type {HTMLElement|null} */ ($("#studentsPlaced"));
    const champRecherche = /** @type {HTMLInputElement|null} */ ($("#studentSearch"));
    if (!listeNonPlaces || !listePlaces) return;

    const q = norm(champRecherche?.value || "");
    listeNonPlaces.innerHTML = "";
    listePlaces.innerHTML = "";

    // Tri : NOM puis prénom (collator FR)
    const items = [...state.students].sort(compareByLastThenFirst);

    for (const st of items) {
        const f = norm(st.first);
        const l = norm(st.last);
        const fl = (f + " " + l).trim();
        const lf = (l + " " + f).trim();

        if (q && !(fl.includes(q) || lf.includes(q) || f.includes(q) || l.includes(q))) {
            continue;
        }

        const carte = document.createElement("div");
        carte.className = "student" + (state.selection.studentId === st.id ? " selected" : "");
        carte.dataset.sid = String(st.id);
        carte.innerHTML = `
      <div class="d-flex flex-column">
        <span class="student-name">${st.first}</span>
        <span class="student-sub">${st.last}</span>
      </div>
    `;

        carte.addEventListener("click", () => {
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

        if (state.placedByStudent.has(st.id)) listePlaces.appendChild(carte);
        else listeNonPlaces.appendChild(carte);
    }
}
