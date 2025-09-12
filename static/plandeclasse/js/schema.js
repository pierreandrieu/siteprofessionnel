// static/plandeclasse/js/schema.js
"use strict";

/**
 * Module Schema : (re)construction du plan (rangées/tables/capacités) et
 * nettoyage des placements/interdits/cohérence avec contraintes.
 *
 * Sécurité (CSP) :
 *  - Pas de style inline et pas d’HTML injecté via innerHTML pour les éléments dynamiques.
 */

import {state as etat} from "./state.js";
import {
    renderRoom as rendreSalle,
    renderStudents as rendreEleves,
    updateBanButtonLabel as majBoutonBan
} from "./render.js";
import {renderConstraints as rendreContraintes} from "./constraints.js";

/* ==========================================================================
   Recalage après changement de schéma
   ========================================================================== */

/**
 * Recalage des placements/interdits/contraintes après un changement de schéma
 * (sans reconstruire etat.schema). Les capacités négatives sont des "trous".
 *
 * Effets :
 * - purge les affectations devenues invalides (hors bornes / sur table-trou / hors capacité),
 * - reconstruit proprement la liste des sièges interdits + contraintes forbid_seat,
 * - rafraîchit l’UI (salle/élèves/contraintes/boutons + mini-éditeur de rangées).
 */
export function reconcileAfterSchemaChange() {
    const nouveauxPlacements = new Map();
    const nouvelIndexInverse = new Map();

    // Recalage des affectations existantes
    for (const [cleSiege, sid] of etat.placements.entries()) {
        const [x, y, s] = cleSiege.split(",").map(Number);
        if (y < etat.schema.length && x < etat.schema[y].length) {
            const capacite = etat.schema[y][x];
            if (capacite > 0 && s < capacite) {
                nouveauxPlacements.set(cleSiege, sid);
                nouvelIndexInverse.set(sid, cleSiege);
            }
        }
    }
    etat.placements = nouveauxPlacements;
    etat.placedByStudent = nouvelIndexInverse;

    // Recalage des sièges interdits (+ contraintes forbid_seat)
    const nouveauxInterdits = new Set();
    const contraintesInterdits = [];
    for (const cleSiege of etat.forbidden) {
        const [x, y, s] = cleSiege.split(",").map(Number);
        if (y < etat.schema.length && x < etat.schema[y].length) {
            const capacite = etat.schema[y][x];
            if (capacite > 0 && s < capacite) {
                nouveauxInterdits.add(cleSiege);
                contraintesInterdits.push({
                    type: "forbid_seat",
                    x, y, s,
                    human: `siège (x=${x}, y=${y}, s=${s}) doit rester vide`,
                    key: cleSiege,
                });
            }
        }
    }
    etat.forbidden = nouveauxInterdits;

    // Remplace toutes les forbid_seat par la version recalculée
    etat.constraints = etat.constraints
        .filter((c) => c.type !== "forbid_seat")
        .concat(contraintesInterdits);

    // Rafraîchit l’IHM
    rendreSalle();
    rendreEleves();
    rendreContraintes();
    majBoutonBan();
    renderRowsEditor();
}

/* ==========================================================================
   Application d’un schéma "rectangulaire"
   ========================================================================== */

/**
 * Construit un schéma à partir d’un nombre de rangées et d’une chaîne de capacités.
 * Exemple : rows=3, capacitiesStr="2,3,2" → [[2,3,2],[2,3,2],[2,3,2]]
 *
 * @param {number} rows - nombre de rangées
 * @param {string} capacitiesStr - liste des capacités séparées par virgules/espaces ; négatif = "trou"
 */
export function applySchema(rows /**: number */, capacitiesStr /**: string */) {
    const capacites = capacitiesStr
        .split(/[,\s]+/)
        .map((s) => Number(s.trim()))
        .filter((n) => Number.isFinite(n) && n !== 0);

    // Reconstruit toutes les rangées à l’identique
    const nouveauSchema = Array.from({length: rows}, () => capacites.slice());
    etat.schema = nouveauSchema;

    // Recale le reste sans retoucher au schéma
    reconcileAfterSchemaChange();
}

/* ==========================================================================
   Réinitialisation complète de la salle (schéma)
   ========================================================================== */

/**
 * Réinitialise la **salle** (schéma) et recale l’état dépendant.
 *
 * Effets :
 * - Vide le schéma (etat.schema = [])
 * - Recalage via reconcileAfterSchemaChange() : nettoie placements et
 *   reconstruit proprement l’état “sièges interdits/contraintes de siège”
 * - Efface la sélection courante
 * - Re-rend l’UI (salle/élèves/contraintes) + met à jour les boutons
 *
 * Conserve :
 * - Les contraintes non structurelles (unaires/binaires) restent telles quelles
 *   (inutiles avec une salle vide, mais on n’efface pas la “liste de souhaits”)
 */
export function resetRoomSchema() {
    // Vide le schéma
    etat.schema = [];

    // La sélection n’a plus de sens
    etat.selection.studentId = null;
    etat.selection.seatKey = null;

    // Recalage général (purge placements + reclasse les “forbid_seat” au propre)
    reconcileAfterSchemaChange();

    // (reconcileAfterSchemaChange fait déjà les render + updateBanButtonLabel + editor)
}

/* ==========================================================================
   Mini-éditeur des rangées (liste + suppression)
   ========================================================================== */

/**
 * Rendu du petit éditeur de rangées (aperçu + bouton supprimer).
 * Utilise uniquement des nœuds DOM et textContent (pas d’innerHTML) pour CSP/XSS.
 */
export function renderRowsEditor() {
    const racine = document.getElementById("rowsEditor");
    if (!racine) return;
    racine.textContent = "";

    const lignes = etat.schema;
    if (!Array.isArray(lignes) || lignes.length === 0) {
        const vide = document.createElement("div");
        vide.className = "text-muted small";
        vide.textContent = "aucune rangée pour le moment.";
        racine.appendChild(vide);
        return;
    }

    lignes.forEach((capacites, y) => {
        const item = document.createElement("div");
        item.className = "d-flex align-items-center justify-content-between border rounded px-2 py-1";

        // Bloc libellé : <strong>rangée N</strong> (<span class="text-muted">(…)</span>)
        const blocLibelle = document.createElement("div");

        const fort = document.createElement("strong");
        fort.textContent = `rangée ${y + 1}`;

        const spanDetails = document.createElement("span");
        spanDetails.className = "text-muted";
        const joli = capacites.map((c) => (c > 0 ? String(c) : `trou(${Math.abs(c)})`)).join(" · ");
        spanDetails.textContent = ` (${joli})`;

        blocLibelle.appendChild(fort);
        blocLibelle.appendChild(document.createTextNode(" "));
        blocLibelle.appendChild(spanDetails);

        // Bouton supprimer
        const btnSuppr = document.createElement("button");
        btnSuppr.className = "btn btn-sm btn-outline-danger";
        btnSuppr.setAttribute("aria-label", `Supprimer la rangée ${y + 1}`);
        btnSuppr.textContent = "🗑";
        btnSuppr.addEventListener("click", () => {
            if (!confirm(`Supprimer la rangée ${y + 1} ?`)) return;
            deleteRowAt(y);
        });

        item.appendChild(blocLibelle);
        item.appendChild(btnSuppr);
        racine.appendChild(item);
    });
}

/**
 * Supprime la rangée d’index y et recale l’état.
 * @param {number} y - index de rangée (0-based)
 */
export function deleteRowAt(y) {
    if (y < 0 || y >= etat.schema.length) return;
    // Retire la rangée
    etat.schema.splice(y, 1);
    // Recalage des placements/interdits/forbid_seat existants (+ rerenders & editor)
    reconcileAfterSchemaChange();
}
