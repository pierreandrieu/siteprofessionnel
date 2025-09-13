// static/plandeclasse/js/export.js
"use strict";

/**
 * Module Export — génération et envoi des artefacts d’export.
 *
 * Points clés CSP :
 *  - Pas de <style> inline, pas d’attribut style= (tout passe en attributs SVG).
 *  - Le fond blanc est un <rect> simple.
 *  - On convertit toute taille de police inline en attribut `font-size`.
 */

import {state} from "plandeclasse/state";
import {$} from "plandeclasse/utils";

/* ==========================================================================
   Outils SVG (CSP-friendly)
   ========================================================================== */

/** Ajoute un fond blanc couvrant (évite la transparence des PNG). */
function addWhiteBackground(svg) {
    const bg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    bg.setAttribute("x", "0");
    bg.setAttribute("y", "0");
    bg.setAttribute("width", "100%");
    bg.setAttribute("height", "100%");
    bg.setAttribute("fill", "#ffffff");
    svg.insertBefore(bg, svg.firstChild || null);
}

/** Copie le canvas (#roomCanvas) sans rien injecter dans le DOM. */
function cloneCanvasSvg(svgEl) {
    const clone = /** @type {SVGSVGElement} */ (svgEl.cloneNode(true));
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");

    // Dimensionne à partir du viewBox (utile pour les exports raster côté serveur).
    const vb = (clone.getAttribute("viewBox") || "").trim().split(/\s+/).map(Number);
    if (vb.length === 4 && vb.every(Number.isFinite)) {
        const [, , w, h] = vb;
        clone.setAttribute("width", String(w));
        clone.setAttribute("height", String(h));
    }
    return clone;
}

/** Petit utilitaire d’attribution en masse. */
function setAttrs(el, dict) {
    for (const [k, v] of Object.entries(dict)) el.setAttribute(k, String(v));
}

/**
 * Convertit styles et classes → attributs de présentation SVG (CSP-safe).
 * - Supprime l’attribut `style` si présent (ex: font-size), en le répercutant.
 * - Applique les styles attendus selon les classes utilisées au rendu.
 */
function applyPresentationAttributes(svg) {
    const all = svg.querySelectorAll("*");
    all.forEach((el) => {
        const tag = el.tagName.toLowerCase();
        const cls = (el.getAttribute("class") || "").split(/\s+/);

        // 1) Normalise l’attribut style → attributs dédiés (au moins font-size)
        if (el.hasAttribute("style")) {
            const style = el.getAttribute("style") || "";
            const fontSize = /font-size\s*:\s*([^;]+)/i.exec(style)?.[1];
            if (fontSize) el.setAttribute("font-size", fontSize.trim());
            el.removeAttribute("style");
        }

        // 2) Styles par classes (convertis en attributs SVG)
        if (cls.includes("board-rect")) {
            setAttrs(el, {fill: "#1f2937", stroke: "#111827", "stroke-width": "1.5"});
        }
        if (cls.includes("board-label") && tag === "text") {
            setAttrs(el, {
                fill: "#994444",
                "font-weight": "600",
                "letter-spacing": ".02em",
                "font-size": "12px",
            });
        }
        if (cls.includes("table-rect")) {
            setAttrs(el, {fill: "#f1f3f5", stroke: "#cfd4da"});
        }
        if (cls.includes("seat-divider")) {
            setAttrs(el, {fill: "#d1d5db"});
        }
        if (cls.includes("seat-forbidden-cross")) {
            setAttrs(el, {
                stroke: "#ef4444",
                "stroke-width": "1.5",
                "stroke-linecap": "round",
                opacity: "0.6",
            });
        }
        if (cls.includes("seat-name") && tag === "text") {
            setAttrs(el, {
                fill: "#212529",
                "dominant-baseline": "middle",
                "font-weight": "600",
            });
        }
        // Siège sélectionné → surlignage
        if (cls.includes("seat-selected")) {
            setAttrs(el, {stroke: "#ffc107", "stroke-width": "3"});
        }
        // Siège libre/occupé : ne pas écraser un fill déjà défini (ex: url(#forbidPattern))
        if (cls.includes("seat-free") && !el.hasAttribute("fill")) {
            setAttrs(el, {fill: "#ffffff", "fill-opacity": "0.6"});
        }
        if (cls.includes("seat-occupied") && !el.hasAttribute("fill")) {
            setAttrs(el, {fill: "#0b57d0", "fill-opacity": "0.12"});
        }
    });
}

/** Sérialise l’élément SVG en XML (avec prologue). */
function serializeSvg(svg) {
    const xml = new XMLSerializer().serializeToString(svg);
    return `<?xml version="1.0" encoding="UTF-8"?>\n${xml}`;
}

/* ==========================================================================
   Collecte des deux variantes de SVG (élève / prof)
   ========================================================================== */

/** SVG “vue élève” : identique à l’affichage à l’écran. */
function collectRoomSvgMarkupStudent() {
    const svgEl = document.getElementById("roomCanvas");
    if (!(svgEl instanceof SVGSVGElement)) return null;

    const clone = cloneCanvasSvg(svgEl);
    addWhiteBackground(clone);
    applyPresentationAttributes(clone); // <- pas de <style>, pas de style=

    return serializeSvg(clone);
}

/**
 * SVG “vue prof” : miroir vertical global + redressement local des <text>.
 * (texte lisible, positions miroir).
 */
function collectRoomSvgMarkupTeacher() {
    const svgEl = document.getElementById("roomCanvas");
    if (!(svgEl instanceof SVGSVGElement)) return null;

    const clone = cloneCanvasSvg(svgEl);
    addWhiteBackground(clone);

    const W = Number(clone.getAttribute("width") || "0");
    const H = Number(clone.getAttribute("height") || "0");
    if (!Number.isFinite(W) || !Number.isFinite(H) || W <= 0 || H <= 0) {
        applyPresentationAttributes(clone);
        return serializeSvg(clone);
    }

    const ns = "http://www.w3.org/2000/svg";
    const g = document.createElementNS(ns, "g");
    // miroir global
    g.setAttribute("transform", `translate(${W}, ${H}) scale(-1, -1)`);

    // Déplace tout (sauf le fond blanc tout juste ajouté) dans le groupe miroir
    Array.from(clone.childNodes).forEach((n) => {
        if (!(n instanceof Element)) return;
        const tag = n.tagName?.toLowerCase();
        const isBg = tag === "rect" && n.getAttribute("width") === "100%" && n.getAttribute("height") === "100%";
        if (isBg) return; // laisse le fond au niveau racine
        g.appendChild(n);
    });
    clone.appendChild(g);

    // Redressement local des textes
    g.querySelectorAll("text").forEach((t) => {
        const xAttr = t.getAttribute("x");
        const yAttr = t.getAttribute("y");
        if (xAttr != null && xAttr !== "" && !Number.isNaN(Number(xAttr))) {
            t.setAttribute("x", String(-Number(xAttr)));
        }
        if (yAttr != null && yAttr !== "" && !Number.isNaN(Number(yAttr))) {
            t.setAttribute("y", String(-Number(yAttr)));
        }
        // Tspan avec x explicite → miroir aussi
        t.querySelectorAll("tspan[x]").forEach((ts) => {
            const xx = Number(ts.getAttribute("x"));
            if (Number.isFinite(xx)) ts.setAttribute("x", String(-xx));
        });
        const prev = t.getAttribute("transform") || "";
        t.setAttribute("transform", `scale(-1,-1)${prev ? " " + prev : ""}`);
    });

    // Applique les attributs de présentation à la fin (sur tout le clone)
    applyPresentationAttributes(clone);

    return serializeSvg(clone);
}

/* ==========================================================================
   Construction du payload
   ========================================================================== */

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
        constraints: state.constraints,
        forbidden: Array.from(state.forbidden),
        placements: Object.fromEntries(state.placements),
        name_view: state.nameView,
    };
}

/* ==========================================================================
   UI export : utilitaires
   ========================================================================== */

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
   Export — envoi + liens
   ========================================================================== */

export async function startExport() {
    const btn = /** @type {HTMLButtonElement|null} */ ($("#btnExport"));
    const classInput = /** @type {HTMLInputElement|null} */ ($("#className"));

    const className = (classInput?.value || "").trim();
    if (!className) {
        classInput?.classList.add("is-invalid");
        classInput?.focus();
        return;
    }
    classInput?.classList.remove("is-invalid");

    const svgTxt = collectRoomSvgMarkupStudent();
    if (!svgTxt) {
        alert("Aucun plan de classe à exporter pour le moment.");
        return;
    }

    const body = JSON.stringify({...buildExportPayload(), class_name: className});

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
            const msg = (await r.json().catch(() => ({})))?.error || "export failed";
            throw new Error(msg);
        }

        const data = await r.json();
        const dl = data?.download || {};

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

        const s = dl.student || dl; // rétro-compat
        const t = dl.teacher || {};

        setDownloadLink(sPNG, s?.png);
        setDownloadLink(sPDF, s?.pdf);
        setDownloadLink(sSVG, s?.svg);

        setDownloadLink(tPNG, t?.png);
        setDownloadLink(tPDF, t?.pdf);
        setDownloadLink(tSVG, t?.svg);

        setDownloadLink(exJSON, dl?.json);
        setDownloadLink(exZIP, dl?.zip);

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

export function setupExportUI() {
    /** @type {HTMLInputElement|null} */
    const classInput = document.getElementById("className");
    /** @type {HTMLButtonElement|null} */
    const btn = document.getElementById("btnExport");

    if (classInput) {
        classInput.required = true;
        const onEdit = () => {
            syncExportButtonEnabled();
            if (classInput.value.trim().length > 0) {
                classInput.classList.remove("is-invalid");
            }
        };
        classInput.addEventListener("input", onEdit);
        classInput.addEventListener("change", onEdit);
    } else if (btn) {
        btn.disabled = false;
    }

    if (btn && !btn.dataset.wired) {
        btn.dataset.wired = "1";
        btn.addEventListener("click", (ev) => {
            ev.preventDefault();
            startExport();
        });
    }

    syncExportButtonEnabled();
}

/* ==========================================================================
   Auto-init
   ========================================================================== */

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => setupExportUI());
} else {
    setupExportUI();
}
