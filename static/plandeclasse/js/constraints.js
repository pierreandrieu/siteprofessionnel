// static/plandeclasse/js/constraints.js
"use strict";

/**
 * Module Constraints (version groupe, CSP-safe)
 *
 * Fonctions exposées :
 * - refreshConstraintSelectors() : remplit la liste d’élèves (desktop + mobile)
 * - onConstraintTypeChange()     : gère l’affichage/borne du champ paramètre (k/d)
 * - addConstraint()              : ajoute des contraintes pour un groupe sélectionné
 * - cancelConstraintForm()       : remet à zéro le formulaire (sélections/paramètres)
 * - renderConstraints()          : affiche les lots + contraintes individuelles avec suppression
 *
 * Notes :
 * - Les contraintes créées “en lot” reçoivent toutes un batch_id commun et un
 *   marqueur spécial { type: "_batch_marker_", batch_id, human, count } pour l’IHM.
 * - Les contraintes “forbid_seat” (issues des sièges interdits) restent individuelles,
 *   et leur suppression met aussi à jour state.forbidden.
 */

import {state} from "plandeclasse/state";
import {$, compareByLastThenFirst, computeMaxManhattan} from "plandeclasse/utils";
import {renderRoom, renderStudents, updateBanButtonLabel} from "plandeclasse/render";

/* ==========================================================================
   Helpers internes
   ========================================================================== */

/** Retourne la liste d’élèves triée NOM puis prénom. */
function getStudentsSorted() {
    return [...state.students].sort(compareByLastThenFirst);
}

/** Retourne les IDs sélectionnés (desktop : <select multiple>, mobile : checkboxes). */
function getSelectedStudentIds() {
    const isMobile = window.matchMedia("(max-width: 575.98px)").matches;
    if (isMobile) {
        const inputs = document.querySelectorAll("#cstStudentsMobile input[type=checkbox]:checked");
        return Array.from(inputs).map((i) => Number(i.value));
    }
    const sel = /** @type {HTMLSelectElement|null} */ (document.getElementById("cstStudents"));
    if (!sel) return [];
    return Array.from(sel.selectedOptions).map((o) => Number(o.value));
}

/** Formatte “Alice DURAND, Bob MARTIN et Chloé DUPONT”. */
function formatNamesList(ids /**: number[] */) /**: string */ {
    const byId = new Map(state.students.map((s) => [s.id, s]));
    const names = ids
        .map((id) => byId.get(id))
        .filter(Boolean)
        .map((s) => `${s.first} ${s.last}`.trim());

    if (names.length <= 1) return names[0] || "";
    const head = names.slice(0, -1).join(", ");
    return `${head} et ${names[names.length - 1]}`;
}

/** Toutes les paires non ordonnées de 2 éléments parmi ids. */
function pairs(ids /**: number[] */) /**: Array<[number,number]> */ {
    const out = [];
    for (let i = 0; i < ids.length; i++) {
        for (let j = i + 1; j < ids.length; j++) out.push([ids[i], ids[j]]);
    }
    return out;
}

/** ID de lot simple et suffisamment unique pour l’IHM. */
function newBatchId() {
    return "b" + Date.now().toString(36) + Math.floor(Math.random() * 1e6).toString(36);
}

/** Affiche/masque le bloc du paramètre (k/d). */
function toggleParamBlock(show) {
    const wrap = document.getElementById("cstParamInner") || document.getElementById("cstParamWrap");
    if (!wrap) return;
    if (show) {
        wrap.classList.remove("d-none");
        wrap.removeAttribute("hidden");
    } else {
        wrap.classList.add("d-none");
        wrap.setAttribute("hidden", "true");
    }
}

/** Récupère le nom affichable d’un élève à partir de son id. */
function displayNameById(id /**: number */) /**: string */ {
    const s = state.students.find((st) => st.id === id);
    return s ? `${s.first} ${s.last}`.trim() : `élève #${id}`;
}

/** Humanise une contrainte individuelle non batchée (fallback legacy). */
function humanizeConstraint(c /**: any */) /**: string */ {
    switch (c.type) {
        case "exact_seat":
            return `${displayNameById(c.a)} doit être exactement en (x=${c.x}, y=${c.y}, s=${c.s})`;
        case "forbid_seat":
            return c.human || `siège (x=${c.x}, y=${c.y}, s=${c.s}) doit rester vide`;
        case "front_rows":
            return `${displayNameById(c.a)} doit être dans les premières rangées (k=${c.k ?? "?"})`;
        case "back_rows":
            return `${displayNameById(c.a)} doit être dans les dernières rangées (k=${c.k ?? "?"})`;
        case "solo_table":
            return `${displayNameById(c.a)} doit être isolé·e sur une table`;
        case "empty_neighbor":
            return `${displayNameById(c.a)} doit avoir au moins un siège vide à côté`;
        case "no_adjacent":
            return `${displayNameById(c.a)} ne doit avoir aucun·e voisin·e adjacent·e`;
        case "same_table":
            return `${displayNameById(c.a)} et ${displayNameById(c.b)} doivent être à la même table`;
        case "far_apart":
            return `${displayNameById(c.a)} et ${displayNameById(c.b)} doivent être éloigné·e·s d’au moins d=${c.d ?? "?"}`;
        default:
            return c.human || c.type || "(contrainte)";
    }
}

/** Bascule libellés des boutons selon ajout/édition. */
function setConstraintButtonsEditing(editing) {
    const btnAdd = /** @type {HTMLButtonElement|null} */ (document.getElementById("btnAddConstraint"));
    const btnCancel = /** @type {HTMLButtonElement|null} */ (document.getElementById("btnCancelConstraint"));
    if (btnAdd) btnAdd.textContent = editing ? "Enregistrer les modifications" : "Ajouter";
    if (btnCancel) btnCancel.textContent = editing ? "Annuler l’édition" : "Réinitialiser";
}

/** Coche/selectionne programmatique des élèves dans les deux UIs (desktop+mobile). */
function applyIdsToSelectors(ids /**: number[] */) {
    const set = new Set(ids.map(Number));

    const sel = /** @type {HTMLSelectElement|null} */ (document.getElementById("cstStudents"));
    if (sel) {
        Array.from(sel.options).forEach(opt => {
            opt.selected = set.has(Number(opt.value));
        });
    }
    const mob = /** @type {HTMLElement|null} */ (document.getElementById("cstStudentsMobile"));
    if (mob) {
        mob.querySelectorAll('input[type="checkbox"]').forEach((i) => {
            /** @type {HTMLInputElement} */ (i).checked = set.has(Number(i.value));
        });
    }
}

/** Devine si un type est unaire/binaire. */
function isUnaryType(t /**: string */) {
    return ["front_rows", "back_rows", "solo_table", "empty_neighbor", "no_adjacent"].includes(t);
}


/* ==========================================================================
   Sélecteurs d’élèves (desktop + mobile)
   ========================================================================== */

/** Remplit la liste d’élèves en conservant la sélection courante. */
export function refreshConstraintSelectors() {
    // Desktop : <select multiple>
    const sel = /** @type {HTMLSelectElement|null} */ (document.getElementById("cstStudents"));
    // Mobile : liste de checkboxes
    const mob = /** @type {HTMLElement|null} */ (document.getElementById("cstStudentsMobile"));

    const studentsSorted = getStudentsSorted();
    const previouslySelected = new Set(getSelectedStudentIds());

    if (sel) {
        sel.innerHTML = "";
        for (const st of studentsSorted) {
            const opt = document.createElement("option");
            opt.value = String(st.id);
            opt.textContent = `${st.first} ${st.last}`.trim();
            if (previouslySelected.has(st.id)) opt.selected = true;
            sel.appendChild(opt);
        }
    }

    if (mob) {
        mob.innerHTML = "";
        for (const st of studentsSorted) {
            const wrap = document.createElement("label");
            wrap.className = "list-group-item d-flex align-items-center gap-2 py-2";

            const input = document.createElement("input");
            input.type = "checkbox";
            input.className = "form-check-input m-0";
            input.value = String(st.id);
            input.checked = previouslySelected.has(st.id);

            const txt = document.createElement("span");
            txt.className = "flex-grow-1";
            txt.textContent = `${st.first} ${st.last}`.trim();

            wrap.appendChild(input);
            wrap.appendChild(txt);
            mob.appendChild(wrap);
        }
    }
}

/* ==========================================================================
   Formulaire : type/k/d + reset
   ========================================================================== */

/** Met à jour l’UI du paramètre selon le type (k pour front/back, d pour far_apart). */
export function onConstraintTypeChange() {
    const typeSel = /** @type {HTMLSelectElement|null} */ (document.getElementById("constraintType"));
    const pLabel = /** @type {HTMLElement|null} */        (document.getElementById("cstParamLabel"));
    const pHelp = /** @type {HTMLElement|null} */        (document.getElementById("cstParamHelp"));
    const pInput = /** @type {HTMLInputElement|null} */   (document.getElementById("cstParam"));
    if (!typeSel || !pLabel || !pHelp || !pInput) return;

    const t = typeSel.value;
    const needsK = t === "front_rows" || t === "back_rows";
    const needsD = t === "far_apart";

    if (needsK) {
        toggleParamBlock(true);
        pLabel.textContent = "k (nombre de rangées)";
        pInput.min = "1";
        pInput.removeAttribute("max");
        pInput.step = "1";
        if (!pInput.value) pInput.value = "1";
        pHelp.textContent = "";
        return;
    }

    if (needsD) {
        toggleParamBlock(true);
        const maxD = computeMaxManhattan(state.schema) || 0;
        pLabel.textContent = "distance d (Manhattan)";
        pInput.min = "2";
        pInput.step = "1";

        if (Number.isFinite(maxD) && maxD >= 3) {
            pInput.max = String(maxD);
            pHelp.textContent = `valeur ≤ ${maxD} pour cette salle`;
        } else {
            pInput.removeAttribute("max");
            pHelp.textContent = "";
        }

        const cur = Number(pInput.value);
        pInput.value = Number.isFinite(cur) && cur >= 2 ? String(cur) : "2";
        return;
    }

    // Pas de paramètre
    toggleParamBlock(false);
    pLabel.textContent = "Paramètre";
    pInput.value = "";
    pInput.removeAttribute("min");
    pInput.removeAttribute("max");
    pInput.removeAttribute("step");
    pHelp.textContent = "";
}

/** Réinitialise le formulaire (sélections, type, paramètre) et remet le focus. */
export function cancelConstraintForm() {
    // Desktop
    const sel = /** @type {HTMLSelectElement|null} */ (document.getElementById("cstStudents"));
    if (sel) sel.selectedIndex = -1;

    // Mobile
    const mob = /** @type {HTMLElement|null} */ (document.getElementById("cstStudentsMobile"));
    if (mob) {
        mob.querySelectorAll('input[type="checkbox"]').forEach((i) => {
            /** @type {HTMLInputElement} */ (i).checked = false;
        });
    }
    // Si on était en mode édition de lot, on sort de l'édition
    if (state.uiDraft.editingBatchId) {
        state.uiDraft.editingBatchId = null;
        setConstraintButtonsEditing(false);
    }

    const typeSel = /** @type {HTMLSelectElement|null} */ (document.getElementById("constraintType"));
    if (typeSel) typeSel.selectedIndex = 0;

    const p = /** @type {HTMLInputElement|null} */ (document.getElementById("cstParam"));
    if (p) p.value = "";

    onConstraintTypeChange();
    (sel ?? typeSel)?.focus();
}

/* ==========================================================================
   Création de contraintes (lots)
   ========================================================================== */

/**
 * Ajoute des contraintes à partir d’un GROUPE d’élèves :
 *  - unaires  : 1 entrée par élève
 *  - binaires : 1 entrée par paire du groupe (C(n,2))
 * Les entrées générées reçoivent un batch_id commun + insertion d’un _batch_marker_.
 */
export function addConstraint() {
    const typeSel = /** @type {HTMLSelectElement} */ (document.getElementById("constraintType"));
    const t = typeSel.value;
    const selectedIds = getSelectedStudentIds();

    const isUnary = ["front_rows", "back_rows", "solo_table", "empty_neighbor", "no_adjacent"].includes(t);
    const isBinary = ["same_table", "far_apart"].includes(t);

    if (isUnary && selectedIds.length === 0) {
        alert("Sélectionnez au moins un élève pour cette contrainte.");
        return;
    }
    if (isBinary && selectedIds.length < 2) {
        alert("Sélectionnez au moins deux élèves pour cette contrainte.");
        return;
    }

    const pInput = /** @type {HTMLInputElement|null} */ (document.getElementById("cstParam"));
    const pValRaw = pInput?.value ? Number(pInput.value) : null;

    const maxD = computeMaxManhattan(state.schema);
    const d = t === "far_apart" ? Math.min(Math.max(2, pValRaw || 2), Math.max(2, maxD)) : null;
    const k = (t === "front_rows" || t === "back_rows") ? Math.max(1, pValRaw ?? 1) : null;

    const batch_id = newBatchId();
    const namesPlural = formatNamesList(selectedIds);

    let batch_human = "";
    switch (t) {
        case "front_rows":
            batch_human = `${namesPlural} doivent être dans les premières rangées (k=${k ?? "?"})`;
            break;
        case "back_rows":
            batch_human = `${namesPlural} doivent être dans les dernières rangées (k=${k ?? "?"})`;
            break;
        case "solo_table":
            batch_human = `${namesPlural} doivent être isolé·e·s sur une table`;
            break;
        case "empty_neighbor":
            batch_human = `${namesPlural} doivent avoir au moins un siège vide à côté`;
            break;
        case "no_adjacent":
            batch_human = `${namesPlural} ne doivent avoir aucun·e voisin·e adjacent·e`;
            break;
        case "same_table":
            batch_human = `${namesPlural} doivent être à la même table`;
            break;
        case "far_apart":
            batch_human = `${namesPlural} doivent être éloigné·e·s d’une distance d’au moins d=${d ?? "?"}`;
            break;
    }

    /** @type {any[]} */
    const payloads = [];

    if (isUnary) {
        for (const a of selectedIds) {
            const c = /** @type {any} */ ({type: t, a, batch_id, human: ""});
            if (k != null) c.k = k;
            payloads.push(c);
        }
    } else {
        for (const [a, b] of pairs(selectedIds)) {
            const c = /** @type {any} */ ({type: t, a, b, batch_id, human: ""});
            if (d != null) c.d = d;
            payloads.push(c);
        }
    }

    for (const p of payloads) state.constraints.push(p);
    state.constraints.push({type: "_batch_marker_", batch_id, human: batch_human, count: payloads.length});

    renderConstraints();
}

/* ==========================================================================
   Rendu + suppression
   ========================================================================== */

/**
 * Affiche les contraintes dans l’UI.
 *
 * Deux catégories sont rendues :
 *  1) Les « lots » (marqueurs `_batch_marker_`) :
 *     - Affichés comme des pills avec le texte humain (m.human).
 *     - Bouton ✎ pour éditer le lot (pré-remplit le formulaire).
 *     - Bouton ✕ pour supprimer TOUT le lot (les entrées + le marqueur).
 *       → Si on supprimait le lot actuellement édité, on sort proprement du mode édition
 *         (reset des boutons, du formulaire, et vidage de editingBatchId).
 *
 *  2) Les contraintes individuelles SANS batch_id (ex : `forbid_seat`, `exact_seat`, legacy) :
 *     - Affichées comme des pills individuelles.
 *     - Bouton ✕ qui retire la contrainte, avec effets de bord nécessaires :
 *          • `forbid_seat` : met à jour `state.forbidden`.
 *          • `exact_seat`  : désaffecte l’élève si besoin.
 *
 * Cette fonction se contente du rendu + wiring des boutons.
 * Elle délègue la logique d’édition à `startEditBatch()` et la logique de reset
 * du formulaire à `cancelConstraintForm()`. Après toute mutation, elle rafraîchit
 * les vues nécessaires (room, students, badges de boutons).
 */
export function renderConstraints() {
    const root = /** @type {HTMLElement|null} */ ($("#constraintsList"));
    if (!root) return;

    // Vide le conteneur avant de re-render.
    root.innerHTML = "";

    /* -----------------------------------------------------------------------
     * 1) Lots (marqueurs _batch_marker_)
     * --------------------------------------------------------------------- */
    const markers = state.constraints.filter((c) => c.type === "_batch_marker_");

    for (const m of markers) {
        // Conteneur visuel du lot
        const item = document.createElement("div");
        item.className = "constraint-pill me-2 mb-2 d-inline-flex align-items-center gap-2";
        item.setAttribute("role", "group");
        item.setAttribute("aria-label", "Lot de contraintes");
        item.dataset.batchId = m.batch_id;

        // Texte humain du lot (ex: "Alice et Bob doivent ...")
        const text = document.createElement("span");
        text.textContent = m.human || "(lot)";
        item.appendChild(text);

        // Bouton ÉDITER (✎) → ouvre le formulaire pré-rempli (type, param, élèves)
        const edit = document.createElement("button");
        edit.className = "btn btn-sm btn-outline-secondary";
        edit.type = "button";
        edit.setAttribute("aria-label", "Éditer ce lot de contraintes");
        edit.textContent = "✎";
        edit.addEventListener("click", () => {
            startEditBatch(m.batch_id);
        });
        item.appendChild(edit);

        // Bouton SUPPRIMER (✕) → retire toutes les contraintes du lot + le marqueur
        const del = document.createElement("button");
        del.className = "btn btn-sm btn-outline-danger";
        del.type = "button";
        del.setAttribute("aria-label", "Supprimer ce lot de contraintes");
        del.textContent = "✕";
        del.addEventListener("click", () => {
            const bid = m.batch_id;

            // Si on supprimait le lot en cours d’édition → on sort proprement du mode édition
            if (state.uiDraft.editingBatchId === bid) {
                state.uiDraft.editingBatchId = null;
                setConstraintButtonsEditing(false);
                cancelConstraintForm(); // remet à zéro type/param/sel. d’élèves + focus
            }

            // Supprime ce lot : toutes les entrées avec ce batch_id + le marqueur m
            state.constraints = state.constraints.filter((c) => c.batch_id !== bid && c !== m);

            // Rafraîchis l’UI (liste contraintes, étiquettes/boutons, SVG)
            renderConstraints();
            updateBanButtonLabel();
            renderRoom();
        });

        item.appendChild(del);
        root.appendChild(item);
    }

    /* -----------------------------------------------------------------------
     * 2) Contraintes individuelles SANS batch_id
     *    (legacy, forbid_seat, exact_seat, etc.) — on ignore les _objective_
     * --------------------------------------------------------------------- */
    const singles = state.constraints.filter(
        (c) => c.type !== "_batch_marker_" && c.type !== "_objective_" && !c.batch_id
    );

    for (const c of singles) {
        const item = document.createElement("div");
        item.className = "constraint-pill me-2 mb-2 d-inline-flex align-items-center gap-2";
        item.setAttribute("role", "group");
        item.setAttribute("aria-label", "Contrainte");

        // Texte lisible (« élève X doit … », etc.)
        const text = document.createElement("span");
        text.textContent = humanizeConstraint(c);
        item.appendChild(text);

        // Bouton SUPPRIMER (✕) pour la contrainte individuelle
        const del = document.createElement("button");
        del.className = "btn btn-sm btn-outline-danger";
        del.type = "button";
        del.setAttribute("aria-label", "Supprimer cette contrainte");
        del.textContent = "✕";
        del.addEventListener("click", () => {
            // 2.1) Effets de bord propres
            if (c.type === "forbid_seat") {
                // On retire aussi la clé de `state.forbidden`
                const k =
                    c.key ||
                    (Number.isFinite(c.x) && Number.isFinite(c.y) && Number.isFinite(c.s) ? `${c.x},${c.y},${c.s}` : null);
                if (k) state.forbidden.delete(k);
            }

            if (c.type === "exact_seat") {
                // Éjecte l’élève si la contrainte le "pinnait" à un siège
                const sid = Number(c.a);
                const prev = state.placedByStudent.get(sid);
                if (prev) {
                    state.placedByStudent.delete(sid);
                    state.placements.delete(prev);
                }
            }

            // 2.2) Supprime la contrainte de l’array
            const idx = state.constraints.indexOf(c);
            if (idx >= 0) state.constraints.splice(idx, 1);

            // 2.3) Rafraîchis l’UI
            renderConstraints();
            renderRoom();
            renderStudents();
            updateBanButtonLabel();
        });

        item.appendChild(del);
        root.appendChild(item);
    }
}


/**
 * Lance l'édition d'un lot identifié par batch_id :
 * - pré-remplit le formulaire (type, param, élèves),
 * - bascule les boutons en mode "édition".
 */
export function startEditBatch(batch_id /**: string */) {
    // Récupère toutes les entrées du lot (hors marqueur)
    const items = state.constraints.filter(c => c.batch_id === batch_id && c.type !== "_batch_marker_");
    if (!items.length) return;

    // Type du lot = type de la première entrée
    const t = items[0].type;
    const typeSel = /** @type {HTMLSelectElement|null} */ (document.getElementById("constraintType"));
    const pInput = /** @type {HTMLInputElement|null} */ (document.getElementById("cstParam"));
    if (!typeSel || !pInput) return;

    // Préselectionne le type et affiche le bon champ param.
    typeSel.value = t;
    onConstraintTypeChange();

    // Paramètre (si applicable) : on prend la 1ère valeur rencontrée
    if (t === "far_apart") {
        const d = Number(items.find(c => "d" in c)?.d ?? 2) || 2;
        const maxD = computeMaxManhattan(state.schema);
        pInput.value = String(Math.min(Math.max(2, d), Math.max(2, maxD)));
    } else if (t === "front_rows" || t === "back_rows") {
        const k = Number(items.find(c => "k" in c)?.k ?? 1) || 1;
        pInput.value = String(Math.max(1, k));
    } else {
        pInput.value = "";
    }

    // Élèves concernés
    let ids = [];
    if (isUnaryType(t)) {
        ids = items.map(c => Number(c.a)).filter(Number.isFinite);
    } else {
        const set = new Set();
        for (const c of items) {
            if (Number.isFinite(c.a)) set.add(Number(c.a));
            if (Number.isFinite(c.b)) set.add(Number(c.b));
        }
        ids = Array.from(set);
    }

    // Rafraîchit les sélecteurs puis applique la sélection
    refreshConstraintSelectors();
    applyIdsToSelectors(ids);

    // Passe en mode édition
    state.uiDraft.editingBatchId = batch_id;
    setConstraintButtonsEditing(true);

    // Focus UX
    (document.getElementById("cstParam") || document.getElementById("cstStudents") || typeSel)?.focus();
}

/**
 * Bouton principal du formulaire :
 * - si on n'édite pas de lot → ajoute (comportement existant),
 * - si un lot est en cours d'édition → met à jour ce lot.
 */
export function commitConstraintForm() {
    const editing = state.uiDraft.editingBatchId;
    if (!editing) {
        addConstraint(); // comportement existant inchangé
        return;
    }

    // ===== Mise à jour du lot existant =====
    const typeSel = /** @type {HTMLSelectElement} */ (document.getElementById("constraintType"));
    const t = typeSel.value;
    const selectedIds = getSelectedStudentIds();

    const isUnary = isUnaryType(t);
    const isBinary = ["same_table", "far_apart"].includes(t);

    if (isUnary && selectedIds.length === 0) {
        alert("Sélectionnez au moins un élève pour cette contrainte.");
        return;
    }
    if (isBinary && selectedIds.length < 2) {
        alert("Sélectionnez au moins deux élèves pour cette contrainte.");
        return;
    }

    const pInput = /** @type {HTMLInputElement|null} */ (document.getElementById("cstParam"));
    const pValRaw = pInput?.value ? Number(pInput.value) : null;

    const maxD = computeMaxManhattan(state.schema);
    const d = t === "far_apart" ? Math.min(Math.max(2, pValRaw || 2), Math.max(2, maxD)) : null;
    const k = (t === "front_rows" || t === "back_rows") ? Math.max(1, pValRaw ?? 1) : null;

    // Texte humain du lot
    const namesPlural = formatNamesList(selectedIds);
    let batch_human = "";
    switch (t) {
        case "front_rows":
            batch_human = `${namesPlural} doivent être dans les premières rangées (k=${k ?? "?"})`;
            break;
        case "back_rows":
            batch_human = `${namesPlural} doivent être dans les dernières rangées (k=${k ?? "?"})`;
            break;
        case "solo_table":
            batch_human = `${namesPlural} doivent être isolé·e·s sur une table`;
            break;
        case "empty_neighbor":
            batch_human = `${namesPlural} doivent avoir au moins un siège vide à côté`;
            break;
        case "no_adjacent":
            batch_human = `${namesPlural} ne doivent avoir aucun·e voisin·e adjacent·e`;
            break;
        case "same_table":
            batch_human = `${namesPlural} doivent être à la même table`;
            break;
        case "far_apart":
            batch_human = `${namesPlural} doivent être éloigné·e·s d’une distance d’au moins d=${d ?? "?"}`;
            break;
    }

    /** @type {any[]} */
    const payloads = [];
    if (isUnary) {
        for (const a of selectedIds) {
            const c = /** @type {any} */ ({type: t, a, batch_id: editing, human: ""});
            if (k != null) c.k = k;
            payloads.push(c);
        }
    } else {
        for (const [a, b] of pairs(selectedIds)) {
            const c = /** @type {any} */ ({type: t, a, b, batch_id: editing, human: ""});
            if (d != null) c.d = d;
            payloads.push(c);
        }
    }

    // 1) Purge l'ancien lot (contraintes + marqueur)
    state.constraints = state.constraints.filter(c => c.batch_id !== editing);

    // 2) Réinsère les contraintes + nouveau marqueur (même batch_id conservé)
    for (const p of payloads) state.constraints.push(p);
    state.constraints.push({type: "_batch_marker_", batch_id: editing, human: batch_human, count: payloads.length});

    // 3) UI : reset mode édition + rerender
    state.uiDraft.editingBatchId = null;
    setConstraintButtonsEditing(false);
    cancelConstraintForm(); // remet à zéro la sélection/param/UI
    renderConstraints();
}

