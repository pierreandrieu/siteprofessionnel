from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import DefaultDict, Dict, List, Optional, Sequence, Set, Tuple, Iterable

from collections import defaultdict
from ortools.sat.python import cp_model

from ..modele.eleve import Eleve
from ..modele.position import Position
from ..modele.salle import Salle
from ..contraintes.base import Contrainte
from ..solveurs.base import ResultatResolution, Solveur

logger = logging.getLogger(__name__)


# ======================================================================
# Représentation interne d’un siège (x, y, s) + clé de table
# ======================================================================

@dataclass(frozen=True)
class _Seat:
    idx: int
    x: int
    y: int
    s: int
    table_key: Tuple[int, int]
    px: int
    py: int


@dataclass(frozen=True)
class GeomPixels:
    table_pitch_x: int
    table_pitch_y: int
    seat_pitch_x: int
    seat_offset_x: int = 0
    seat_offset_y: int = 0


TableOffsets = Dict[Tuple[int, int], Tuple[int, int]]


# ======================================================================
# Solveur CP-SAT
# ======================================================================

class SolveurCPSAT(Solveur):
    """
    Solveur de plan de classe basé sur OR-Tools CP-SAT.

    Ajouts notables :
      • Prise en charge d’un **ordre visuel par table** via `row_map_ui`
        (ex: une table décalée “passe” des premières aux dernières rangées).
      • `visual_row_order` (par rang) et/ou géométrie pixels restent supportés.

    Objectifs lexicographiques :
      (1) Max #élèves isolés
      (2) Min #paires adjacentes même genre
      (3) Min somme des Y (ou py si géométrie)
    """

    def __init__(
            self,
            *,
            prefer_alone: bool = True,
            prefer_mixage: bool = True,
            seed: Optional[int] = None,
            randomize_order: bool = False,
            tiebreak_random: bool = True,
            geom: Optional[GeomPixels] = None,
            table_offsets: Optional[TableOffsets] = None,
            row_order_ui: Optional[List[int]] = None,
            row_map_ui: Optional[Dict[Tuple[int, int], int]] = None,  # ← NEW
    ) -> None:
        super().__init__()
        self.prefer_alone = prefer_alone
        self.prefer_mixage = prefer_mixage
        self.seed = seed
        self.randomize_order = randomize_order
        self.tiebreak_random = tiebreak_random
        self.geom = geom
        self.table_offsets: TableOffsets = table_offsets or {}
        self.row_order_ui: Optional[List[int]] = list(row_order_ui) if row_order_ui else None
        self.row_map_ui: Optional[Dict[Tuple[int, int], int]] = dict(row_map_ui) if row_map_ui else None

    # ------------------------------------------------------------------ API Solveur

    def resoudre(
            self,
            salle: Salle,
            eleves: Sequence[Eleve],
            contraintes: Sequence[Contrainte],
            *,
            essais_max: int = 10_000,
            budget_temps_ms: Optional[int] = None,
    ) -> ResultatResolution:
        rng = random.Random(self.seed)

        self._sanity_check(salle, eleves, contraintes)

        eleves_work: List[Eleve] = list(eleves)
        if self.randomize_order:
            rng.shuffle(eleves_work)

        seats: List[_Seat] = self._enumerate_seats(salle, self.geom, self.table_offsets)
        allowed_by_e: Dict[int, Set[int]] = self._compute_allowed_domains(salle, eleves_work, contraintes, seats)
        self._apply_exact_seats(contraintes, eleves_work, seats, allowed_by_e)

        edges_adj: List[Tuple[int, int]] = self._adjacent_edges_same_table(seats)

        time_total_s: Optional[float] = (budget_temps_ms / 1000.0) if budget_temps_ms and budget_temps_ms > 0 else None
        n_passes = 3 + (1 if self.tiebreak_random else 0)
        per_pass_s: Optional[float] = (time_total_s / n_passes) if time_total_s else None

        # ----- PASS 1
        model1, x1, sumY1, nb_iso1, nb_same1 = self._build_model(
            eleves_work, seats, allowed_by_e, contraintes, edges_adj,
            include_isolates=True, include_mixage=True
        )
        if self.prefer_alone:
            model1.Maximize(nb_iso1)
            primary_key = "iso"
        elif self.prefer_mixage and nb_same1 is not None:
            model1.Minimize(nb_same1)
            primary_key = "same"
        else:
            model1.Minimize(sumY1)
            primary_key = "sumY"

        solver1 = self._make_solver(per_pass_s)
        status1 = solver1.Solve(model1)
        if status1 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return ResultatResolution(affectation=None, essais=0, verifications=0)

        best_iso = int(solver1.Value(nb_iso1))
        best_same = int(solver1.Value(nb_same1)) if nb_same1 is not None else None
        _best_sumY_1 = int(solver1.Value(sumY1))

        # ----- PASS 2
        do_pass2 = self.prefer_alone and self.prefer_mixage and (nb_same1 is not None)
        if do_pass2:
            model2, x2, sumY2, nb_iso2, nb_same2 = self._build_model(
                eleves_work, seats, allowed_by_e, contraintes, edges_adj,
                include_isolates=True, include_mixage=True
            )
            if primary_key == "iso":
                model2.Add(nb_iso2 == best_iso)
                model2.Minimize(nb_same2)
            else:
                model2.Add(nb_same2 == best_same)
                model2.Maximize(nb_iso2)

            solver2 = self._make_solver(per_pass_s)
            status2 = solver2.Solve(model2)
            if status2 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                return ResultatResolution(affectation=None, essais=0, verifications=0)
            best_iso = int(solver2.Value(nb_iso2))
            best_same = int(solver2.Value(nb_same2)) if nb_same2 is not None else best_same

        # ----- PASS 3
        model3, x3, sumY3, nb_iso3, nb_same3 = self._build_model(
            eleves_work, seats, allowed_by_e, contraintes, edges_adj,
            include_isolates=True, include_mixage=True
        )
        if self.prefer_alone:
            model3.Add(nb_iso3 == best_iso)
        if self.prefer_mixage and (nb_same3 is not None) and (best_same is not None):
            model3.Add(nb_same3 == best_same)

        model3.Minimize(sumY3)
        solver3 = self._make_solver(per_pass_s)
        status3 = solver3.Solve(model3)
        if status3 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return ResultatResolution(affectation=None, essais=0, verifications=0)

        best_sumY = int(solver3.Value(sumY3))

        # ----- PASS 4 (départage aléatoire)
        if self.tiebreak_random:
            model4, x4, sumY4, nb_iso4, nb_same4 = self._build_model(
                eleves_work, seats, allowed_by_e, contraintes, edges_adj,
                include_isolates=True, include_mixage=True
            )
            if self.prefer_alone:
                model4.Add(nb_iso4 == best_iso)
            if self.prefer_mixage and (nb_same4 is not None) and (best_same is not None):
                model4.Add(nb_same4 == best_same)
            model4.Add(sumY4 == best_sumY)

            weights: Dict[Tuple[int, int], int] = {}
            E, S = len(eleves_work), len(seats)
            for e in range(E):
                for i in range(S):
                    weights[(e, i)] = random.Random(self.seed).randrange(1, 1_000_000)
            rand_expr = sum(weights[(e, i)] * x4[e][i] for e in range(E) for i in range(S))
            model4.Maximize(rand_expr)

            solver4 = self._make_solver(per_pass_s)
            status4 = solver4.Solve(model4)
            if status4 in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                affectation4: Dict[Eleve, Position] = {}
                for e_idx, e in enumerate(eleves_work):
                    seat_taken: Optional[int] = None
                    for i in range(len(seats)):
                        if solver4.Value(x4[e_idx][i]) == 1:
                            seat_taken = i
                            break
                    if seat_taken is None:
                        return ResultatResolution(affectation=None, essais=0, verifications=0)
                    st = seats[seat_taken]
                    affectation4[e] = Position(x=st.x, y=st.y, siege=st.s)
                if self.valider_final(salle, affectation4, contraintes):
                    return ResultatResolution(affectation=affectation4, essais=0, verifications=0)

        # Reconstruction (passe 3)
        affectation: Dict[Eleve, Position] = {}
        for e_idx, e in enumerate(eleves_work):
            seat_taken: Optional[int] = None
            for i in range(len(seats)):
                if solver3.Value(x3[e_idx][i]) == 1:
                    seat_taken = i
                    break
            if seat_taken is None:
                return ResultatResolution(affectation=None, essais=0, verifications=0)
            st = seats[seat_taken]
            affectation[e] = Position(x=st.x, y=st.y, siege=st.s)

        if not self.valider_final(salle, affectation, contraintes):
            return ResultatResolution(affectation=None, essais=0, verifications=0)

        return ResultatResolution(affectation=affectation, essais=0, verifications=0)

    # ------------------------------------------------------------------ Construction du modèle

    def _build_model(
            self,
            eleves: Sequence[Eleve],
            seats: Sequence[_Seat],
            allowed_by_e: Dict[int, Set[int]],
            contraintes: Sequence[Contrainte],
            edges_adj: Sequence[Tuple[int, int]],
            *,
            include_isolates: bool,
            include_mixage: bool,
    ) -> Tuple[
        cp_model.CpModel,
        List[List[cp_model.IntVar]],
        cp_model.IntVar,
        cp_model.IntVar,
        Optional[cp_model.IntVar],
    ]:
        E = len(eleves)
        S = len(seats)

        model = cp_model.CpModel()

        # x[e][i]
        x: List[List[cp_model.IntVar]] = [[model.NewBoolVar(f"x_e{e}_s{i}") for i in range(S)] for e in range(E)]

        # Domaines
        for e in range(E):
            allowed = allowed_by_e.get(e, set())
            if not allowed:
                model.Add(sum(x[e][i] for i in range(S)) == -1)
                continue
            for i in range(S):
                if i not in allowed:
                    model.Add(x[e][i] == 0)

        # Affectations
        for e in range(E):
            model.Add(sum(x[e][i] for i in range(S)) == 1)
        for i in range(S):
            model.Add(sum(x[e][i] for e in range(E)) <= 1)

        # Pré-calculs
        neighbors_of: DefaultDict[int, List[int]] = defaultdict(list)
        for (i, j) in edges_adj:
            neighbors_of[i].append(j)
            neighbors_of[j].append(i)

        seats_by_table: DefaultDict[Tuple[int, int], List[int]] = defaultdict(list)
        for i, st in enumerate(seats):
            seats_by_table[st.table_key].append(i)

        # ---------- Contraintes binaires ----------
        from ..contraintes.binaires import DoiventEtreSurMemeTable, DoiventEtreEloignes, DoiventEtreAdjacents

        # (a) Même table
        for c in contraintes:
            if isinstance(c, DoiventEtreSurMemeTable):
                a = eleves.index(c.a)
                b = eleves.index(c.b)
                for i in range(S):
                    for j in range(S):
                        if seats[i].table_key != seats[j].table_key:
                            model.Add(x[a][i] + x[b][j] <= 1)

        # (b) Eloignés (grille ou px)
        for c in contraintes:
            if isinstance(c, DoiventEtreEloignes):
                a = eleves.index(c.a)
                b = eleves.index(c.b)
                dmin = int(c.d)
                for i in range(S):
                    for j in range(S):
                        use_px = getattr(c, "en_pixels", False) or getattr(c, "metric", "") == "px"
                        if use_px:
                            dij = abs(seats[i].px - seats[j].px) + abs(seats[i].py - seats[j].py)
                        else:
                            dij = abs(seats[i].x - seats[j].x) + abs(seats[i].y - seats[j].y)
                        if dij < dmin:
                            model.Add(x[a][i] + x[b][j] <= 1)

        # (c) Adjacent requis
        allowed_pairs: Set[Tuple[int, int]] = set()
        for (i, j) in edges_adj:
            allowed_pairs.add((i, j))
            allowed_pairs.add((j, i))
        for c in contraintes:
            if isinstance(c, DoiventEtreAdjacents):
                a = eleves.index(c.a)
                b = eleves.index(c.b)
                for i in range(S):
                    for j in range(S):
                        if i == j or (i, j) not in allowed_pairs:
                            model.Add(x[a][i] + x[b][j] <= 1)

        # ---------- Contraintes unaires ----------
        from ..contraintes.unaires import (
            DoitEtreSeulALaTable,
            DoitNePasAvoirVoisinAdjacent,
            DoitAvoirVoisinVide,
        )

        occ: List[cp_model.IntVar] = [model.NewBoolVar(f"occ_s{i}") for i in range(S)]
        for i in range(S):
            model.Add(occ[i] == sum(x[e][i] for e in range(E)))

        # SEUL_A_TABLE
        solo_indices = [eleves.index(c.eleve) for c in contraintes if isinstance(c, DoitEtreSeulALaTable)]
        for a in solo_indices:
            for table_key, seat_ids in seats_by_table.items():
                a_sur_T = model.NewBoolVar(f"a{a}_on_{table_key[0]}_{table_key[1]}")
                model.AddMaxEquality(a_sur_T, [x[a][i] for i in seat_ids])
                sum_others_T = model.NewIntVar(0, len(seat_ids), f"sum_others_T_{table_key[0]}_{table_key[1]}_a{a}")
                model.Add(sum_others_T == sum(x[e][i] for e in range(E) if e != a for i in seat_ids))
                model.Add(sum_others_T == 0).OnlyEnforceIf(a_sur_T)

        # NO_ADJACENT
        no_adj_indices = [eleves.index(c.eleve) for c in contraintes if isinstance(c, DoitNePasAvoirVoisinAdjacent)]
        for a in no_adj_indices:
            for i, adj_i in neighbors_of.items():
                if not adj_i:
                    continue
                sum_others_adj_i = model.NewIntVar(0, len(adj_i), f"sum_others_adj_i_{i}_a{a}")
                model.Add(sum_others_adj_i == sum(x[e][j] for e in range(E) if e != a for j in adj_i))
                model.Add(sum_others_adj_i == 0).OnlyEnforceIf(x[a][i])

        # EMPTY_NEIGHBOR (au moins un siège adjacent libre)
        empty_neigh_indices = [eleves.index(c.eleve) for c in contraintes if isinstance(c, DoitAvoirVoisinVide)]
        for a in empty_neigh_indices:
            for i, adj_i in neighbors_of.items():
                if not adj_i:
                    continue
                model.Add(x[a][i] + sum(occ[j] for j in adj_i) <= len(adj_i))

        need_empty_indices = [eleves.index(c.eleve) for c in contraintes if isinstance(c, DoitAvoirVoisinVide)]
        for a in need_empty_indices:
            for table_key, seat_ids in seats_by_table.items():
                cap_T = len(seat_ids)
                a_on_T = model.NewBoolVar(f"a{a}_needs_empty_on_{table_key[0]}_{table_key[1]}")
                model.AddMaxEquality(a_on_T, [x[a][i] for i in seat_ids])
                sum_occ_T = sum(occ[i] for i in seat_ids)
                model.Add(sum_occ_T + a_on_T <= cap_T)

        # ---------- Objectifs ----------
        max_py = max((st.py for st in seats), default=0)
        sumY: cp_model.IntVar = model.NewIntVar(0, max(0, len(eleves) * max_py), "sumY")
        model.Add(sumY == sum(seats[i].py * x[e][i] for e in range(E) for i in range(S)))

        pair_used: Dict[Tuple[int, int], cp_model.IntVar] = {}
        for (i, j) in edges_adj:
            ii, jj = (i, j) if i < j else (j, i)
            v = model.NewBoolVar(f"pair_used_{ii}_{jj}")
            model.Add(v <= occ[ii])
            model.Add(v <= occ[jj])
            model.Add(v >= occ[ii] + occ[jj] - 1)
            pair_used[(ii, jj)] = v

        has_neighbor: List[cp_model.IntVar] = [model.NewBoolVar(f"hasN_s{i}") for i in range(S)]
        for i in range(S):
            if not neighbors_of[i]:
                model.Add(has_neighbor[i] == 0)
            else:
                incident = [pair_used[(min(i, j), max(i, j))] for j in neighbors_of[i]]
                model.Add(has_neighbor[i] <= sum(incident))
                for v in incident:
                    model.Add(has_neighbor[i] >= v)

        iso: List[cp_model.IntVar] = [model.NewBoolVar(f"iso_s{i}") for i in range(S)]
        for i in range(S):
            model.Add(iso[i] <= occ[i])
            model.Add(iso[i] + has_neighbor[i] <= 1)
            model.Add(iso[i] >= occ[i] - has_neighbor[i])

        nb_isoles: cp_model.IntVar = model.NewIntVar(0, len(eleves), "nb_isoles")
        model.Add(nb_isoles == sum(iso))

        nb_same: Optional[cp_model.IntVar] = None
        if include_mixage:
            occ_f: List[cp_model.IntVar] = [model.NewBoolVar(f"occF_s{i}") for i in range(S)]
            occ_m: List[cp_model.IntVar] = [model.NewBoolVar(f"occM_s{i}") for i in range(S)]
            idx_f = [e for e, el in enumerate(eleves) if self._genre_code(getattr(el, "genre", None)) == "f"]
            idx_m = [e for e, el in enumerate(eleves) if self._genre_code(getattr(el, "genre", None)) == "m"]
            for i in range(S):
                model.Add(occ_f[i] == (sum(x[e][i] for e in idx_f) if idx_f else 0))
                model.Add(occ_m[i] == (sum(x[e][i] for e in idx_m) if idx_m else 0))
            same_terms: List[cp_model.IntVar] = []
            for (i, j) in edges_adj:
                ii, jj = (i, j) if i < j else (j, i)
                vf = model.NewBoolVar(f"pairF_{ii}_{jj}")
                vm = model.NewBoolVar(f"pairM_{ii}_{jj}")
                model.Add(vf <= occ_f[ii])
                model.Add(vf <= occ_f[jj])
                model.Add(vf >= occ_f[ii] + occ_f[jj] - 1)
                model.Add(vm <= occ_m[ii])
                model.Add(vm <= occ_m[jj])
                model.Add(vm >= occ_m[ii] + occ_m[jj] - 1)
                same_terms.extend([vf, vm])
            nb_same = model.NewIntVar(0, 2 * len(edges_adj), "nb_same_gender_pairs")
            model.Add(nb_same == sum(same_terms))

        return model, x, sumY, nb_isoles, nb_same

    # ------------------------------------------------------------------ Aides de modélisation

    @staticmethod
    def _enumerate_seats(salle: Salle, geom: Optional[GeomPixels], offsets: TableOffsets) -> List[_Seat]:
        out: List[_Seat] = []
        idx = 0
        for p in salle.toutes_les_places():
            if not geom:
                px, py = p.x, p.y
            else:
                dx, dy = offsets.get((p.x, p.y), (0, 0))
                px = p.x * geom.table_pitch_x + dx + geom.seat_offset_x + p.siege * geom.seat_pitch_x
                py = p.y * geom.table_pitch_y + dy + geom.seat_offset_y
            out.append(_Seat(idx=idx, x=p.x, y=p.y, s=p.siege, table_key=(p.x, p.y), px=px, py=py))
            idx += 1
        return out

    def _compute_allowed_domains(
            self,
            salle: "Salle",
            eleves: Sequence["Eleve"],
            contraintes: Sequence["Contrainte"],
            seats: Sequence["_Seat"],
    ) -> Dict[int, Set[int]]:
        """
        Calcule, pour chaque élève, l'ensemble des sièges autorisés.

        Règles « premières/dernières rangées »
        --------------------------------------
        Priorité :
          1) **row_map_ui** (table → rangée visuelle)   ← NEW (par table)
          2) row_order_ui (liste des rangs du devant → fond)
          3) géométrie px (min/max(py) par rang y de grille)
          4) grille (y croissant)
        """
        all_ids: Set[int] = {st.idx for st in seats}
        allowed_by_e: Dict[int, Set[int]] = {e_idx: set(all_ids) for e_idx in range(len(eleves))}

        from ..contraintes.unaires import DoitEtreDansPremieresRangees, DoitEtreDansDernieresRangees

        use_ui_map: bool = bool(self.row_map_ui)
        use_ui_order: bool = bool(self.row_order_ui)
        use_px_geom: bool = bool(self.geom)

        # --- Pré-calculs pour les variantes visuelles ---
        # (A) row_map_ui : "x,y" -> rang_visuel (0..R-1, devant → fond)
        map_ui: Dict[Tuple[int, int], int] = self.row_map_ui or {}
        if use_ui_map:
            try:
                nb_vis_rows = 1 + max(map_ui.values())
            except ValueError:
                nb_vis_rows = 0

        # (B) row_order_ui : ordre de rang y (devant → fond)
        ord_front: List[int] = list(self.row_order_ui or [])
        ord_back: List[int] = ord_front  # même base

        # (C) px geom : min/max(py) par rang y (grille)
        rows_grid: List[int] = sorted({st.y for st in seats})
        if use_px_geom and not use_ui_map and not use_ui_order:
            row_py: DefaultDict[int, List[int]] = defaultdict(list)
            seen_tables: Set[Tuple[int, int]] = set()
            for st in seats:
                key = st.table_key
                if st.s == 0 and key not in seen_tables:
                    row_py[st.y].append(st.py)
                    seen_tables.add(key)
            if row_py:
                ord_front = sorted(row_py.keys(), key=lambda yy: min(row_py[yy]))
                ord_back = sorted(row_py.keys(), key=lambda yy: max(row_py[yy]))

        # ------------------------------------------------------------------
        # Application de toutes les contraintes
        # ------------------------------------------------------------------
        for c in contraintes:
            impliques: Sequence["Eleve"] = c.implique() or []

            is_front = isinstance(c, DoitEtreDansPremieresRangees)
            is_back = isinstance(c, DoitEtreDansDernieresRangees)

            if is_front or is_back:
                k: int = int(getattr(c, "k"))
                metric: str = str(getattr(c, "metric", "grid")).strip().lower()

                # --- Variante 1 : row_map_ui (par table) -------------------
                if use_ui_map and map_ui:
                    R = nb_vis_rows if 'nb_vis_rows' in locals() and nb_vis_rows else len(set(map_ui.values()))
                    if R <= 0:
                        ids_allowed = set(all_ids)
                    else:
                        if is_front:
                            allowed_vis = set(range(min(k, R)))
                        else:
                            start = max(0, R - k)
                            allowed_vis = set(range(start, R))
                        allowed_tables = {tk for tk, r in map_ui.items() if r in allowed_vis}
                        ids_allowed = {st.idx for st in seats if st.table_key in allowed_tables}

                # --- Variante 2 : row_order_ui (par rang) ------------------
                elif use_ui_order and ord_front and ord_back:
                    allowed_y: Set[int]
                    if is_front:
                        allowed_y = set(ord_front[:k])
                    else:
                        allowed_y = set(ord_back[-k:])
                    ids_allowed = {st.idx for st in seats if st.y in allowed_y}

                # --- Variante 3 : géométrie px explicite -------------------
                elif use_px_geom and metric == "px" and ord_front and ord_back:
                    allowed_y: Set[int]
                    if is_front:
                        allowed_y = set(ord_front[:k])
                    else:
                        allowed_y = set(ord_back[-k:])
                    ids_allowed = {st.idx for st in seats if st.y in allowed_y}

                # --- Variante 4 : grille (fallback) ------------------------
                else:
                    if is_front:
                        allowed_y = set(rows_grid[:k])
                    else:
                        allowed_y = set(rows_grid[-k:])
                    ids_allowed = {st.idx for st in seats if st.y in allowed_y}

                # Application aux élèves concernés (ou tous si contrainte globale)
                targets: Iterable[int] = (eleves.index(e) for e in impliques) if impliques else range(len(eleves))
                for e_idx in targets:
                    allowed_by_e[e_idx] &= ids_allowed

                continue  # contrainte traitée

            # ======= Chemin générique via places_autorisees(...) =======
            if impliques:
                for e in impliques:
                    e_idx = eleves.index(e)
                    autorisees = c.places_autorisees(e, salle)
                    if autorisees is not None:
                        ids = {self._seat_index_of(p, seats) for p in autorisees}
                        allowed_by_e[e_idx] &= ids
            else:
                for e_idx, e in enumerate(eleves):
                    autorisees = c.places_autorisees(e, salle)
                    if autorisees is not None:
                        ids2 = {self._seat_index_of(p, seats) for p in autorisees}
                        allowed_by_e[e_idx] &= ids2

        return allowed_by_e

    @staticmethod
    def _apply_exact_seats(
            contraintes: Sequence[Contrainte],
            eleves: Sequence[Eleve],
            seats: Sequence[_Seat],
            allowed_by_e: Dict[int, Set[int]],
    ) -> None:
        for c in contraintes:
            if c.__class__.__name__ == "DoitEtreExactementIci":
                e: Eleve = getattr(c, "eleve")
                p: Position = getattr(c, "ou")
                e_idx: int = eleves.index(e)
                seat_id: int = SolveurCPSAT._seat_index_of(p, seats)
                allowed_by_e[e_idx].intersection_update({seat_id})

    @staticmethod
    def _adjacent_edges_same_table(seats: Sequence[_Seat]) -> List[Tuple[int, int]]:
        by_table: DefaultDict[Tuple[int, int], List[_Seat]] = defaultdict(list)
        for st in seats:
            by_table[st.table_key].append(st)
        edges: List[Tuple[int, int]] = []
        for _, lst in by_table.items():
            lst_sorted = sorted(lst, key=lambda u: u.s)
            for a, b in zip(lst_sorted, lst_sorted[1:]):
                i, j = a.idx, b.idx
                if i > j:
                    i, j = j, i
                edges.append((i, j))
        return edges

    @staticmethod
    def _seat_index_of(p: Position, seats: Sequence[_Seat]) -> int:
        for st in seats:
            if st.x == p.x and st.y == p.y and st.s == p.siege:
                return st.idx
        raise KeyError("Position inconnue dans l’inventaire des sièges")

    @staticmethod
    def _genre_code(g: Optional[str]) -> Optional[str]:
        if not g:
            return None
        gg = g.strip().lower()
        if gg.startswith("f"):
            return "f"
        if gg.startswith("m") or gg.startswith("g"):
            return "m"
        return None

    def _make_solver(self, time_limit_s: Optional[float]) -> cp_model.CpSolver:
        solver = cp_model.CpSolver()
        if time_limit_s is not None:
            solver.parameters.max_time_in_seconds = max(0.1, time_limit_s)
        solver.parameters.num_search_workers = 8
        if self.seed is not None:
            try:
                solver.parameters.random_seed = int(self.seed)
            except Exception:
                pass
        return solver

    # ------------------------------------------------------------------ Vérifs préalables & validation finale

    @staticmethod
    def _sanity_check(salle: Salle, eleves: Sequence[Eleve], contraintes: Sequence[Contrainte]) -> None:
        total_seats = sum(len(ps) for ps in salle.positions_par_table().values())
        nb_eleves = len(eleves)
        if nb_eleves > total_seats:
            raise ValueError(f"{nb_eleves} élèves pour {total_seats} sièges disponibles.")

        exact_positions: Set[Tuple[int, int, int]] = set()
        nom_exact = "DoitEtreExactementIci"
        for c in contraintes:
            if c.__class__.__name__ == nom_exact:
                p: Position = getattr(c, "ou")
                key = (p.x, p.y, p.siege)
                if key in exact_positions:
                    raise ValueError("Deux élèves ne peuvent pas avoir le même siège imposé.")
                exact_positions.add(key)

        forb_tables: Set[Tuple[int, int]] = {
            (getattr(c, "x"), getattr(c, "y"))
            for c in contraintes
            if c.__class__.__name__ == "TableDoitEtreVide"
        }
        for c in contraintes:
            if c.__class__.__name__ == nom_exact:
                p2: Position = getattr(c, "ou")
                if (p2.x, p2.y) in forb_tables:
                    raise ValueError("Un siège exact est situé sur une table interdite.")

    def valider_final(self, salle: Salle, affectation: Dict[Eleve, Position],
                      contraintes: Sequence[Contrainte]) -> bool:
        from collections import defaultdict
        from ..contraintes.unaires import DoitEtreSeulALaTable, DoitNePasAvoirVoisinAdjacent, DoitAvoirVoisinVide
        from ..contraintes.binaires import DoiventEtreSurMemeTable, DoiventEtreEloignes, DoiventEtreAdjacents

        by_xy: Dict[Tuple[int, int], Dict[int, Eleve]] = defaultdict(dict)
        pos_by_e: Dict[Eleve, Position] = {}
        for e, p in affectation.items():
            pos_by_e[e] = p
            by_xy[(p.x, p.y)][p.siege] = e

        def same_table(e1: Eleve, e2: Eleve) -> bool:
            p1 = pos_by_e.get(e1)
            p2 = pos_by_e.get(e2)
            return (p1 is not None and p2 is not None) and (p1.x == p2.x and p1.y == p2.y)

        def _pxpy(p: Position) -> Tuple[int, int]:
            if not self.geom:
                return (p.x, p.y)
            dx, dy = self.table_offsets.get((p.x, p.y), (0, 0))
            px = p.x * self.geom.table_pitch_x + dx + self.geom.seat_offset_x + p.siege * self.geom.seat_pitch_x
            py = p.y * self.geom.table_pitch_y + dy + self.geom.seat_offset_y
            return (px, py)

        for c in contraintes:
            if isinstance(c, DoitEtreSeulALaTable):
                p = pos_by_e.get(c.eleve)
                if p is None:
                    continue
                occ_xy = by_xy.get((p.x, p.y), {})
                if any(e is not c.eleve for _s, e in occ_xy.items()):
                    return False
            elif isinstance(c, DoitNePasAvoirVoisinAdjacent):
                p = pos_by_e.get(c.eleve)
                if p is None:
                    continue
                occ_xy = by_xy.get((p.x, p.y), {})
                if (p.siege - 1 in occ_xy and occ_xy[p.siege - 1] is not c.eleve) or \
                        (p.siege + 1 in occ_xy and occ_xy[p.siege + 1] is not c.eleve):
                    return False
            elif isinstance(c, DoitAvoirVoisinVide):
                p = pos_by_e.get(c.eleve)
                if p is None:
                    continue
                occ_xy = by_xy.get((p.x, p.y), {})
                neighbors = [p.siege - 1, p.siege + 1]
                valid_neighbors = [s for s in neighbors if s in range(0, max(occ_xy.keys(), default=-1) + 2)]
                if not valid_neighbors:
                    continue
                if all(s in occ_xy for s in valid_neighbors):
                    return False

        for c in contraintes:
            if isinstance(c, DoiventEtreSurMemeTable):
                if not same_table(c.a, c.b):
                    return False
            elif isinstance(c, DoiventEtreAdjacents):
                pa = pos_by_e.get(c.a)
                pb = pos_by_e.get(c.b)
                if not (pa and pb and pa.x == pb.x and pa.y == pb.y and abs(pa.siege - pb.siege) == 1):
                    return False
            elif isinstance(c, DoiventEtreEloignes):
                pa = pos_by_e.get(c.a)
                pb = pos_by_e.get(c.b)
                if not (pa and pb):
                    continue
                use_px = bool(getattr(c, "en_pixels", False) or getattr(c, "metric", "") == "px")
                if use_px and self.geom is not None:
                    ax, ay = _pxpy(pa)
                    bx, by = _pxpy(pb)
                    dij = abs(ax - bx) + abs(ay - by)
                else:
                    dij = abs(pa.x - pb.x) + abs(pa.y - pb.y)
                if dij < int(c.d):
                    return False

        return True
