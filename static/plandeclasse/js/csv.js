// static/plandeclasse/js/csv.js
"use strict";

/**
 * Module CSV
 *  - Import tolérant (Pronote nouveau/ancien, Excel FR, Google Sheets…)
 *  - Auto-détection du séparateur : ; , ou tabulation
 *  - Parsing CSV correct : guillemets, échappement "", séparateurs dans champs
 *  - Détection du genre (F/M) depuis HTML Pronote ou textes FR/EN
 *  - Détection flexible des colonnes (Nom / Prénom / Nom complet)
 *
 * Sortie : Array<{ name: string, gender: "F"|"M"|null }>
 */

/* ==========================================================================
   Petits utilitaires
   ========================================================================== */

/** Enlève le BOM éventuel en début de fichier. */
function stripBOM(s) {
    return s && s.charCodeAt(0) === 0xfeff ? s.slice(1) : s;
}

/** Enlève les balises HTML et les guillemets superflus. */
function stripHtmlAndQuotes(s) {
    return String(s || "").replace(/<[^>]+>/g, "").replace(/"/g, "").trim();
}

/** Enlève les diacritiques (accents) puis passe en minuscule. */
function lowerNoDiacritics(s) {
    return String(s || "")
        .normalize("NFD")
        .replace(/\p{Diacritic}/gu, "")
        .toLowerCase()
        .trim();
}

/** Normalise un en-tête pour les comparaisons (fr/accents/punct). */
function normHeader(h) {
    return lowerNoDiacritics(stripHtmlAndQuotes(h)).replace(/\s+/g, " ");
}

/* ==========================================================================
   Détection séparateur + parsing CSV « vrai »
   ========================================================================== */

/** Teste plusieurs séparateurs et garde celui qui donne la meilleure cohérence. */
function sniffSeparator(lines) {
    const candidates = [";", ",", "\t"];
    const maxProbe = Math.min(10, lines.length);
    let best = ";";
    let bestScore = -1;

    for (const sep of candidates) {
        const widths = [];
        for (let i = 0; i < maxProbe; i++) {
            widths.push(csvSplit(lines[i], sep).length);
        }
        // Score = médiane des largeurs (on privilégie un nombre de colonnes > 1 et stable)
        widths.sort((a, b) => a - b);
        const median = widths[Math.floor(widths.length / 2)];
        const penalty = median <= 1 ? -1000 : 0;
        const score = median + penalty;
        if (score > bestScore) {
            bestScore = score;
            best = sep;
        }
    }
    return best;
}

/**
 * Découpe une ligne CSV selon `sep`, en respectant les guillemets.
 * - Supporte l’échappement CSV standard : "" à l’intérieur d’un champ guillemeté.
 * - Ne supprime pas les espaces internes (on nettoie plus tard).
 */
function csvSplit(line, sep) {
    const out = [];
    let cur = "";
    let inQ = false;

    for (let i = 0; i < line.length; i++) {
        const ch = line[i];

        if (inQ) {
            if (ch === '"') {
                // "" -> guillemet échappé
                if (line[i + 1] === '"') {
                    cur += '"';
                    i++;
                } else {
                    inQ = false;
                }
            } else {
                cur += ch;
            }
        } else {
            if (ch === '"') {
                inQ = true;
            } else if (ch === sep) {
                out.push(cur);
                cur = "";
            } else {
                cur += ch;
            }
        }
    }
    out.push(cur);
    return out;
}

/* ==========================================================================
   Détection du genre
   ========================================================================== */

/**
 * Déduit le genre depuis une cellule (HTML Pronote, lettres/mots FR/EN).
 * @param {string} cell
 * @returns {"F"|"M"|null}
 */
export function extractGender(cell) {
    const raw = String(cell || "").trim();
    const lower = raw.toLowerCase();

    // Pronote (icônes HTML)
    if (lower.includes("icon_venus")) return "F";
    if (lower.includes("icon_mars")) return "M";

    // Texte « propre »
    const noTags = stripHtmlAndQuotes(lower);

    // FR/EN : formes courantes
    if (/^(f|feminin|féminin|female|fille)$/u.test(noTags)) return "F";
    if (/^(g|garcon|gar\u00e7on)$/u.test(noTags)) return "M";
    if (/^(m|masculin|male)$/u.test(noTags)) return "M";


    // Abréviations fréquentes (H/F, M/F…)
    if (/^\s*f\s*\/\s*m\s*$/i.test(noTags)) return null; // intitulé
    if (/^\s*h\s*\/\s*f\s*$/i.test(noTags)) return null; // intitulé
    if (/^f\s*\/\s*h$/i.test(noTags)) return null;

    // Valeurs individuelles de type "H" (homme) / "F" (femme)
    if (/^h(omme)?$/.test(noTags)) return "M";

    return null;
}

/* ==========================================================================
   Parsing CSV et mapping des colonnes
   ========================================================================== */

/**
 * Détecte les colonnes NOM / PRENOM / NAME / GENDER à partir de l’en-tête.
 * Retourne des indices (ou -1 si absent).
 */
function detectColumns(header) {
    const H = header.map(normHeader);

    const isNameCol = (h) =>
        ["nom complet", "eleve", "el\u00e8ve", "name", "student", "full name", "nom/prenom", "prenom/nom"].includes(h) ||
        // Un simple "nom" est trop ambigu, on le traite séparément
        false;

    const idxFullName = H.findIndex(isNameCol);

    // Colonnes séparées
    const idxNom = H.findIndex((h) =>
        ["nom", "last name", "lastname", "surname", "family name", "nom de famille"].includes(h)
    );
    const idxPrenom = H.findIndex((h) =>
        ["prenom", "pr\u00e9nom", "first name", "firstname", "given name"].includes(h)
    );

    // Colonne genre
    const idxGender = H.findIndex((h) =>
        ["sexe", "genre", "gender", "sex"].includes(h)
    );

    // Fallback : si rien de clair, on considère la 1ère colonne comme "nom complet"
    let idxName = idxFullName;
    if (idxName === -1 && idxNom === -1 && idxPrenom === -1) {
        idxName = 0;
    }

    return {idxName, idxNom, idxPrenom, idxGender};
}

/**
 * Parse un CSV pragmatique :
 *  - détection du séparateur
 *  - entêtes FR/EN variées
 *  - lecture des champs guillemetés
 *  - extraction du genre
 *
 * @param {string} text
 * @returns {Array<{name:string, gender:"F"|"M"|null}>}
 */
export function parseCSV(text) {
    const raw = stripBOM(String(text || ""));
    const lines = raw
        .split(/\r?\n/)
        .map((l) => l.trimEnd())
        .filter((l) => l !== "");

    if (!lines.length) return [];

    const sep = sniffSeparator(lines);
    const header = csvSplit(lines[0], sep);

    const {idxName, idxNom, idxPrenom, idxGender} = detectColumns(header);

    /** @type {Array<{name:string, gender:"F"|"M"|null}>} */
    const rows = [];

    for (let i = 1; i < lines.length; i++) {
        const cols = csvSplit(lines[i], sep);

        const get = (idx) => (idx >= 0 && idx < cols.length ? cols[idx] : "");

        // Compose le nom
        let name = "";
        if (idxNom !== -1 || idxPrenom !== -1) {
            const prenom = stripHtmlAndQuotes(get(idxPrenom));
            const nom = stripHtmlAndQuotes(get(idxNom));
            name = [prenom, nom].filter(Boolean).join(" ").trim();
        } else {
            name = stripHtmlAndQuotes(get(idxName));
        }

        if (!name) continue;

        // Genre
        let gender = null;
        if (idxGender !== -1) {
            gender = extractGender(get(idxGender));
        }

        rows.push({name, gender});
    }

    return rows;
}
