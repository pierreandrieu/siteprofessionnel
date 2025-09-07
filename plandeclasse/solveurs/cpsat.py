from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import DefaultDict, Dict, Iterable, List, Optional, Sequence, Set, Tuple

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
    """Siège indexé de manière compacte pour le solveur CP-SAT."""
    idx: int  # index global 0..S-1
    x: int  # colonne (table)
    y: int  # rang (distance au tableau)
    s: int  # index du siège *sur la table* (pour l’adjacence)
    table_key: Tuple[int, int]  # (x, y)


# ======================================================================
# Solveur CP-SAT
# ======================================================================

class SolveurCPSAT(Solveur):
    """
    Solveur de plan de classe basé sur OR-Tools CP-SAT.

    Objectifs *lexicographiques* (ordre strict) :
      (1) **Maximiser** le nombre d’élèves *sans voisin adjacent* (iso)
      (2) **Minimiser** les paires adjacentes de *même genre* (mixage)
      (3) **Minimiser** la somme des rangs Y (distance au tableau)

    Contraintes unaires « dures » encodées :
      • SEUL_A_TABLE (solo_table)
      • NO_ADJACENT (no_adjacent)
      • EMPTY_NEIGHBOR (empty_neighbor)

    Variabilité :
      • `seed` : graine aléatoire (reproductible)
      • `randomize_order` : mélange l’ordre des élèves avant modélisation
      • `tiebreak_random` : 4ᵉ passe aléatoire qui départage les co-optimums
    """

    def __init__(
            self,
            *,
            prefer_alone: bool = True,
            prefer_mixage: bool = True,
            seed: Optional[int] = None,
            randomize_order: bool = False,
            tiebreak_random: bool = True,
    ) -> None:
        super().__init__()
        self.prefer_alone: bool = prefer_alone
        self.prefer_mixage: bool = prefer_mixage
        self.seed: Optional[int] = seed
        self.randomize_order: bool = randomize_order
        self.tiebreak_random: bool = tiebreak_random
        logger.info(
            "SolveurCPSAT initialisé (prefer_alone=%s, prefer_mixage=%s, seed=%s, randomize_order=%s, tiebreak_random=%s)",
            prefer_alone, prefer_mixage, seed, randomize_order, tiebreak_random
        )

    # ------------------------------------------------------------------ API Solveur

    def resoudre(
            self,
            salle: Salle,
            eleves: Sequence[Eleve],
            contraintes: Sequence[Contrainte],
            *,
            essais_max: int = 10_000,  # compat. API, non utilisé ici
            budget_temps_ms: Optional[int] = None,
    ) -> ResultatResolution:
        """
        Résolution avec **optimisation lexicographique** :
        iso → mixage → distance, en figeant l’optimum de chaque passe pour la suivante.
        Une 4ᵉ passe optionnelle et aléatoire départage les co-optimums.
        """
        # RNG (reproductible si seed non-nulle)
        rng = random.Random(self.seed)

        # 0) Vérifications rapides
        self._sanity_check(salle, eleves, contraintes)

        # 0bis) Ordre des élèves (variabilité contrôlée)
        eleves_work: List[Eleve] = list(eleves)
        if self.randomize_order:
            rng.shuffle(eleves_work)

        # 1) Sièges + domaines autorisés
        seats: List[_Seat] = self._enumerate_seats(salle)
        allowed_by_e: Dict[int, Set[int]] = self._compute_allowed_domains(salle, eleves_work, contraintes, seats)
        self._apply_exact_seats(contraintes, eleves_work, seats, allowed_by_e)

        # 2) Arêtes d’adjacence intra-table (|Δs| = 1)
        edges_adj: List[Tuple[int, int]] = self._adjacent_edges_same_table(seats)

        # 3) Budget temps par passe
        time_total_s: Optional[float] = (budget_temps_ms / 1000.0) if budget_temps_ms and budget_temps_ms > 0 else None
        n_passes = 3 + (1 if self.tiebreak_random else 0)
        per_pass_s: Optional[float] = (time_total_s / n_passes) if time_total_s else None

        # ==================== PASS 1 — objectif principal ====================
        model1, x1, sumY1, nb_iso1, nb_same1 = self._build_model(
            eleves_work, seats, allowed_by_e, contraintes, edges_adj,
            include_isolates=True, include_mixage=True
        )

        # Choix de l’objectif #1 : iso prioritaire, sinon mixage, sinon distance
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

        best_iso: int = int(solver1.Value(nb_iso1))
        best_same: Optional[int] = int(solver1.Value(nb_same1)) if nb_same1 is not None else None
        _best_sumY_1: int = int(solver1.Value(sumY1))

        # ==================== PASS 2 — deuxième objectif ====================
        do_pass2: bool = self.prefer_alone and self.prefer_mixage and (nb_same1 is not None)
        if do_pass2:
            model2, x2, sumY2, nb_iso2, nb_same2 = self._build_model(
                eleves_work, seats, allowed_by_e, contraintes, edges_adj,
                include_isolates=True, include_mixage=True
            )

            if primary_key == "iso":
                model2.Add(nb_iso2 == best_iso)
                model2.Minimize(nb_same2)
            else:
                assert primary_key == "same" and best_same is not None
                model2.Add(nb_same2 == best_same)
                model2.Maximize(nb_iso2)

            solver2 = self._make_solver(per_pass_s)
            status2 = solver2.Solve(model2)
            if status2 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                return ResultatResolution(affectation=None, essais=0, verifications=0)

            best_iso = int(solver2.Value(nb_iso2))
            best_same = int(solver2.Value(nb_same2)) if nb_same2 is not None else best_same

        # ==================== PASS 3 — distance au tableau ====================
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

        best_sumY: int = int(solver3.Value(sumY3))

        # ==================== PASS 4 — départage aléatoire (optionnel) ====================
        if self.tiebreak_random:
            model4, x4, sumY4, nb_iso4, nb_same4 = self._build_model(
                eleves_work, seats, allowed_by_e, contraintes, edges_adj,
                include_isolates=True, include_mixage=True
            )
            # figer l’optimum des passes précédentes
            if self.prefer_alone:
                model4.Add(nb_iso4 == best_iso)
            if self.prefer_mixage and (nb_same4 is not None) and (best_same is not None):
                model4.Add(nb_same4 == best_same)
            model4.Add(sumY4 == best_sumY)

            # Objectif aléatoire reproductible (en fonction de 'seed')
            # Maximize(Σ w[e,i] * x[e,i]) pour choisir un optimum différent.
            weights: Dict[Tuple[int, int], int] = {}
            E = len(eleves_work)
            S = len(seats)
            for e in range(E):
                for i in range(S):
                    # Poids strictement positifs pour éviter les égalités triviales
                    weights[(e, i)] = rng.randrange(1, 1_000_000)
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
                # sinon on retombe sur la passe 3 (sécurité)

        # 4) Reconstruction de l’affectation (passe 3)
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

        # 5) Validation finale locale (cohérente avec le modèle)
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
        """
        Construit un modèle autonome (une passe) :
        - affectation 1 siège / élève, exclusivité des sièges,
        - contraintes dures (binaires + unaires SEUL_A_TABLE, NO_ADJACENT, EMPTY_NEIGHBOR),
        - variables d’objectifs (isolation, mixage, somme des Y).
        """
        E: int = len(eleves)
        S: int = len(seats)

        model: cp_model.CpModel = cp_model.CpModel()

        # ---------- Variables x[e][i] : 1 si l’élève e occupe le siège i ----------
        x: List[List[cp_model.IntVar]] = [
            [model.NewBoolVar(f"x_e{e}_s{i}") for i in range(S)]
            for e in range(E)
        ]

        # ---------- Domaines autorisés ----------
        for e in range(E):
            allowed: Set[int] = allowed_by_e.get(e, set())
            if not allowed:
                model.Add(sum(x[e][i] for i in range(S)) == -1)  # infaisable (aucun siège)
                continue
            for i in range(S):
                if i not in allowed:
                    model.Add(x[e][i] == 0)

        # ---------- Affectation : 1 siège par élève, exclusivité des sièges ----------
        for e in range(E):
            model.Add(sum(x[e][i] for i in range(S)) == 1)
        for i in range(S):
            model.Add(sum(x[e][i] for e in range(E)) <= 1)

        # ---------- Pré-calculs adjacency / tables ----------
        neighbors_of: DefaultDict[int, List[int]] = defaultdict(list)
        for (i, j) in edges_adj:
            neighbors_of[i].append(j)
            neighbors_of[j].append(i)

        seats_by_table: DefaultDict[Tuple[int, int], List[int]] = defaultdict(list)
        for i, st in enumerate(seats):
            seats_by_table[st.table_key].append(i)

        # ---------- Contraintes *binaires* dures ----------
        from ..contraintes.binaires import DoiventEtreSurMemeTable, DoiventEtreEloignes, DoiventEtreAdjacents

        # (a) Même table
        for c in contraintes:
            if isinstance(c, DoiventEtreSurMemeTable):
                a: int = eleves.index(c.a)
                b: int = eleves.index(c.b)
                for i in range(S):
                    for j in range(S):
                        if seats[i].table_key != seats[j].table_key:
                            model.Add(x[a][i] + x[b][j] <= 1)

        # (b) Éloignés d’au moins d (Manhattan sur (x,y))
        for c in contraintes:
            if isinstance(c, DoiventEtreEloignes):
                a = eleves.index(c.a)
                b = eleves.index(c.b)
                dmin: int = int(c.d)
                for i in range(S):
                    for j in range(S):
                        dij = abs(seats[i].x - seats[j].x) + abs(seats[i].y - seats[j].y)
                        if dij < dmin:
                            model.Add(x[a][i] + x[b][j] <= 1)

        # (c) Adjacent requis (seulement paires adjacentes permises)
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

        # ---------- Contraintes *unaires* dures ----------
        from ..contraintes.unaires import (
            DoitEtreSeulALaTable,
            DoitNePasAvoirVoisinAdjacent,
            DoitAvoirVoisinVide,
        )

        # Variables d’occupation par siège
        occ: List[cp_model.IntVar] = [model.NewBoolVar(f"occ_s{i}") for i in range(S)]
        for i in range(S):
            model.Add(occ[i] == sum(x[e][i] for e in range(E)))  # ∑∈{0,1}

        # (1) SEUL_A_TABLE
        solo_indices = [eleves.index(c.eleve) for c in contraintes if isinstance(c, DoitEtreSeulALaTable)]
        for a in solo_indices:
            for table_key, seat_ids in seats_by_table.items():
                # a_sur_T = OR_{i in seat_ids} x[a][i]
                a_sur_T = model.NewBoolVar(f"a{a}_on_{table_key[0]}_{table_key[1]}")
                model.AddMaxEquality(a_sur_T, [x[a][i] for i in seat_ids])

                # Somme des autres élèves sur T
                sum_others_T = model.NewIntVar(0, len(seat_ids), f"sum_others_T_{table_key[0]}_{table_key[1]}_a{a}")
                model.Add(sum_others_T == sum(x[e][i] for e in range(E) if e != a for i in seat_ids))

                # Implication : si a_sur_T alors aucun autre élève sur T
                model.Add(sum_others_T == 0).OnlyEnforceIf(a_sur_T)

        # (2) NO_ADJACENT
        no_adj_indices = [eleves.index(c.eleve) for c in contraintes if isinstance(c, DoitNePasAvoirVoisinAdjacent)]
        for a in no_adj_indices:
            for i, adj_i in neighbors_of.items():
                if not adj_i:
                    continue
                sum_others_adj_i = model.NewIntVar(0, len(adj_i), f"sum_others_adj_i_{i}_a{a}")
                model.Add(sum_others_adj_i == sum(x[e][j] for e in range(E) if e != a for j in adj_i))
                model.Add(sum_others_adj_i == 0).OnlyEnforceIf(x[a][i])

        # (3) EMPTY_NEIGHBOR — AU MOINS UN SIÈGE ADJACENT VIDE
        empty_neigh_indices = [eleves.index(c.eleve) for c in contraintes if isinstance(c, DoitAvoirVoisinVide)]
        for a in empty_neigh_indices:
            for i, adj_i in neighbors_of.items():
                if not adj_i:
                    continue
                # x[a,i] + Σ occ[j] ≤ |adj_i|
                model.Add(x[a][i] + sum(occ[j] for j in adj_i) <= len(adj_i))

        need_empty_indices = [eleves.index(c.eleve) for c in contraintes if isinstance(c, DoitAvoirVoisinVide)]
        for a in need_empty_indices:
            for table_key, seat_ids in seats_by_table.items():
                cap_T = len(seat_ids)
                a_on_T = model.NewBoolVar(f"a{a}_needs_empty_on_{table_key[0]}_{table_key[1]}")
                model.AddMaxEquality(a_on_T, [x[a][i] for i in seat_ids])
                sum_occ_T = sum(occ[i] for i in seat_ids)
                # sum_occ_T + a_on_T <= cap_T  ⇒ au moins un siège libre sur la table de a
                model.Add(sum_occ_T + a_on_T <= cap_T)

        # ---------- Objectif (3) : somme des rangs Y ----------
        max_y: int = max((st.y for st in seats), default=0)
        sumY: cp_model.IntVar = model.NewIntVar(0, max(0, E * max_y), "sumY")
        model.Add(sumY == sum(seats[i].y * x[e][i] for e in range(E) for i in range(S)))

        # ---------- Objectif (1) : “sans voisin” (iso) ----------
        pair_used: Dict[Tuple[int, int], cp_model.IntVar] = {}
        for (i, j) in edges_adj:
            ii, jj = (i, j) if i < j else (j, i)
            v = model.NewBoolVar(f"pair_used_{ii}_{jj}")
            model.Add(v <= occ[ii]);
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

        # ---------- Objectif (2) : mixage ----------
        nb_same: Optional[cp_model.IntVar] = None
        if include_mixage:
            occ_f: List[cp_model.IntVar] = [model.NewBoolVar(f"occF_s{i}") for i in range(S)]
            occ_m: List[cp_model.IntVar] = [model.NewBoolVar(f"occM_s{i}") for i in range(S)]

            idx_f: List[int] = [e for e, el in enumerate(eleves) if self._genre_code(getattr(el, "genre", None)) == "f"]
            idx_m: List[int] = [e for e, el in enumerate(eleves) if self._genre_code(getattr(el, "genre", None)) == "m"]

            for i in range(S):
                model.Add(occ_f[i] == (sum(x[e][i] for e in idx_f) if idx_f else 0))
                model.Add(occ_m[i] == (sum(x[e][i] for e in idx_m) if idx_m else 0))

            same_terms: List[cp_model.IntVar] = []
            for (i, j) in edges_adj:
                ii, jj = (i, j) if i < j else (j, i)
                vf = model.NewBoolVar(f"pairF_{ii}_{jj}")
                vm = model.NewBoolVar(f"pairM_{ii}_{jj}")
                model.Add(vf <= occ_f[ii]);
                model.Add(vf <= occ_f[jj])
                model.Add(vf >= occ_f[ii] + occ_f[jj] - 1)
                model.Add(vm <= occ_m[ii]);
                model.Add(vm <= occ_m[jj])
                model.Add(vm >= occ_m[ii] + occ_m[jj] - 1)
                same_terms.extend([vf, vm])

            nb_same = model.NewIntVar(0, 2 * len(edges_adj), "nb_same_gender_pairs")
            model.Add(nb_same == sum(same_terms))

        return model, x, sumY, nb_isoles, nb_same

    # ------------------------------------------------------------------ Aides de modélisation

    @staticmethod
    def _enumerate_seats(salle: Salle) -> List[_Seat]:
        out: List[_Seat] = []
        for idx, p in enumerate(salle.toutes_les_places()):
            out.append(_Seat(idx=idx, x=p.x, y=p.y, s=p.siege, table_key=(p.x, p.y)))
        return out

    def _compute_allowed_domains(
            self,
            salle: Salle,
            eleves: Sequence[Eleve],
            contraintes: Sequence[Contrainte],
            seats: Sequence[_Seat],
    ) -> Dict[int, Set[int]]:
        all_ids: Set[int] = {st.idx for st in seats}
        allowed_by_e: Dict[int, Set[int]] = {e_idx: set(all_ids) for e_idx in range(len(eleves))}

        for c in contraintes:
            impliques: Sequence[Eleve] = c.implique() or []
            if impliques:
                for e in impliques:
                    e_idx: int = eleves.index(e)
                    allowed = c.places_autorisees(e, salle)
                    if allowed is not None:
                        ids = {self._seat_index_of(p, seats) for p in allowed}
                        allowed_by_e[e_idx] &= ids
            else:
                for e_idx, e in enumerate(eleves):
                    allowed = c.places_autorisees(e, salle)
                    if allowed is not None:
                        ids = {self._seat_index_of(p, seats) for p in allowed}
                        allowed_by_e[e_idx] &= ids
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
        # pour la variabilité reproductible
        if self.seed is not None:
            try:
                solver.parameters.random_seed = int(self.seed)
            except Exception:
                pass
        return solver

    # ------------------------------------------------------------------ Vérifs préalables

    @staticmethod
    def _sanity_check(salle: Salle, eleves: Sequence[Eleve], contraintes: Sequence[Contrainte]) -> None:
        total_seats: int = sum(len(ps) for ps in salle.positions_par_table().values())
        nb_eleves: int = len(eleves)
        if nb_eleves > total_seats:
            raise ValueError(f"{nb_eleves} élèves pour {total_seats} sièges disponibles.")

        exact_positions: Set[Tuple[int, int, int]] = set()
        nom_exact: str = "DoitEtreExactementIci"
        for c in contraintes:
            if c.__class__.__name__ == nom_exact:
                p: Position = getattr(c, "ou")
                key: Tuple[int, int, int] = (p.x, p.y, p.siege)
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

    # ------------------------------------------------------------------ Validation finale cohérente

    def valider_final(self, salle: Salle, affectation: Dict[Eleve, Position],
                      contraintes: Sequence[Contrainte]) -> bool:
        """
        Validation locale **alignée** avec le modèle :
         - DoitAvoirVoisinVide : au moins un siège adjacent *libre* (si au moins un voisin existe).
         - DoitEtreSeulALaTable / DoitNePasAvoirVoisinAdjacent : déjà respectées par le modèle,
           on revérifie pour robustesse.
         - Binaires : revalidation directe.
        """
        by_xy: Dict[Tuple[int, int], Dict[int, Eleve]] = defaultdict(dict)  # (x,y) -> {seat_index: eleve}
        pos_by_e: Dict[Eleve, Position] = {}
        for e, p in affectation.items():
            pos_by_e[e] = p
            by_xy[(p.x, p.y)][p.siege] = e

        def same_table(e1: Eleve, e2: Eleve) -> bool:
            p1 = pos_by_e.get(e1);
            p2 = pos_by_e.get(e2)
            return (p1 is not None and p2 is not None) and (p1.x == p2.x and p1.y == p2.y)

        from ..contraintes.unaires import (
            DoitEtreSeulALaTable,
            DoitNePasAvoirVoisinAdjacent,
            DoitAvoirVoisinVide,
        )
        from ..contraintes.binaires import (
            DoiventEtreSurMemeTable,
            DoiventEtreEloignes,
            DoiventEtreAdjacents,
        )

        # Unaires
        for c in contraintes:
            if isinstance(c, DoitEtreSeulALaTable):
                p = pos_by_e.get(c.eleve)
                if p is None:
                    continue
                occ_xy = by_xy.get((p.x, p.y), {})
                if any(e is not c.eleve for s, e in occ_xy.items()):
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

        # Binaires
        for c in contraintes:
            if isinstance(c, DoiventEtreSurMemeTable):
                if not same_table(c.a, c.b):
                    return False
            elif isinstance(c, DoiventEtreAdjacents):
                pa = pos_by_e.get(c.a);
                pb = pos_by_e.get(c.b)
                if not (pa and pb and pa.x == pb.x and pa.y == pb.y and abs(pa.siege - pb.siege) == 1):
                    return False
            elif isinstance(c, DoiventEtreEloignes):
                pa = pos_by_e.get(c.a);
                pb = pos_by_e.get(c.b)
                if not (pa and pb and (abs(pa.x - pb.x) + abs(pa.y - pb.y) >= int(c.d))):
                    return False

        return True
