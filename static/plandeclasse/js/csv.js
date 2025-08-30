// static/plandeclasse/js/csv.js
"use strict";

/**
 * Module CSV : import tolérant Pronote (nouveau/ancien) + détection du genre.
 * On laisse le split prénom/nom au module utils.
 */

export function extractGender(cell /**: string */) /**: "F"|"M"|null */ {
    const raw = String(cell || "").trim();
    const lower = raw.toLowerCase();

    // Nouvel export Pronote : balises <i class="... icon_venus|icon_mars ...">
    if (lower.includes("icon_venus")) return "F";
    if (lower.includes("icon_mars")) return "M";

    // Nettoyage HTML générique
    const noTags = lower.replace(/<[^>]+>/g, "").replace(/"/g, "").trim();

    // Ancien export : lettres ou mots (fr/en)
    if (/^f(é|minin|emale)?$/.test(noTags)) return "F";   // f, féminin, female
    if (/^g$/.test(noTags)) return "M";                   // g = garçon
    if (/^m(asculin|ale)?$/.test(noTags)) return "M";     // m, masculin, male

    return null;
}

/**
 * Parse CSV pragmatique : détecte séparateur, colonne nom, et genre (header/heuristique).
 */
export function parseCSV(text /**: string */) /**: Array<{name:string, gender:"F"|"M"|null}> */ {
    const lines = text.split(/\r?\n/).filter((l) => l.trim() !== "");
    if (!lines.length) return [];

    const sep = lines[0].includes(";") ? ";" : ",";
    const header = lines[0].split(sep).map((h) => h.trim().toLowerCase());

    let idxName = header.findIndex((h) => ["nom", "élève", "eleve", "name"].includes(h));
    if (idxName === -1) idxName = 0;

    let idxGender = header.findIndex((h) => ["sexe", "genre", "gender"].includes(h));

    if (idxGender === -1 && lines.length > 1) {
        const maxProbe = Math.min(6, lines.length); // header + 5 lignes
        const scores = new Array(header.length).fill(0);
        for (let i = 1; i < maxProbe; i++) {
            const cols = lines[i].split(sep);
            for (let c = 0; c < cols.length; c++) {
                const g = extractGender(cols[c]);
                if (g === "F" || g === "M") scores[c] += 1;
            }
        }
        let best = -1, bestScore = 0;
        for (let c = 0; c < scores.length; c++) {
            if (scores[c] > bestScore) {
                best = c;
                bestScore = scores[c];
            }
        }
        if (bestScore > 0) idxGender = best;
    }

    const rows = [];
    for (let i = 1; i < lines.length; i++) {
        const cols = lines[i].split(sep);
        const rawName = (cols[idxName] || "").replace(/<[^>]+>/g, "").replace(/"/g, "").trim();
        if (!rawName) continue;
        let g = null;
        if (idxGender !== -1 && idxGender < cols.length) {
            g = extractGender(cols[idxGender]);
        }
        rows.push({name: rawName, gender: g});
    }
    return rows;
}
