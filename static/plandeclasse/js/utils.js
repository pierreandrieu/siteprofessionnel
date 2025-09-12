// static/plandeclasse/js/utils.js
"use strict";

/**
 * Module utilitaires : fonctions pures + helpers DOM.
 * Objectif : aucune dépendance au reste, réutilisable partout.
 *
 * CSP-friendly : aucun style inline, aucun accès DOM agressif.
 */

/* ==========================================================================
   Sélecteurs DOM
   ========================================================================== */

/**
 * Sélecteur court (équivalent `document.querySelector`).
 * @param {string} sel - sélecteur CSS
 * @returns {Element|null}
 */
export const $ = (sel) => document.querySelector(sel);

/* ==========================================================================
   Sièges / clés canoniques
   ========================================================================== */

/**
 * Construit la clé canonique d’un siège.
 * @param {number} x - index de table dans la rangée
 * @param {number} y - index de rangée
 * @param {number} s - index de siège dans la table
 * @returns {string} clé au format "x,y,s"
 */
export const keyOf = (x, y, s) => `${x},${y},${s}`;

/* ==========================================================================
   Noms & affichages
   ========================================================================== */

/**
 * Découpe un nom complet en { first, last }.
 * Règle : on considère que les premiers tokens 100% MAJUSCULES (accents ok)
 * appartiennent au NOM ; le reste forme le(s) prénom(s).
 *
 * Exemples :
 *  - "DUPONT Jean"        -> { first:"Jean", last:"DUPONT" }
 *  - "JEAN DUPONT"        -> { first:"DUPONT", last:"JEAN" } (rare mais voulu)
 *  - "Jean Dupont"        -> { first:"Jean Dupont", last:"" }
 *  - "D'ALMEIDA João"     -> { first:"João", last:"D'ALMEIDA" }
 *
 * @param {string} full
 * @returns {{first:string, last:string}}
 */
export function splitName(full) {
    const nettoye = String(full || "").trim().replace(/\s+/g, " ");
    if (!nettoye) return {first: "", last: ""};

    const tokens = nettoye.split(" ");

    /** Teste si un token est "MAJUSCULE" (en ignorant - ' ’) */
    const estMajuscule = (tok) => {
        const core = tok.replace(/[-'’]/g, "");
        const aDesLettres = /[A-ZÀ-ÖØ-Þ]/.test(core);
        return aDesLettres && core === core.toLocaleUpperCase("fr-FR");
    };

    let i = 0;
    while (i < tokens.length && estMajuscule(tokens[i])) i++;

    if (i === 0) {
        // Aucun token en majuscule → on ne sépare pas (prénoms+nom restent en first)
        return {first: nettoye, last: ""};
    }
    const last = tokens.slice(0, i).join(" ");
    const first = tokens.slice(i).join(" ").trim();
    return {first, last};
}

/**
 * Désambiguïsation générique : quand plusieurs items partagent la même clé
 * primaire, on ajoute un suffixe dérivé de la clé secondaire.
 *
 * Exemple : "Pierre" -> "Pierre A.", "Pierre B."
 *
 * @template T
 * @param {T[]} liste
 * @param {(item:T)=>string} clePrimaire      - ex: s => s.first
 * @param {(item:T)=>string} cleSecondaire    - ex: s => s.last
 * @param {(base:string, suffix:string)=>string} formatter - ex: (p,ext)=> ext?`${p} ${ext}.`:p
 * @returns {Map<number,string>} id -> libellé désambiguïsé (suppose item.id number)
 */
export function disambiguate(liste, clePrimaire, cleSecondaire, formatter) {
    const groupes = new Map(); // base -> T[]
    for (const item of liste) {
        const base = String(clePrimaire(item) || "");
        if (!groupes.has(base)) groupes.set(base, []);
        groupes.get(base).push(item);
    }

    const res = new Map(); // id -> libellé
    for (const [base, arr] of groupes.entries()) {
        if (arr.length === 1) {
            res.set(arr[0].id, base);
            continue;
        }
        const utilises = new Set();
        // Plusieurs homonymes : on étend avec des préfixes de la clé secondaire
        for (const item of arr) {
            const sec = String(cleSecondaire(item) || "");
            let n = 1;
            while (true) {
                const ext = sec.slice(0, n);
                const candidat = formatter(base, ext);
                if (!utilises.has(candidat) && candidat.trim() !== "") {
                    utilises.add(candidat);
                    res.set(item.id, candidat);
                    break;
                }
                n += 1;
                // sécurité (évite boucle infinie si sec="")
                if (n > sec.length + 5) {
                    const fallback = formatter(base, String(item.id));
                    res.set(item.id, utilises.has(fallback) ? `${base} ${item.id}` : fallback);
                    utilises.add(fallback);
                    break;
                }
            }
        }
    }
    return res;
}

/**
 * Construit les trois variantes d’affichage : prénom / nom / les deux.
 * - `firstMap` : "Jean" / "Jean D."
 * - `lastMap`  : "DUPONT" / "DUPONT J."
 * - `bothMap`  : "Jean\nDUPONT"
 *
 * @param {Array<{id:number, first:string, last:string}>} students
 * @returns {{firstMap:Map<number,string>, lastMap:Map<number,string>, bothMap:Map<number,string>}}
 */
export function buildDisplayMaps(students) {
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

/* ==========================================================================
   Outils calcul / tri / normalisation
   ========================================================================== */

/**
 * Distance de Manhattan maximale sur la "grille" salle.
 * NB : approximation : on prend (#rangées - 1) + (max #tables - 1).
 *
 * @param {number[][]} schema
 * @returns {number}
 */
export function computeMaxManhattan(schema) {
    const rangs = Array.isArray(schema) ? schema.length : 0;
    if (!rangs) return 0;
    const maxTables = Math.max(...schema.map((r) => r.length || 0));
    return Math.max(0, rangs - 1) + Math.max(0, maxTables - 1);
}

/** Collator FR pour un tri insensible aux accents/ponctuation. */
export const frNameCollator = new Intl.Collator("fr", {
    sensitivity: "base",
    ignorePunctuation: true,
});

/**
 * Tri : NOM puis prénom (avec collator FR).
 * @param {{first?:string,last?:string}} a
 * @param {{first?:string,last?:string}} b
 * @returns {number}
 */
export function compareByLastThenFirst(a, b) {
    const la = String(a.last || "").trim();
    const lb = String(b.last || "").trim();
    const c1 = frNameCollator.compare(la, lb);
    if (c1 !== 0) return c1;
    const fa = String(a.first || "").trim();
    const fb = String(b.first || "").trim();
    return frNameCollator.compare(fa, fb);
}

/**
 * Normalise un texte pour la recherche tolérante :
 * - NFD + suppression des diacritiques,
 * - minuscules,
 * - compactage ponctuation/espaces en simple espace.
 *
 * @param {string} str
 * @returns {string}
 */
export function norm(str) {
    return String(str || "")
        .normalize("NFD")
        .replace(/\p{Diacritic}/gu, "")  // enlève les accents
        .toLowerCase()
        .replace(/[-'’.\s]+/g, " ")      // compacte ponctuation/espaces
        .trim();
}
