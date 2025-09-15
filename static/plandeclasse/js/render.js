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
function appendSeatLabelFitted(svg, cx, cy, seatW, seatH, texte, seatKey) {
    // Paramètres d’ajustement
    const paddingX = Math.round(8 * UI_SCALE);
    const paddingY = Math.round(6 * UI_SCALE);
    const interligne = 1.12;
    const policeMin = Math.max(8, Math.round(8 * UI_SCALE));
    const policeDepart = Math.floor(
        Math.min(22 * UI_SCALE, seatW * 0.28, seatH * 0.70)
    );

    const lignes = String(texte || "").split("\n").slice(0, 2); // max 2 lignes
    const ns = "http://www.w3.org/2000/svg";

    const textEl = document.createElementNS(ns, "text");
    textEl.setAttribute("text-anchor", "middle");
    textEl.setAttribute("class", "seat-name");
    textEl.setAttribute("data-seat", seatKey);
    svg.appendChild(textEl);

    // Crée les tspans immédiatement pour que les mesures fonctionnent

    const tspans = lignes.map((l) => {
        const t = document.createElementNS(ns, "tspan");
        t.setAttribute("x", String(cx));
        t.textContent = l;
        // 👇 ajoute cette ligne pour que le clic sur <tspan> soit nativement reconnu
        t.setAttribute("data-seat", seatKey);
        textEl.appendChild(t);
        return t;
    });

    const largeurMax = seatW - paddingX * 2;
    const hauteurMax = seatH - paddingY * 2;

    // Positionne verticalement selon la taille de police courante
    function positionnerSelonTaille(taille) {
        const lh = taille * interligne;
        if (tspans.length === 1) {
            textEl.setAttribute("x", String(cx));
            textEl.setAttribute("y", String(cy));
            tspans[0].setAttribute("dy", "0");
        } else {
            const totalH = lh * tspans.length;
            const yTop = cy - totalH / 2 + taille * 0.8; // centrage optique
            textEl.setAttribute("y", String(yTop));
            tspans.forEach((ts, i) => {
                ts.setAttribute("x", String(cx));
                ts.setAttribute("dy", i === 0 ? "0" : String(lh));
            });
        }
    }

    // Teste si toutes les lignes tiennent en largeur
    function tientEnLargeur() {
        return tspans.every((ts) => ts.getComputedTextLength() <= largeurMax);
    }

    // Réduction progressive de la police (sans style inline)
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

    // Dernier recours : ellipse PAR LIGNE si ça dépasse encore
    if (!tientEnLargeur()) {
        const ellipsiser = (ts) => {
            const original = ts.textContent || "";
            const chars = Array.from(original);

            // 1) coupe mot à mot
            let cut = original;
            while (ts.getComputedTextLength() > largeurMax && /\s/.test(cut)) {
                cut = cut.replace(/\s+\S+$/u, ""); // retire le dernier mot
                ts.textContent = cut + "…";
                if (cut.length <= 1) break;
            }
            // 2) coupe caractère à caractère
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
        // re-centre verticalement (hauteur modifiée)
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
export function renderRoom() {
    const svg = /** @type {SVGSVGElement|null} */ ($("#roomCanvas"));
    if (!svg) return;
    svg.innerHTML = "";

    const nbRangees = state.schema.length;
    if (nbRangees === 0) {
        svg.setAttribute("viewBox", `0 0 ${Math.round(600 * UI_SCALE)} ${Math.round(200 * UI_SCALE)}`);
        svg.setAttribute("width", String(Math.round(600 * UI_SCALE)));
        svg.setAttribute("height", String(Math.round(200 * UI_SCALE)));
        return;
    }

    // Dimensions (compactes) calculées selon le schéma
    const {padX, padY, seatW, tableH, seatGap, colGap, rowGap, boardH} =
        computeDims(state.schema);

    // Largeurs de rangée (centrage)
    const largeursRangee = state.schema.map((caps) => {
        const tablesW = caps.reduce((somme, cap) => {
            const c = Math.abs(cap); // compte aussi la largeur des trous
            return somme + c * seatW + (c - 1) * seatGap;
        }, 0);
        const entre = (caps.length - 1) * colGap;
        return tablesW + entre;
    });
    const largeurMaxRangee = Math.max(...largeursRangee);
    const largeurTableau = Math.max(largeurMaxRangee, 600 * UI_SCALE);

    const xTableau = padX + (largeurMaxRangee - largeurTableau) / 2;
    const yTableau = padY;

    // Origines Y des rangées
    const originesY = [];
    let yCourant = yTableau + boardH + Math.round(10 * UI_SCALE);
    for (let y = 0; y < nbRangees; y++) {
        originesY.push(yCourant);
        yCourant += tableH + rowGap;
    }

    const largeurTotale = padX * 2 + largeurMaxRangee;
    const hauteurTotale = (originesY.at(-1) || padY + 32) + tableH + padY;

    // Vue + dimensions (sans style inline)
    svg.setAttribute("viewBox", `0 0 ${largeurTotale} ${hauteurTotale}`);
    // Si tu souhaites fixer une taille “min” côté JS, préfère les attributs :
    svg.setAttribute("width", String(largeurTotale));
    svg.setAttribute("height", String(Math.min(800, hauteurTotale)));

    const ns = "http://www.w3.org/2000/svg";

    // motif hatch pour sièges interdits
// motif hatch pour sièges interdits (scalé)
    const defs = document.createElementNS(ns, "defs");
    const pattern = document.createElementNS(ns, "pattern");
    pattern.setAttribute("id", "forbidPattern");
    pattern.setAttribute("patternUnits", "userSpaceOnUse");

// scale du pavé de pattern
    const patS = UI_SCALE;
    pattern.setAttribute("width", String(8 * patS));
    pattern.setAttribute("height", String(8 * patS));

    const pBg = document.createElementNS(ns, "rect");
    pBg.setAttribute("width", String(8 * patS));
    pBg.setAttribute("height", String(8 * patS));
    pBg.setAttribute("fill", "#f3f4f6");
    pattern.appendChild(pBg);

    const pLines = document.createElementNS(ns, "path");
// on garde le même tracé de base…
    pLines.setAttribute("d", "M0,8 l8,-8 M-2,2 l4,-4 M6,10 l4,-4");
    pLines.setAttribute("stroke", "#cbd5e1");
    pLines.setAttribute("stroke-width", "1");
// mais on le scale globalement pour suivre l'échelle UI
    pLines.setAttribute("transform", `scale(${patS})`);
    pattern.appendChild(pLines);

    defs.appendChild(pattern);
    svg.appendChild(defs);


    // Tableau
    const rectTableau = document.createElementNS(ns, "rect");
    rectTableau.setAttribute("x", String(xTableau));
    rectTableau.setAttribute("y", String(yTableau));
    rectTableau.setAttribute("width", String(largeurTableau));
    rectTableau.setAttribute("height", String(boardH));
    rectTableau.setAttribute("class", "board-rect");
    svg.appendChild(rectTableau);

    const labelTableau = document.createElementNS(ns, "text");
    labelTableau.setAttribute("x", String(xTableau + largeurTableau / 2));
    labelTableau.setAttribute("y", String(yTableau + boardH / 2));
    labelTableau.setAttribute("text-anchor", "middle");
    labelTableau.setAttribute("dominant-baseline", "middle");
    labelTableau.setAttribute("class", "board-label");
    labelTableau.textContent = "TABLEAU";
    svg.appendChild(labelTableau);

    const {firstMap, lastMap, bothMap} = buildDisplayMaps(state.students);

    for (let y = 0; y < nbRangees; y++) {
        const caps = state.schema[y];

        const tablesW = caps.reduce((somme, cap) => {
            const c = Math.abs(cap); // pour bien centrer chaque rangée
            return somme + c * seatW + (c - 1) * seatGap;
        }, 0);
        const entre = (caps.length - 1) * colGap;
        const largeurRangee = tablesW + entre;

        let ox = padX + (largeurMaxRangee - largeurRangee) / 2;
        const oy = originesY[y];

        for (let x = 0; x < caps.length; x++) {
            const cap = caps[x];
            const largeurTable = cap * seatW + (cap - 1) * seatGap;

            if (cap < 0) {
                // "trou" : avance le curseur horizontal comme si on avait une table
                const k = Math.abs(cap);
                const largeurTrou = k * seatW + (k - 1) * seatGap;
                ox += largeurTrou + colGap;
                continue;
            }

            // Table
            const rectTable = document.createElementNS(ns, "rect");
            rectTable.setAttribute("x", String(ox));
            rectTable.setAttribute("y", String(oy));
            rectTable.setAttribute("width", String(largeurTable));
            rectTable.setAttribute("height", String(tableH));
            rectTable.setAttribute("rx", String(Math.round(10 * UI_SCALE)));
            rectTable.setAttribute("class", "table-rect");
            svg.appendChild(rectTable);

            for (let s = 0; s < cap; s++) {
                const sx = ox + s * (seatW + seatGap);
                const sy = oy;
                const seatKey = `${x},${y},${s}`;
                const occupant = state.placements.get(seatKey) ?? null;
                const estInterdit = state.forbidden.has(seatKey);
                const estSelection = state.selection.seatKey === seatKey;

                // Cellule de siège
                const rectSiege = document.createElementNS(ns, "rect");
                rectSiege.setAttribute("x", String(sx));
                rectSiege.setAttribute("y", String(sy));
                rectSiege.setAttribute("width", String(seatW));
                rectSiege.setAttribute("height", String(tableH));
                rectSiege.setAttribute("data-seat", seatKey);
                rectSiege.setAttribute(
                    "class",
                    "seat-cell " +
                    (estInterdit
                        ? "seat-forbidden "
                        : occupant != null
                            ? "seat-occupied "
                            : "seat-free ") +
                    (estSelection ? "seat-selected" : ""),
                );

                if (estInterdit) {
                    rectSiege.setAttribute("fill", "url(#forbidPattern)");
                    rectSiege.setAttribute("stroke-width", "2");
                } else {
                    rectSiege.removeAttribute("fill");
                    rectSiege.removeAttribute("stroke-width");
                }
                svg.appendChild(rectSiege);

                // Croisillon d’overlay sur les sièges interdits
                if (estInterdit) {
                    const cross = document.createElementNS(ns, "path");
                    const pad = Math.round(8 * UI_SCALE);
                    const x1 = sx + pad,
                        y1 = sy + pad;
                    const x2 = sx + seatW - pad,
                        y2 = sy + tableH - pad;
                    const x3 = sx + pad,
                        y3 = sy + tableH - pad;
                    const x4 = sx + seatW - pad,
                        y4 = sy + pad;
                    cross.setAttribute("d", `M${x1},${y1} L${x2},${y2} M${x3},${y3} L${x4},${y4}`);
                    cross.setAttribute("class", "seat-forbidden-cross");
                    svg.appendChild(cross);
                }

                // Séparateur fin entre sièges
// Séparateur fin entre sièges (scalé)
                if (s < cap - 1) {
                    const divider = document.createElementNS(ns, "rect");

                    // largeur du trait et padding vertical proportionnels à l'échelle
                    const dividerW = Math.max(1, Math.round(1 * UI_SCALE));
                    const dividerYPad = Math.round(6 * UI_SCALE);

                    divider.setAttribute("x", String(sx + seatW + seatGap / 2 - dividerW / 2));
                    divider.setAttribute("y", String(sy + dividerYPad));
                    divider.setAttribute("width", String(dividerW));
                    divider.setAttribute("height", String(tableH - 2 * dividerYPad));
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

            ox += largeurTable + colGap;
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
