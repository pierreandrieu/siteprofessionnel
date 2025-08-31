// static/plandeclasse/js/utils.js
"use strict";

/**
 * Module Utils : fonctions pures et utilitaires DOM.
 * Objectif : zéro dépendance au reste, réutilisable partout.
 */

/** Sélecteur DOM court. */
export const $ = (sel /**: string */) /**: Element|null */ => document.querySelector(sel);

/** Clé canonique d’un siège. */
export const keyOf = (x /**: number */, y /**: number */, s /**: number */) /**: string */ =>
    `${x},${y},${s}`;

/** Découpe « NOM EN MAJUSCULES » + « Prénoms » selon règle décrite. */
export function splitName(full /**: string */) /**: {first:string,last:string} */ {
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

/** Disambiguation générique (ex: "Pierre A." / "Pierre B."). */
export function disambiguate(list, primaryKey, secondaryKey, format) {
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

/** Construit les affichages possibles (prénom/nom/les deux) sans dépendre de l’état. */
export function buildDisplayMaps(students /**: Array<{id:number,first:string,last:string}> */) {
    const firstMap = disambiguate(
        students,
        (s) => s.first,
        (s) => s.last,
        (p, ext) => (ext ? `${p} ${ext}.` : p),
    );
    const lastMap = disambiguate(
        students,
        (s) => s.last || s.first,
        (s) => s.first,
        (p, ext) => (ext ? `${p} ${ext}.` : p),
    );
    const bothMap = new Map(students.map((s) => [s.id, `${s.first}\n${s.last}`.trim()]));
    return {firstMap, lastMap, bothMap};
}

/** Distance max de Manhattan sur la salle (utile pour borne de contraintes). */
export function computeMaxManhattan(schema /**: number[][] */) /**: number */ {
    const rows = schema.length;
    if (!rows) return 0;
    const maxCols = Math.max(...schema.map((r) => r.length));
    return (rows - 1) + (maxCols - 1);
}

export const frNameCollator = new Intl.Collator('fr', {sensitivity: 'base', ignorePunctuation: true});

export function compareByLastThenFirst(a, b) {
    const c1 = frNameCollator.compare((a.last || '').trim(), (b.last || '').trim());
    return c1 !== 0 ? c1 : frNameCollator.compare((a.first || '').trim(), (b.first || '').trim());
}

export function norm(str) {
    return String(str || "")
        .normalize("NFD")
        .replace(/\p{Diacritic}/gu, "")      // enlève les accents
        .toLowerCase()
        .replace(/[-'’.\s]+/g, " ")          // compacte ponctuation/espaces
        .trim();
}