from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Dict, Sequence, Optional, Tuple, List, Set, Iterable, DefaultDict

from collections import defaultdict
from ortools.sat.python import cp_model

from ..modele.eleve import Eleve
from ..modele.position import Position
from ..modele.salle import Salle
from ..contraintes.base import Contrainte
from ..solveurs.base import ResultatResolution, Solveur

logger = logging.getLogger(__name__)


# ---------- Représentation interne d’un siège (pour éviter d’éparpiller x,y,s partout)

@dataclass(frozen=True)
class _Seat:
    idx: int  # index global 0..S-1
    x: int  # coordonnée table (colonne)
    y: int  # rang (distance au tableau)
    s: int  # index du siège sur la table (pour l’adjacence)
    table_key: Tuple[int, int]  # (x, y) de la table


class SolveurCPSAT(Solveur):
    """
    Solveur de plan de classe par CP-SAT (OR-Tools).

    Objectifs lexicographiques (dans l’ordre) :
      (1) Minimiser la somme des rangs Y (distance au tableau)
      (2) Maximiser le nombre d’élèves « isolés » à leur table (aucun voisin adjacent)
      (3) Minimiser les paires adjacentes de même genre (F-F ou M-M)

    Stratégie :
      - Variables binaires x[e][i] : « l’élève e occupe le siège i »
      - Domaines d’autorisation « allow » reconstruits par élève à partir de `places_autorisees`
      - Contraintes binaires « dures » (même table, éloignés, adjacents)
      - Trois passes de résolution ; chaque passe reconstruit le modèle et fige l’optimum précédent
    """

    def __init__(
            self,
            *,
            prefer_alone: bool = True,
            prefer_mixage: bool = True,
    ) -> None:
        super().__init__()
        self.prefer_alone = prefer_alone
        self.prefer_mixage = prefer_mixage

        logger.info("SolveurCPSAT initialisé (prefer_alone=%s, prefer_mixage=%s)", prefer_alone, prefer_mixage)

    # --------------------------------------------------------------------- API Solveur

    def resoudre(
            self,
            salle: Salle,
            eleves: Sequence[Eleve],
            contraintes: Sequence[Contrainte],
            *,
            essais_max: int = 10_000,  # non utilisé ici (compat API)
            budget_temps_ms: Optional[int] = None,  # temps total (réparti 1/3 par passe)
    ) -> ResultatResolution:
        # Vérifications élémentaires
        self._sanity_check(salle, eleves, contraintes)

        # Inventaire des sièges (positions) -> vecteur _Seat
        seats: List[_Seat] = self._enumerate_seats(salle)

        # Domaines autorisés par élève (intersections successives)
        allowed_by_e: Dict[int, Set[int]] = self._compute_allowed_domains(salle, eleves, contraintes, seats)

        # Sièges exacts (singleton de domaine)
        self._apply_exact_seats(contraintes, eleves, seats, allowed_by_e)

        # Adjacences (sur une même table) pour les objectifs + contraintes
        edges_adj: List[Tuple[int, int]] = self._adjacent_edges_same_table(seats)

        # Répartition du temps
        time_total_s: Optional[float] = (budget_temps_ms / 1000.0) if budget_temps_ms and budget_temps_ms > 0 else None
        per_pass_s: Optional[float] = (time_total_s / 3.0) if time_total_s else None

        # ----------------------------- PASSE 1 : Min sumY (distance au tableau)

        model1, x1, sumY1, nb_iso1, nb_same1 = self._build_model(
            eleves, seats, allowed_by_e, contraintes, edges_adj,
            include_isolates=True, include_mixage=True
        )
        model1.Minimize(sumY1)

        solver1 = self._make_solver(per_pass_s)
        status1 = solver1.Solve(model1)
        if status1 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return ResultatResolution(affectation=None, essais=0, verifications=0)
        best_sumY: int = int(solver1.Value(sumY1))

        # ----------------------------- PASSE 2 : Max nb_isoles (si activé), avec sumY fixé

        model2, x2, sumY2, nb_iso2, nb_same2 = self._build_model(
            eleves, seats, allowed_by_e, contraintes, edges_adj,
            include_isolates=True, include_mixage=True
        )
        model2.Add(sumY2 == best_sumY)
        if self.prefer_alone:
            model2.Maximize(nb_iso2)
        else:
            # objectif neutre
            model2.Minimize(0)

        solver2 = self._make_solver(per_pass_s)
        status2 = solver2.Solve(model2)
        if status2 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return ResultatResolution(affectation=None, essais=0, verifications=0)
        best_iso: int = int(solver2.Value(nb_iso2))

        # ----------------------------- PASSE 3 : Min nb_same_gender_pairs (si activé), sumY & iso figés

        model3, x3, sumY3, nb_iso3, nb_same3 = self._build_model(
            eleves, seats, allowed_by_e, contraintes, edges_adj,
            include_isolates=True, include_mixage=True
        )
        model3.Add(sumY3 == best_sumY)
        if self.prefer_alone:
            model3.Add(nb_iso3 == best_iso)

        if self.prefer_mixage and nb_same3 is not None:
            model3.Minimize(nb_same3)
        else:
            model3.Minimize(0)

        solver3 = self._make_solver(per_pass_s)
        status3 = solver3.Solve(model3)
        if status3 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return ResultatResolution(affectation=None, essais=0, verifications=0)

        # Reconstruction de l’affectation finale depuis la passe 3
        affectation: Dict[Eleve, Position] = {}
        for e_idx, e in enumerate(eleves):
            seat_taken: Optional[int] = None
            for i in range(len(seats)):
                if solver3.Value(x3[e_idx][i]) == 1:
                    seat_taken = i
                    break
            if seat_taken is None:
                return ResultatResolution(affectation=None, essais=0, verifications=0)
            st = seats[seat_taken]
            affectation[e] = Position(x=st.x, y=st.y, siege=st.s)

        # Validation finale locale (ex. voisin vide)
        if not self.valider_final(salle, affectation, contraintes):
            return ResultatResolution(affectation=None, essais=0, verifications=0)

        return ResultatResolution(affectation=affectation, essais=0, verifications=0)

    # --------------------------------------------------------------------- Construction du modèle

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
        Construit un modèle CP-SAT autonome (utilisé à chaque passe).

        Retourne :
          - model : le modèle CP-SAT
          - x[e][i] : variables d’occupation
          - sumY    : somme des rangs (distance au tableau)
          - nb_iso  : nombre d’élèves isolés (utile à la passe 2 / contrainte à la passe 3)
          - nb_same : nombre de paires adjacentes de même genre (objectif passe 3) ou None si absent
        """
        E: int = len(eleves)
        S: int = len(seats)

        model: cp_model.CpModel = cp_model.CpModel()

        # ---------------- Variables : x[e][i] = 1 si e occupe le siège i
        x: List[List[cp_model.IntVar]] = [
            [model.NewBoolVar(f"x_e{e}_s{i}") for i in range(S)] for e in range(E)
        ]

        # ---------------- Domaines autorisés (allow) : x[e][i] = 0 si i non autorisé pour e
        for e in range(E):
            allowed: Set[int] = allowed_by_e.get(e, set())
            if not allowed:
                # aucun siège autorisé pour e -> pas de solution faisable
                # on laisse le modèle incohérent ; la résolution renverra "infeasible"
                model.Add(sum(x[e][i] for i in range(S)) == -1)  # contrainte impossible
                continue
            for i in range(S):
                if i not in allowed:
                    model.Add(x[e][i] == 0)

        # ---------------- Affectation : 1 siège par élève, exclusivité des sièges
        for e in range(E):
            model.Add(sum(x[e][i] for i in range(S)) == 1)
        for i in range(S):
            model.Add(sum(x[e][i] for e in range(E)) <= 1)

        # ---------------- Contraintes binaires « dures »
        # Imports locaux pour éviter dépendances circulaires
        from ..contraintes.binaires import (
            DoiventEtreSurMemeTable,
            DoiventEtreEloignes,
            DoiventEtreAdjacents,
        )

        # (a) Même table : pour tout couple de sièges de tables différentes -> interdit
        for c in contraintes:
            if isinstance(c, DoiventEtreSurMemeTable):
                a: int = eleves.index(c.a)
                b: int = eleves.index(c.b)
                for i in range(S):
                    for j in range(S):
                        if seats[i].table_key != seats[j].table_key:
                            model.Add(x[a][i] + x[b][j] <= 1)

        # (b) Eloignés d’au moins d (distance de Manhattan sur (x,y))
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

        # (c) Adjacent : toutes paires non adjacentes interdites
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

        # ---------------- Occupation par siège (occ[i] = OR_e x[e][i]) pour les objectifs
        occ: List[cp_model.IntVar] = [model.NewBoolVar(f"occ_s{i}") for i in range(S)]
        for i in range(S):
            # Ici, comme ∑_e x[e][i] ∈ {0,1}, on peut imposer l’égalité
            model.Add(occ[i] == sum(x[e][i] for e in range(E)))

        # ---------------- Objectif (1) : somme des rangs Y
        max_y: int = max((st.y for st in seats), default=0)
        sumY: cp_model.IntVar = model.NewIntVar(0, max(0, E * max_y), "sumY")
        model.Add(sumY == sum(seats[i].y * x[e][i] for e in range(E) for i in range(S)))

        # ---------------- Préparation des objectifs (2) et (3)

        # Adjacences par siège
        neighbors_of: DefaultDict[int, List[int]] = defaultdict(list)
        for (i, j) in edges_adj:
            neighbors_of[i].append(j)
            neighbors_of[j].append(i)

        # paires adjacentes « occupées » (indépendantes du genre)
        pair_used: Dict[Tuple[int, int], cp_model.IntVar] = {}
        for (i, j) in edges_adj:
            v = model.NewBoolVar(f"pair_used_{i}_{j}")
            # v = occ[i] AND occ[j]
            model.Add(v <= occ[i])
            model.Add(v <= occ[j])
            model.Add(v >= occ[i] + occ[j] - 1)
            pair_used[(i, j)] = v

        # has_neighbor[i] = OR des pair_used sur les arêtes incidentes à i
        has_neighbor: List[cp_model.IntVar] = [model.NewBoolVar(f"hasN_s{i}") for i in range(S)]
        for i in range(S):
            if not neighbors_of[i]:
                model.Add(has_neighbor[i] == 0)
            else:
                incident = [pair_used[(min(i, j), max(i, j))] for j in neighbors_of[i]]
                # has_neighbor[i] == (∑ incident > 0) via encadrement booléen
                model.Add(has_neighbor[i] <= sum(incident))
                # Si aucune arête occupée, has_neighbor[i] doit être 0
                model.Add(sum(incident) >= has_neighbor[i])

        # iso[i] = occ[i] AND NOT has_neighbor[i]
        iso: List[cp_model.IntVar] = [model.NewBoolVar(f"iso_s{i}") for i in range(S)]
        for i in range(S):
            model.Add(iso[i] <= occ[i])
            model.Add(iso[i] + has_neighbor[i] <= 1)
            model.Add(iso[i] >= occ[i] - has_neighbor[i])

        nb_isoles: cp_model.IntVar = model.NewIntVar(0, len(eleves), "nb_isoles")
        model.Add(nb_isoles == sum(iso))

        # Comptage des paires adjacentes « même genre »
        nb_same: Optional[cp_model.IntVar] = None
        if include_mixage:
            occ_f: List[cp_model.IntVar] = [model.NewBoolVar(f"occF_s{i}") for i in range(S)]
            occ_m: List[cp_model.IntVar] = [model.NewBoolVar(f"occM_s{i}") for i in range(S)]

            idx_f: List[int] = [e for e, el in enumerate(eleves) if self._genre_code(getattr(el, "genre", None)) == "f"]
            idx_m: List[int] = [e for e, el in enumerate(eleves) if self._genre_code(getattr(el, "genre", None)) == "m"]

            for i in range(S):
                if idx_f:
                    model.Add(occ_f[i] == sum(x[e][i] for e in idx_f))
                else:
                    model.Add(occ_f[i] == 0)
                if idx_m:
                    model.Add(occ_m[i] == sum(x[e][i] for e in idx_m))
                else:
                    model.Add(occ_m[i] == 0)

            same_terms: List[cp_model.IntVar] = []
            for (i, j) in edges_adj:
                vf = model.NewBoolVar(f"pairF_{i}_{j}")
                vm = model.NewBoolVar(f"pairM_{i}_{j}")
                # deux filles adjacentes
                model.Add(vf <= occ_f[i])
                model.Add(vf <= occ_f[j])
                model.Add(vf >= occ_f[i] + occ_f[j] - 1)
                # deux garçons adjacents
                model.Add(vm <= occ_m[i])
                model.Add(vm <= occ_m[j])
                model.Add(vm >= occ_m[i] + occ_m[j] - 1)
                same_terms.append(vf)
                same_terms.append(vm)

            nb_same = model.NewIntVar(0, 2 * len(edges_adj), "nb_same_gender_pairs")
            model.Add(nb_same == sum(same_terms))

        return model, x, sumY, nb_isoles, nb_same

    # --------------------------------------------------------------------- Aides de modélisation

    @staticmethod
    def _enumerate_seats(salle: Salle) -> List[_Seat]:
        """Liste structurée des sièges disponibles dans la salle."""
        seats: List[_Seat] = []
        for idx, p in enumerate(salle.toutes_les_places()):
            seats.append(_Seat(idx=idx, x=p.x, y=p.y, s=p.siege, table_key=(p.x, p.y)))
        return seats

    def _compute_allowed_domains(
            self,
            salle: Salle,
            eleves: Sequence[Eleve],
            contraintes: Sequence[Contrainte],
            seats: Sequence[_Seat],
    ) -> Dict[int, Set[int]]:
        """
        Domaine autorisé par élève :
          - base = tous les sièges
          - intersection avec tous les `places_autorisees(eleve, salle)` fournis
            par les contraintes unaires et structurelles.
        """
        all_ids: Set[int] = {st.idx for st in seats}
        allowed_by_e: Dict[int, Set[int]] = {e_idx: set(all_ids) for e_idx in range(len(eleves))}

        # Application des filtres de chaque contrainte
        for c in contraintes:
            impliques: Sequence[Eleve] = c.implique() or []
            if impliques:
                for e in impliques:
                    e_idx: int = eleves.index(e)
                    allowed: Optional[Iterable[Position]] = c.places_autorisees(e, salle)
                    if allowed is not None:
                        ids = {self._seat_index_of(p, seats) for p in allowed}
                        allowed_by_e[e_idx] &= ids
            else:
                # Contrainte « globale » : appliquer le filtrage (s’il existe) à tous
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
        """Réduction à un singleton en cas de `DoitEtreExactementIci`."""
        for c in contraintes:
            if c.__class__.__name__ == "DoitEtreExactementIci":
                e: Eleve = getattr(c, "eleve")
                p: Position = getattr(c, "ou")
                e_idx: int = eleves.index(e)
                seat_id: int = SolveurCPSAT._seat_index_of(p, seats)
                allowed_by_e[e_idx].intersection_update({seat_id})

    @staticmethod
    def _adjacent_edges_same_table(seats: Sequence[_Seat]) -> List[Tuple[int, int]]:
        """
        Paires (i, j) de sièges adjacents sur la même table (|s_i - s_j| = 1).
        Les paires sont renvoyées avec i < j.
        """
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
        """Recherche linéaire sûre (S est petit) de l’index du siège correspondant à Position p."""
        for st in seats:
            if st.x == p.x and st.y == p.y and st.s == p.siege:
                return st.idx
        raise KeyError("Position inconnue dans l’inventaire des sièges")

    @staticmethod
    def _genre_code(g: Optional[str]) -> Optional[str]:
        """
        Normalisation du genre :
          - "f", "femme", "féminin", "female" → "f"
          - "m", "masculin", "male", "g", "garçon" → "m"
          - sinon : None
        """
        if not g:
            return None
        gg = g.strip().lower()
        if gg.startswith("f"):
            return "f"
        if gg.startswith("m") or gg.startswith("g"):
            return "m"
        return None

    @staticmethod
    def _make_solver(time_limit_s: Optional[float]) -> cp_model.CpSolver:
        """Instancie un solveur avec paramétrage standard pour ce cas d’usage."""
        solver = cp_model.CpSolver()
        if time_limit_s is not None:
            solver.parameters.max_time_in_seconds = max(0.1, time_limit_s)
        # Multithread raisonnable ; adapter si besoin
        solver.parameters.num_search_workers = 8
        # Des paramètres supplémentaires (lns, sym_break) peuvent être essayés si nécessaire.
        return solver

    # ------------------- Vérifications préalables (“fail fast”) --------------------------

    @staticmethod
    def _sanity_check(salle: Salle, eleves: Sequence[Eleve], contraintes: Sequence[Contrainte]) -> None:
        """
        Valide des conditions simples avant la modélisation CP-SAT.

        Vérifie :
        - nombre total de sièges suffisant pour tous les élèves,
        - absence de collision entre sièges imposés (DoitEtreExactementIci),
        - cohérence entre sièges imposés et tables interdites.

        Lève ValueError en cas d’anomalie détectée.
        """
        # 1) Capacité totale suffisante
        total_seats: int = sum(len(ps) for ps in salle.positions_par_table().values())
        nb_eleves: int = len(eleves)
        if nb_eleves > total_seats:
            raise ValueError(f"{nb_eleves} élèves pour {total_seats} sièges disponibles.")

        # 2) Collisions de sièges exacts (deux élèves sur le même (x,y,s))
        exact_positions: Set[Tuple[int, int, int]] = set()
        nom_exact: str = "DoitEtreExactementIci"  # évite l’import direct pour circulaires
        for c in contraintes:
            if c.__class__.__name__ == nom_exact:
                p: Position = getattr(c, "ou")  # attendu : Position
                key: Tuple[int, int, int] = (p.x, p.y, p.siege)
                if key in exact_positions:
                    raise ValueError("Deux élèves ne peuvent pas avoir le même siège imposé.")
                exact_positions.add(key)

        # 3) Conflits « siège exact » vs « table interdite »
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
