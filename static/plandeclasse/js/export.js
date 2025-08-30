// static/plandeclasse/js/export.js
"use strict";

/**
 * Export du plan basé sur l'état courant (après ajustements manuels).
 * - Capture l’SVG rendu (#roomCanvas), y injecte un <style> autonome,
 * - Sérialise l’état (élèves, contraintes, placements…),
 * - Envoie au backend /plandeclasse/export pour fabriquer PNG/PDF/SVG/JSON/ZIP,
 * - Met à jour les liens d’export dans le DOM.
 *
 * UX :
 * - Le champ “Nom de la classe” est OBLIGATOIRE (bouton désactivé tant que vide).
 * - Feedback Bootstrap : .is-invalid si on tente d’exporter sans nom.
 */

import {state} from "./state.js";
import {$} from "./utils.js";

/* ==========================================================================
   Helpers internes
   ========================================================================== */

/**
 * Feuille de style minimale embarquée dans l’SVG exporté.
 * On reprend les classes utilisées par le rendu pour garantir un WYSIWYG.
 * @returns {string}
 */
function svgInlineStyles() {
    // NB : si vous changez les couleurs dans plandeclasse.css, gardez la cohérence ici.
    return `
.board-rect{fill:#1f2937;stroke:#111827;stroke-width:1.5}
.board-label{fill:#cbd5e1;font-weight:600;letter-spacing:.02em;font-size:12px}
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
 * Clone l’SVG affiché (#roomCanvas), y injecte un <style> et garantit width/height.
 * @returns {string|null} SVG XML complet prêt pour export, ou null si rien à exporter.
 */
function collectRoomSvgMarkup() {
    const svgEl = document.getElementById("roomCanvas");
    if (!(svgEl instanceof SVGSVGElement)) return null;

    // Clone profond pour ne pas modifier l’instance visible à l’écran
    const clone = /** @type {SVGSVGElement} */ (svgEl.cloneNode(true));

    // Standard : assurer le namespace + dimensions à partir du viewBox
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    const vbAttr = clone.getAttribute("viewBox");
    if (vbAttr) {
        const parts = vbAttr.split(/\s+/).map(Number);
        if (parts.length === 4 && Number.isFinite(parts[2]) && Number.isFinite(parts[3])) {
            clone.setAttribute("width", String(parts[2]));
            clone.setAttribute("height", String(parts[3]));
        }
    }

    // Injecter un <style> autonome (en tête) pour l’export
    const styleEl = document.createElementNS("http://www.w3.org/2000/svg", "style");
    styleEl.setAttribute("type", "text/css");
    styleEl.textContent = svgInlineStyles();
    clone.insertBefore(styleEl, clone.firstChild);

    // Sérialisation XML
    const xml = new XMLSerializer().serializeToString(clone);
    // En-tête XML pour les convertisseurs stricts
    return `<?xml version="1.0" encoding="UTF-8"?>\n${xml}`;
}

/**
 * Renseigne (ou masque) un lien de téléchargement selon l’URL fournie.
 * @param {HTMLAnchorElement|null} a
 * @param {string|undefined} url
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
   API publique du module
   ========================================================================== */

/**
 * Construit le payload d’export avec :
 * - nom de la classe (OBLIGATOIRE),
 * - SVG autonome (ce qui est réellement visible),
 * - état courant (élèves, contraintes, placements…).
 * @returns {object}
 */
export function buildExportPayload() {
    const classInput = /** @type {HTMLInputElement|null} */ ($("#className"));
    const class_name = (classInput?.value || "").trim();

    return {
        class_name,
        svg_markup: collectRoomSvgMarkup(), // ← l’SVG réel, autonome (avec <style>)
        schema: state.schema,
        students: state.students.map((s) => ({
            id: s.id,
            name: s.name,
            first: s.first,
            last: s.last,
            gender: s.gender ?? null,
        })),
        options: state.options,
        constraints: state.constraints,
        forbidden: Array.from(state.forbidden),
        placements: Object.fromEntries(state.placements),
        name_view: state.nameView,
    };
}

/**
 * Lance l’export via /plandeclasse/export et met à jour les liens d’export.
 * - Bloque si le nom de classe est vide (feedback .is-invalid).
 * - Tolérant aux absences d’éléments (le HTML peut évoluer).
 * @returns {Promise<void>}
 */
export async function startExport() {
    const btn = /** @type {HTMLButtonElement|null} */ ($("#btnExport"));
    const block = /** @type {HTMLElement|null} */ ($("#exportDownloads"));
    const exPNG = /** @type {HTMLAnchorElement|null} */ ($("#exPNG"));
    const exPDF = /** @type {HTMLAnchorElement|null} */ ($("#exPDF"));
    const exSVG = /** @type {HTMLAnchorElement|null} */ ($("#exSVG"));
    const exJSON = /** @type {HTMLAnchorElement|null} */ ($("#exJSON"));
    const exZIP = /** @type {HTMLAnchorElement|null} */ ($("#exZIP"));
    const classInput = /** @type {HTMLInputElement|null} */ ($("#className"));

    // 0) Nom de classe obligatoire
    const className = (classInput?.value || "").trim();
    if (!className) {
        classInput?.classList.add("is-invalid");
        classInput?.focus();
        return;
    }
    classInput?.classList.remove("is-invalid");

    // 1) Vérifie qu’on a bien un SVG à exporter
    const svgTxt = collectRoomSvgMarkup();
    if (!svgTxt) {
        alert("Aucun plan de classe à exporter pour le moment.");
        return;
    }

    // 2) Construire le body après vérifications (évite double sérialisation de l’SVG)
    const body = JSON.stringify({
        ...buildExportPayload(),
        class_name: className, // assurance
        svg_markup: svgTxt,
    });

    // 3) Feedback UI
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
            // backend renvoie 400 si nom vide ; message générique si autre souci
            const msg = (await r.json().catch(() => ({})))?.error || "export failed";
            throw new Error(msg);
        }
        const data = await r.json();
        const dl = data?.download || {};

        // 4) Renseigner les liens disponibles
        setDownloadLink(exPNG, dl.png);
        setDownloadLink(exPDF, dl.pdf);
        setDownloadLink(exSVG, dl.svg);
        setDownloadLink(exJSON, dl.json);
        setDownloadLink(exZIP, dl.zip);

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
   Auto-wiring (optionnel) : désactivation/activation du bouton et binding sûr
   ========================================================================== */

/**
 * Prépare l’UI d’export :
 * - bouton désactivé tant que le champ “Nom de la classe” est vide,
 * - enlève .is-invalid à la saisie,
 * - bind du clic sur #btnExport si pas déjà câblé.
 */
export function setupExportUI() {
    const classInput = /** @type {HTMLInputElement|null} */ ($("#className"));
    const btn = /** @type {HTMLButtonElement|null} */ ($("#btnExport"));

    if (classInput) {
        classInput.required = true;
        const sync = () => {
            const hasName = classInput.value.trim().length > 0;
            if (btn) btn.disabled = !hasName;
            if (hasName) classInput.classList.remove("is-invalid");
        };
        classInput.addEventListener("input", sync);
        // premier sync à l’ouverture
        sync();
    } else if (btn) {
        // pas de champ -> on laisse cliquable (fallback)
        btn.disabled = false;
    }

    if (btn && !btn.dataset.wired) {
        btn.dataset.wired = "1";
        btn.addEventListener("click", (ev) => {
            ev.preventDefault();
            startExport();
        });
    }
}

// Auto-init à l’ouverture de la page (sécurisé)
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => setupExportUI());
} else {
    setupExportUI();
}
