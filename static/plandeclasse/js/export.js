// static/plandeclasse/js/export.js
"use strict";

/**
 * Module Export — génération et envoi des artefacts d’export.
 *
 * Fonctions clés :
 * - buildExportPayload() : construit le payload complet à envoyer au backend,
 *   en incluant deux SVG : vue élève et vue prof.
 * - startExport() : envoie le payload au backend /plandeclasse/export,
 *   récupère les URLs et met à jour les liens de téléchargement dans l’IHM.
 * - setupExportUI() / syncExportButtonEnabled() : gestion fine du bouton
 *   d’export (champ nom de classe requis + tooltip explicatif).
 *
 * Notes d’implémentation :
 * - La **vue prof** est réalisée en appliquant un **miroir vertical global**
 *   (translate + scaleY négatif) puis, pour chaque <text>, une inversion locale
 *   (scaleY négatif) et un ajustement de y (y := -y0) pour conserver un texte
 *   lisible tout en maintenant la position “miroir”.
 * - Le code est rétro-compatible avec l’ancien backend qui ne renvoyait qu’une
 *   seule vue. Dans ce cas, seuls les liens “vue élève” sont affichés.
 */

import {state} from "./state.js";
import {$} from "./utils.js";

/* ==========================================================================
   Feuille de style embarquée et outils SVG
   ========================================================================== */

/**
 * Retourne la feuille de styles minimale injectée dans les SVG exportés.
 * Garder la cohérence avec plandeclasse.css si vous modifiez les couleurs.
 * @returns {string}
 */
function svgInlineStyles() {
    return `
.board-rect{fill:#1f2937;stroke:#111827;stroke-width:1.5}
.board-label{fill:#994444;font-weight:600;letter-spacing:.02em;font-size:12px}
.table-rect{fill:#f1f3f5;stroke:#cfd4da}
.seat-cell{cursor:default}
.seat-free{fill:rgba(255,255,255,.6)}
.seat-occupied{fill:rgba(11,87,208,.12)}
.seat-selected{stroke:#ffc107;stroke-width:3}
.seat-name{fill:#212529;dominant-baseline:middle;font-weight:600;white-space:pre-line}
.seat-divider{fill:#d1d5db}
.seat-forbidden-cross{stroke:#ef4444;stroke-width:1.5;stroke-linecap:round;opacity:.6}
`.trim();
}

/**
 * Prépare un clone du #roomCanvas pour l’export :
 * - copie l’SVG affiché,
 * - force xmlns,
 * - force width/height d’après viewBox,
 * - injecte <style> et un fond blanc couvrant (évite la transparence côté PNG).
 *
 * @param {SVGSVGElement} svgEl - l’élément SVG source (#roomCanvas)
 * @returns {SVGSVGElement} - le clone prêt à être sérialisé
 */
function prepareSvgClone(svgEl) {
    const clone = /** @type {SVGSVGElement} */ (svgEl.cloneNode(true));

    // Namespace + dimensionnement à partir du viewBox
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    const vbAttr = clone.getAttribute("viewBox");
    if (vbAttr) {
        const parts = vbAttr.split(/\s+/).map(Number);
        if (parts.length === 4 && Number.isFinite(parts[2]) && Number.isFinite(parts[3])) {
            clone.setAttribute("width", String(parts[2]));
            clone.setAttribute("height", String(parts[3]));
        }
    }

    // <style> embarqué
    const styleEl = document.createElementNS("http://www.w3.org/2000/svg", "style");
    styleEl.setAttribute("type", "text/css");
    styleEl.textContent = svgInlineStyles();
    clone.insertBefore(styleEl, clone.firstChild);

    // Fond blanc couvrant (évite les checkerboards à l’export)
    const bg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    bg.setAttribute("x", "0");
    bg.setAttribute("y", "0");
    bg.setAttribute("width", "100%");
    bg.setAttribute("height", "100%");
    bg.setAttribute("fill", "#ffffff");
    clone.insertBefore(bg, styleEl.nextSibling);

    return clone;
}

/**
 * Sérialise un SVG DOM en XML, avec l’en-tête XML standard.
 * @param {SVGSVGElement} svg - l’élément SVG à sérialiser
 * @returns {string} - XML SVG complet prêt pour l’export
 */
function serializeSvg(svg) {
    const xml = new XMLSerializer().serializeToString(svg);
    return `<?xml version="1.0" encoding="UTF-8"?>\n${xml}`;
}

/* ==========================================================================
   Collecte des deux variantes de SVG (élève / prof)
   ========================================================================== */

/**
 * Produit le SVG “vue élève” : identique à l’affichage à l’écran.
 * @returns {string|null} - XML SVG ou null si le canvas est indisponible
 */
function collectRoomSvgMarkupStudent() {
    const svgEl = document.getElementById("roomCanvas");
    if (!(svgEl instanceof SVGSVGElement)) return null;
    const clone = prepareSvgClone(svgEl);
    return serializeSvg(clone);
}

function buildObjectiveMarkers() {
    const out = [];
    if (state.options.prefer_alone) {
        out.push({type: "_objective_", human: "objectif : maximiser les élèves sans voisin"});
    }
    if (state.options.prefer_mixage) {
        out.push({type: "_objective_", human: "objectif : minimiser les paires adjacentes de même genre"});
    }
    out.push({type: "_objective_", human: "objectif : minimiser la distance au tableau (somme des rangs)"});
    return out;
}

/**
 * Produit le SVG “vue prof” : miroir vertical, **textes lisibles**.
 *
 * Méthode :
 * 1. On regroupe le contenu (hors <style> et fond blanc) dans <g transform="translate(0,H) scale(1,-1)">.
 * 2. Pour chaque <text>, on applique localement `scale(1,-1)` ET on remplace `y` par `-y`.
 *    - Le miroir global retourne toute la scène verticalement.
 *    - L’inversion locale remet le texte “à l’endroit”.
 *    - Le `y := -y0` garantit la bonne position finale (miroir parfait).
 *
 * @returns {string|null} - XML SVG ou null si le canvas est indisponible
 */
function collectRoomSvgMarkupTeacher() {
    const svgEl = document.getElementById("roomCanvas");
    if (!(svgEl instanceof SVGSVGElement)) return null;

    const clone = prepareSvgClone(svgEl);

    // Dimensions nécessaires au pivot 180°
    const W = Number(clone.getAttribute("width") || "0");
    const H = Number(clone.getAttribute("height") || "0");
    if (!Number.isFinite(W) || !Number.isFinite(H) || W <= 0 || H <= 0) {
        // Fallback : si dimensions invalides, renvoyer le clone tel quel
        return serializeSvg(clone);
    }

    const ns = "http://www.w3.org/2000/svg";
    const g = document.createElementNS(ns, "g");
    // Rotation 180° : translate(W,H) puis scale(-1,-1)
    g.setAttribute("transform", `translate(0, ${H}) scale(1, -1)`);

    // Déplacer tout (sauf <style> et fond blanc) dans le <g> pivot
    const children = Array.from(clone.childNodes);
    for (let i = 0; i < children.length; i++) {
        const n = children[i];
        if (!(n instanceof Element)) continue;
        const tag = n.tagName?.toLowerCase();
        const isStyle = tag === "style";
        const isBg =
            tag === "rect" &&
            n.getAttribute("width") === "100%" &&
            n.getAttribute("height") === "100%";
        if (isStyle || isBg) continue;
        g.appendChild(n);
    }
    clone.appendChild(g);

    // Redressement des textes : flip local + inversion de leurs coordonnées.
    const texts = g.querySelectorAll("text");
    texts.forEach((t) => {
        const xAttr = t.getAttribute("x");
        const yAttr = t.getAttribute("y");

        // On ne touche qu'aux textes positionnés ; prudence en cas de valeurs non numériques
        const hasX = xAttr != null && xAttr !== "";
        const hasY = yAttr != null && yAttr !== "";

        if (hasY) {
            const y0 = Number(yAttr);
            if (Number.isFinite(y0)) t.setAttribute("y", String(-y0));
        }
        // Flip local pour remettre les glyphes à l'endroit (X et Y)
        const prev = t.getAttribute("transform") || "";
        t.setAttribute("transform", `scale(1,-1)${prev ? " " + prev : ""}`);

        // NB : on ne touche pas aux dy/dx (relatifs) : le flip local gère le sens.
    });

    return serializeSvg(clone);
}


/* ==========================================================================
   Construction du payload envoyé au backend
   ========================================================================== */

/**
 * Construit le payload d’export :
 * - nom de la classe (OBLIGATOIRE côté UI, mais inclus ici pour robustesse),
 * - svg_markup_student : SVG autonome “vue élève”,
 * - svg_markup_teacher : SVG autonome “vue prof” (miroir vertical, textes à l’endroit),
 * - état courant (schéma, élèves, contraintes, options, etc.).
 *
 * @returns {object} - objet JSON sérialisable pour /plandeclasse/export
 */
export function buildExportPayload() {
    const classInput = /** @type {HTMLInputElement|null} */ ($("#className"));
    const class_name = (classInput?.value || "").trim();

    return {
        class_name,
        svg_markup_student: collectRoomSvgMarkupStudent(),
        svg_markup_teacher: collectRoomSvgMarkupTeacher(),
        schema: state.schema,
        students: state.students.map((s) => ({
            id: s.id, name: s.name, first: s.first, last: s.last, gender: s.gender ?? null,
        })),
        options: state.options,
        // on concatène les “objectifs” pour qu’ils sortent dans le TXT
        constraints: [...state.constraints, ...buildObjectiveMarkers()],
        forbidden: Array.from(state.forbidden),
        placements: Object.fromEntries(state.placements),
        name_view: state.nameView,
    };
}

/* ==========================================================================
   Utilitaires UI
   ========================================================================== */

/**
 * Renseigne (ou masque) un lien de téléchargement selon l’URL fournie.
 * @param {HTMLAnchorElement|null} a - balise <a> ciblée (peut être null si l’IHM diffère)
 * @param {string|undefined} url - URL de téléchargement (ou undefined/null pour masquer)
 * @returns {void}
 */
function setDownloadLink(a, url) {
    if (!a) return;
    if (url) {
        a.href = url;
        a.classList.remove("d-none");
    } else {
        a.href = "#";
        a.classList.add("d-none");
    }
}

/* ==========================================================================
   Export — envoi + mise à jour des liens
   ========================================================================== */

/**
 * Démarre l’export :
 * - Vérifie la présence du nom de classe,
 * - Produit deux SVG (élève/prof),
 * - Envoie l’état complet au backend,
 * - Met à jour les **4 blocs** de liens :
 *     • Vue élève  : PNG / PDF / SVG
 *     • Vue prof   : PNG / PDF / SVG
 *     • Sauvegarde : JSON
 *     • Archive    : ZIP (contient tous les fichiers, y compris “vue prof” si backend à jour)
 *
 * Rétro-compatibilité :
 * - Si le backend renvoie encore un “download” plat (sans .student / .teacher),
 *   on remplit uniquement la “vue élève” (ancienne logique).
 *
 * @returns {Promise<void>}
 */
export async function startExport() {
    const btn = /** @type {HTMLButtonElement|null} */ ($("#btnExport"));
    const classInput = /** @type {HTMLInputElement|null} */ ($("#className"));

    // 0) Nom de classe obligatoire (ergonomie UI)
    const className = (classInput?.value || "").trim();
    if (!className) {
        classInput?.classList.add("is-invalid");
        classInput?.focus();
        return;
    }
    classInput?.classList.remove("is-invalid");

    // 1) Vérifie la présence d’un SVG à exporter (au moins la vue élève)
    const svgTxt = collectRoomSvgMarkupStudent();
    if (!svgTxt) {
        alert("Aucun plan de classe à exporter pour le moment.");
        return;
    }

    // 2) Body JSON (deux vues incluses)
    const body = JSON.stringify({
        ...buildExportPayload(),
        class_name: className, // redondance volontaire
    });

    // 3) Feedback UI (désactive le bouton pendant l’export)
    const prev = btn?.textContent || "";
    if (btn) {
        btn.disabled = true;
        btn.textContent = "export en cours…";
    }

    try {
        const r = await fetch("/plandeclasse/export", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body,
        });
        if (!r.ok) {
            // Backend renvoie {"error": "..."} en cas de pb (ex : nom vide côté serveur)
            const msg = (await r.json().catch(() => ({})))?.error || "export failed";
            throw new Error(msg);
        }

        const data = await r.json();
        const dl = data?.download || {};

        // --- Sélecteurs IHM attendus pour les 4 blocs ---
        const block = /** @type {HTMLElement|null} */ ($("#exportDownloads"));

        // Vue élève
        const sPNG = /** @type {HTMLAnchorElement|null} */ ($("#exS_PNG"));
        const sPDF = /** @type {HTMLAnchorElement|null} */ ($("#exS_PDF"));
        const sSVG = /** @type {HTMLAnchorElement|null} */ ($("#exS_SVG"));

        // Vue prof
        const tPNG = /** @type {HTMLAnchorElement|null} */ ($("#exT_PNG"));
        const tPDF = /** @type {HTMLAnchorElement|null} */ ($("#exT_PDF"));
        const tSVG = /** @type {HTMLAnchorElement|null} */ ($("#exT_SVG"));

        // Sauvegarde + Archive
        const exJSON = /** @type {HTMLAnchorElement|null} */ ($("#exJSON"));
        const exZIP = /** @type {HTMLAnchorElement|null} */ ($("#exZIP"));

        // --- Rétro-compat : si le backend renvoie une structure plate ---
        // Ancien schéma : { png, pdf, svg, json, zip }
        // Nouveau schéma : { student: {png,pdf,svg}, teacher: {png,pdf,svg}, json, zip }
        const s = dl.student || dl;
        const t = dl.teacher || {}; // si absent : on masquera la vue prof

        // Renseigne les URLs
        setDownloadLink(sPNG, s?.png);
        setDownloadLink(sPDF, s?.pdf);
        setDownloadLink(sSVG, s?.svg);

        setDownloadLink(tPNG, t?.png);
        setDownloadLink(tPDF, t?.pdf);
        setDownloadLink(tSVG, t?.svg);

        setDownloadLink(exJSON, dl?.json);
        setDownloadLink(exZIP, dl?.zip);

        // Affiche le bloc si au moins un lien est dispo
        block?.classList.remove("d-none");
    } catch (err) {
        console.error(err);
        alert("Échec de l’export. Vérifiez le nom de la classe et votre connexion, puis réessayez.");
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = prev;
        }
    }
}

/* ==========================================================================
   Initialisation / ergonomie du bouton d’export
   ========================================================================== */

/**
 * Active/désactive le bouton d’export en fonction du champ “Nom de la classe”.
 * Initialise/entretient un tooltip explicatif tant que le bouton est inactif.
 *
 * Cette fonction est utilisée ailleurs (ex. importers.js) pour resynchroniser
 * l’état du bouton lorsque le nom de classe est modifié par programme.
 *
 * @returns {void}
 */
export function syncExportButtonEnabled() {
    /** @type {HTMLButtonElement|null} */
    const btn = document.getElementById("btnExport");
    /** @type {HTMLElement|null} */
    const wrap = document.getElementById("exportBtnWrap");
    /** @type {HTMLInputElement|null} */
    const input = document.getElementById("className");
    if (!btn || !input) return;

    const hasName = !!input.value.trim();
    btn.disabled = !hasName;

    // Tooltip explicatif tant que désactivé (Bootstrap 5)
    if (wrap && window.bootstrap?.Tooltip) {
        const tip = bootstrap.Tooltip.getOrCreateInstance(wrap, {
            trigger: "hover focus",
            placement: "top",
            title: wrap.getAttribute("title") || "Renseignez un nom de classe pour activer l’export",
        });

        if (!hasName) {
            if (typeof tip.setContent === "function") {
                tip.setContent({".tooltip-inner": "Renseignez un nom de classe pour activer l’export"});
            } else {
                wrap.setAttribute("title", "Renseignez un nom de classe pour activer l’export");
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

        // Clic sur le wrapper quand désactivé → affiche brièvement l’aide
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
                        }, 1200);
                    } catch {
                    }
                }
            });
        }
    }
}

/**
 * Prépare l’UI d’export (binding des événements + ergonomie du champ texte).
 * - Le champ “Nom de la classe” est requis,
 * - Le bouton est (ré)activé si le champ n’est pas vide,
 * - L’état invalide du champ est enlevé dès qu’on saisit quelque chose,
 * - Le clic sur #btnExport lance startExport().
 *
 * @returns {void}
 */
export function setupExportUI() {
    /** @type {HTMLInputElement|null} */
    const classInput = document.getElementById("className");
    /** @type {HTMLButtonElement|null} */
    const btn = document.getElementById("btnExport");

    if (classInput) {
        classInput.required = true;

        const onEdit = () => {
            // Synchro du bouton + nettoyage de l’état invalide
            syncExportButtonEnabled();
            if (classInput.value.trim().length > 0) {
                classInput.classList.remove("is-invalid");
            }
        };

        classInput.addEventListener("input", onEdit);
        classInput.addEventListener("change", onEdit);
    } else if (btn) {
        // Pas de champ : laisse cliquable (fallback)
        btn.disabled = false;
    }

    // Bind du bouton (une seule fois)
    if (btn && !btn.dataset.wired) {
        btn.dataset.wired = "1";
        btn.addEventListener("click", (ev) => {
            ev.preventDefault();
            startExport();
        });
    }

    // Sync initiale (utile si le nom est déjà pré-rempli via import JSON)
    syncExportButtonEnabled();
}

/* ==========================================================================
   Auto-init (sûr) : prépare l’UI à l’ouverture
   ========================================================================== */

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => setupExportUI());
} else {
    setupExportUI();
}
