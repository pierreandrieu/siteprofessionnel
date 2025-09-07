// static/plandeclasse/js/state.js
"use strict";

/**
 * Module État : centralise l’état de l’UI.
 * Ce fichier reste en JavaScript natif ; les types sont fournis en JSDoc
 * pour l’autocomplétion et les vérifications via TypeScript/VS Code.
 */

/**
 * @typedef {Object} Student
 * @property {number} id              // Identifiant interne
 * @property {string} name            // Nom complet tel qu’importé (brut)
 * @property {"F"|"M"|null} gender    // Genre si détecté (F/M) ou null
 * @property {string} first           // Prénom(s) nettoyé(s)
 * @property {string} last            // NOM (majuscule) si présent
 */

/**
 * @typedef {Object} Constraint
 * @property {string} type
 * @property {number} [a]
 * @property {number} [b]
 * @property {number} [x]
 * @property {number} [y]
 * @property {number} [s]
 * @property {number} [k]
 * @property {number} [d]
 * @property {string} [human]
 * @property {string} [key]
 * @property {string} type  // "front_rows" | "back_rows" | "solo_table" | "empty_neighbor" | "no_adjacent" | "same_table" | "far_apart" | "forbid_seat"
 *
 */

/**
 * @typedef {Object} UIState
 * @property {Student[]} students
 * @property {{ studentId: number|null, seatKey: string|null }} selection
 * @property {number[][]} schema                        // [[2,3,2], ...]
 * @property {Set<string>} forbidden                    // clés "x,y,s"
 * @property {Map<string, number>} placements           // seatKey -> studentId
 * @property {Map<number, string>} placedByStudent      // studentId -> seatKey
 * @property {{ solver: "cpsat"|"asp"|"random", prefer_mixage: boolean, prefer_alone: boolean, time_budget_ms: number }} options
 * @property {"first"|"last"|"both"} nameView
 * @property {Constraint[]} constraints
 */

/** @type {UIState} */
export const state = {
    // Liste complète des élèves importés (CSV)
    students: [],

    // Sélection courante : élève ou siège (clé "x,y,s")
    selection: {studentId: /** @type {number|null} */ (null), seatKey: /** @type {string|null} */ (null)},

    // Schéma de la salle : tableau de rangées ; chaque rangée = liste des capacités des tables
    schema: [],

    // Sièges explicitement interdits (clé "x,y,s")
    forbidden: new Set(),

    // Affectations actuelles : seatKey -> studentId
    placements: new Map(),

    // Inverse des affectations : studentId -> seatKey
    placedByStudent: new Map(),

    // Options transmises au solveur
    options: {
        solver: "cpsat",
        prefer_mixage: false,
        prefer_alone: false,
        lock_placements: false,
        time_budget_ms: 60_000, // lisible grâce au séparateur numérique
    },

    // Mode d’affichage des noms dans le plan
    nameView: "first",

    // Contraintes UI (lisibles par l’humain) à envoyer au solveur
    constraints: [],
};
