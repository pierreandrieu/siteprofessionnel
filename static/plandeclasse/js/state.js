// static/plandeclasse/js/state.js
"use strict";

/**
 * Module État : centralise l’état de l’UI.
 * - Objet unique et mutable exporté : `state`
 * - Types JSDoc fournis pour l’autocomplétion et les vérifications (VS Code/TS)
 * - Aucune dépendance externe.
 */

/* ==========================================================================
   Typages JSDoc (purement informatifs, utiles à l’IDE)
   ========================================================================== */

/** Clé canonique d’un siège (x,y,s) sous forme "x,y,s". */
/// typedef {string} SeatKey

/**
 * Types de contraintes "élève".
 * @typedef {"front_rows"|"back_rows"|"solo_table"|"empty_neighbor"|"no_adjacent"|"same_table"|"far_apart"|"forbid_seat"} ConstraintType
 */

/**
 * Éléments spéciaux stockés dans `constraints` pour l’IHM :
 * - `_batch_marker_` : marqueur de lot (UI only)
 * - `_objective_`    : rappel d’un objectif global (export TXT)
 * @typedef {"_batch_marker_"|"_objective_"} UiOnlyConstraintType
 */

/**
 * Élève (nettoyé à l’import).
 * @typedef {Object} Student
 * @property {number} id           - Identifiant interne
 * @property {string} name         - Nom complet brut tel qu’importé
 * @property {"F"|"M"|null} gender - Genre si détecté (F/M) ou null
 * @property {string} first        - Prénom(s) nettoyé(s)
 * @property {string} last         - NOM (majuscule) si présent
 */

/**
 * Contrainte "métier" (solveur) ou marqueur UI.
 * Les champs optionnels dépendent du type.
 * @typedef {Object} Constraint
 * @property {ConstraintType|UiOnlyConstraintType} type
 * @property {number} [a]      - id élève A (contraintes binaires)
 * @property {number} [b]      - id élève B (contraintes binaires)
 * @property {number} [x]      - abscisse table (forbid_seat)
 * @property {number} [y]      - ordonnée rangée (forbid_seat)
 * @property {number} [s]      - index siège dans la table (forbid_seat)
 * @property {number} [k]      - nombre de rangées (front/back_rows)
 * @property {number} [d]      - distance Manhattan min (far_apart)
 * @property {string} [human]  - libellé lisible (UI / export TXT)
 * @property {string} [key]    - clé de siège (x,y,s) pour forbid_seat
 * @property {string} [batch_id] - identifiant de lot (UI : groupage/suppression)
 * @property {number} [count]  - taille du lot (UI : _batch_marker_)
 */

/**
 * Options solveur/affichage.
 * @typedef {Object} UiOptions
 * @property {"cpsat"|"asp"|"random"} solver
 * @property {boolean} prefer_mixage     - favoriser la mixité (option soft)
 * @property {boolean} prefer_alone      - favoriser les élèves sans voisin (option soft)
 * @property {boolean} lock_placements   - verrouiller les placements existants (si implémenté côté solveur)
 * @property {number}  time_budget_ms    - budget de calcul en millisecondes
 */

/**
 * Sélection courante (élève OU siège).
 * @typedef {Object} UiSelection
 * @property {number|null} studentId
 * @property {SeatKey|null} seatKey
 */

/**
 * État global de l’IHM.
 * @typedef {Object} UIState
 * @property {Student[]} students
 * @property {UiSelection} selection
 * @property {number[][]} schema                 - schéma de salle : chaque rangée = liste des capacités (négatif = trou)
 * @property {Set<SeatKey>} forbidden            - sièges explicitement interdits
 * @property {Map<SeatKey, number>} placements   - seatKey -> studentId
 * @property {Map<number, SeatKey>} placedByStudent - studentId -> seatKey
 * @property {UiOptions} options
 * @property {"first"|"last"|"both"} nameView
 * @property {Constraint[]} constraints
 */

/* ==========================================================================
   Valeurs par défaut (lisibles et centralisées)
   ========================================================================== */

/** @type {UiOptions} */
const OPTIONS_DEFAUT = {
    solver: "cpsat",
    prefer_mixage: false,
    prefer_alone: false,
    lock_placements: false,
    time_budget_ms: 60_000, // lisible grâce au séparateur numérique
};

/** @type {UiSelection} */
const SELECTION_VIDE = {studentId: null, seatKey: null};

/* ==========================================================================
   Objet d’état exporté (mutable par les autres modules)
   ========================================================================== */

/** @type {UIState} */
export const state = {
    // Liste complète des élèves importés (CSV)
    students: [],

    // Sélection courante : élève ou siège (clé "x,y,s")
    selection: {...SELECTION_VIDE},

    // Schéma de la salle : tableau de rangées ; chaque rangée = liste des capacités des tables
    schema: [],

    // Sièges explicitement interdits (clé "x,y,s")
    forbidden: new Set(),

    // Affectations actuelles : seatKey -> studentId
    placements: new Map(),

    // Inverse des affectations : studentId -> seatKey
    placedByStudent: new Map(),

    // Options transmises au solveur
    options: {...OPTIONS_DEFAUT},

    // Mode d’affichage des noms dans le plan
    nameView: "first",

    // Contraintes UI (lisibles par l’humain) + marqueurs UI → envoyés au solveur (les _batch/_objective_ sont filtrés côté backend si nécessaire)
    constraints: [],
};

/* ==========================================================================
   (Optionnel) petites aides pour d’autres modules
   ========================================================================== */

/**
 * Réinitialise la sélection courante.
 * Pratique pour éviter de réécrire l’objet à la main.
 */
export function clearSelection() {
    state.selection.studentId = null;
    state.selection.seatKey = null;
}

/**
 * Réinitialise les options vers les valeurs par défaut.
 * Utile si on veut offrir un bouton "réinitialiser options".
 */
export function resetOptionsToDefault() {
    state.options = {...OPTIONS_DEFAUT};
}
