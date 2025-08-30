# plandeclasse/solveurs/asp.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Sequence, Optional, Tuple, List, Set

import clingo

from ..modele.eleve import Eleve
from ..modele.position import Position
from ..modele.salle import Salle
from ..contraintes.base import Contrainte, ASPContext
from ..solveurs.base import ResultatResolution, Solveur


@dataclass
class _ContexteASP:
    """
    Contexte interne pour la traduction ASP :
    - id_par_eleve : mapping Eleve -> identifiant entier (côté ASP)
    - eleve_par_id : mapping inverse identifiant -> Eleve (reconstruction)
    """
    id_par_eleve: Dict[Eleve, int]
    eleve_par_id: Dict[int, Eleve]


class SolveurClingo(Solveur):
    """
    Solveur basé sur Clingo (Answer Set Programming) sans I/O fichiers.

    Objectifs (lexicographiquement ordonnés dans le programme) :
      @1 Minimiser la distance au tableau (somme des rangs Y).
      @2 Maximiser les élèves isolés (aucun voisin adjacent sur la même table).
      @3 Minimiser les paires adjacentes de même genre.

    Remarques d’implémentation :
    - Le programme fixe contient les directives d’optimisation (#minimize/#maximize) avec priorités.
    - L’API Clingo est utilisée sans options CLI ; si disponible, opt_mode "optN" est activé.
    - La résolution asynchrone permet de borner l’attente (budget_temps_ms). En cas de dépassement,
      le meilleur modèle rencontré est conservé (s’il existe), sinon aucun modèle n’est retourné.
    """

    def __init__(
            self,
            *,
            prefer_alone: bool = True,
            prefer_mixage: bool = True,
            models: int = 1,
    ) -> None:
        super().__init__()
        self.models: int = models
        self.prefer_alone: bool = prefer_alone
        self.prefer_mixage: bool = prefer_mixage

    # ------------------------- API Solveur ---------------------------------

    def resoudre(
            self,
            salle: Salle,
            eleves: Sequence[Eleve],
            contraintes: Sequence[Contrainte],
            *,
            essais_max: int = 10_000,  # ignoré côté ASP (compat API)
            budget_temps_ms: Optional[int] = None,  # timeout mur en millisecondes
    ) -> ResultatResolution:
        """
        Construit le programme ASP, lance la résolution, puis reconstruit l’affectation.
        """
        # 1) Vérifications préalables rapides (fail-fast)
        self._sanity_check(salle, eleves, contraintes)

        # 2) Contexte d’identifiants élèves
        ctx: _ContexteASP = self._contexte(eleves)

        # 3) Programme ASP (squelette + faits)
        parts: List[str] = [
            self._programme_fixe(),
            self._faits_salle(salle),
            self._faits_eleves(eleves),
            self._faits_contraintes(contraintes, ctx=ctx),
            self._faits_allow(salle, eleves, contraintes, ctx=ctx),
            self._faits_objectifs(),
        ]
        prg_str: str = "\n".join(parts)

        # 4) Configuration Clingo (pas d’arguments CLI pour compatibilité)
        ctl: clingo.Control = clingo.Control([])
        ctl.configuration.solve.models = self.models
        # Sélection du mode d’optimisation lexicographique si disponible
        try:
            ctl.configuration.solve.opt_mode = "optN"
        except Exception:
            pass  # attribut absent selon les versions

        # 5) Chargement et grounding
        ctl.add("base", [], prg_str)
        ctl.ground([("base", [])])

        # 6) Résolution (capture du meilleur modèle rencontré)
        best_model_assign: Dict[int, Tuple[int, int, int]] = {}

        def on_model(m: clingo.Model) -> None:
            # Mise à jour à chaque modèle trouvé ; le dernier sera optimal si la résolution termine
            nonlocal best_model_assign
            best_model_assign = self._lire_modele(m)

        handle = ctl.solve(on_model=on_model, async_=True)

        # Attente bornée si budget fourni, sinon attente complète
        if budget_temps_ms and budget_temps_ms > 0:
            handle.wait(budget_temps_ms / 1000.0)
        else:
            handle.wait()

        res: clingo.SolveResult = handle.get()
        try:
            handle.cancel()
        except Exception:
            pass

        # 7) Gestion des cas sans solution
        if not res.satisfiable or not best_model_assign:
            return ResultatResolution(affectation=None, essais=0, verifications=0)

        # 8) Reconstruction Eleve -> Position
        affectation: Dict[Eleve, Position] = {}
        for sid, (x, y, s) in best_model_assign.items():
            e: Eleve = ctx.eleve_par_id[sid]
            affectation[e] = Position(x=x, y=y, siege=s)

        # 9) Vérifications finales locales (si nécessaire)
        if not self.valider_final(salle, affectation, contraintes):
            return ResultatResolution(affectation=None, essais=0, verifications=0)

        return ResultatResolution(affectation=affectation, essais=0, verifications=0)

    # --------------------- Construction du programme -----------------------

    @staticmethod
    def _programme_fixe() -> str:
        """
        Squelette ASP indépendant des instances.

        Règles:
        - Génération des sièges via table/3 -> seat/3.
        - Affectation contrainte à allow/4.
        - Exclusivité de siège.
        - Interdictions globales (ban_table/2, ban_seat/3).
        - Objectifs @1, @2, @3.
        """
        return r"""
% sièges
seat(X,Y,S) :- table(X,Y,C), S=0..C-1.

% affectation restreinte par allow/4
1 { assign(S,X,Y,Sg) : allow(S,X,Y,Sg) } 1 :- student(S).

% exclusivité
:- assign(S1,X,Y,Sg), assign(S2,X,Y,Sg), S1 != S2.

% interdictions table/siège
:- ban_table(X,Y), assign(_,X,Y,_).
:- ban_seat(X,Y,Sg), assign(_,X,Y,Sg).

% (1) distance au tableau — priorité @1
dist(S,Y) :- assign(S,_,Y,_).
#minimize { Y@1,S : dist(S,Y) }.

% (2) isolés à la table — priorité @2
neighbor(I,J) :- I=0..100, J=0..100, |I-J|=1.
isolated(S) :- assign(S,X,Y,I), 0 = #count{ S2 : assign(S2,X,Y,J), neighbor(I,J) }.
#maximize { 1@2,S : isolated(S) }.

% (3) mixage de genre — priorité @3
pair(S1,S2) :- assign(S1,X,Y,I), assign(S2,X,Y,J), S1 < S2, |I - J| = 1.
same_gender_pair(S1,S2) :- pair(S1,S2), gender(S1,G), gender(S2,G).
#minimize { 1@3,S1,S2 : same_gender_pair(S1,S2) }.

#show assign/4.
"""

    @staticmethod
    def _faits_allow(
            salle: Salle,
            eleves: Sequence[Eleve],
            contraintes: Sequence[Contrainte],
            ctx: _ContexteASP,
    ) -> str:
        """
        Construit les faits allow(S,X,Y,Sg) en combinant les filtrages
        proposés par places_autorisees(eleve, salle).
        """
        # Domaine de base : tous les sièges pour tous
        base_allowed: Set[Tuple[int, int, int, int]] = {
            (ctx.id_par_eleve[e], p.x, p.y, p.siege)
            for e in eleves
            for p in salle.toutes_les_places()
        }

        # Filtres par élève (intersection progressive)
        per_student_filters: Dict[int, Set[Tuple[int, int, int, int]]] = {}

        for c in contraintes:
            impliques: Sequence[Eleve] = c.implique() or []
            for e in impliques:
                allowed = c.places_autorisees(e, salle)
                if allowed is not None:
                    sid: int = ctx.id_par_eleve[e]
                    sset: Set[Tuple[int, int, int, int]] = {
                        (sid, p.x, p.y, p.siege) for p in allowed
                    }
                    if sid in per_student_filters:
                        per_student_filters[sid] &= sset
                    else:
                        per_student_filters[sid] = sset

        # Application des filtres au domaine de base
        final: Set[Tuple[int, int, int, int]] = set()
        for sid, x, y, sg in base_allowed:
            filt = per_student_filters.get(sid)
            if filt is None or (sid, x, y, sg) in filt:
                final.add((sid, x, y, sg))

        # Sérialisation
        return "".join(f"allow({sid},{x},{y},{sg}).\n" for sid, x, y, sg in final)

    @staticmethod
    def _faits_salle(salle: Salle) -> str:
        """ Sérialise la salle en faits table(X,Y,C). """
        caps: Dict[Tuple[int, int], int] = salle.capacite_par_table()
        return "".join(f"table({x},{y},{c}).\n" for (x, y), c in caps.items())

    @staticmethod
    def _faits_eleves(eleves: Sequence[Eleve]) -> str:
        """
        Sérialise les élèves :
          - student(ID).
          - gender(ID,f). / gender(ID,m). si disponible (robuste à F/G, f/m, féminin/masculin).
        """
        parts: List[str] = []
        for i, e in enumerate(eleves):
            parts.append(f"student({i}).")
            g_raw: Optional[str] = getattr(e, "genre", None)
            if g_raw:
                g: str = g_raw.strip().lower()
                if g.startswith("f"):  # f, féminin, female…
                    parts.append(f"gender({i},f).")
                elif g.startswith("m") or g.startswith("g"):  # m/masculin/male ou g/garçon
                    parts.append(f"gender({i},m).")
        return "\n".join(parts) + "\n"

    @staticmethod
    def _contexte(eleves: Sequence[Eleve]) -> _ContexteASP:
        """ Construit les mappings Eleve <-> identifiant entier (ASP). """
        id_par_eleve: Dict[Eleve, int] = {e: i for i, e in enumerate(eleves)}
        eleve_par_id: Dict[int, Eleve] = {i: e for i, e in enumerate(eleves)}
        return _ContexteASP(id_par_eleve=id_par_eleve, eleve_par_id=eleve_par_id)

    @staticmethod
    def _faits_contraintes(contraintes: Sequence[Contrainte], *, ctx: _ContexteASP) -> str:
        """ Agrège les règles ASP exposées par chaque contrainte via regles_asp(). """
        asp_ctx: ASPContext = ASPContext(id_par_eleve=ctx.id_par_eleve)
        parts: List[str] = []
        for c in contraintes:
            parts.extend(c.regles_asp(asp_ctx))
        return "\n".join(parts) + ("\n" if parts else "")

    def _faits_objectifs(self) -> str:
        """
        Active/désactive @2 et @3 de manière neutre si demandé.
        Le squelette contient déjà #maximize/#minimize pour @2/@3.
        """
        parts: List[str] = []
        if not self.prefer_alone:
            parts.append("% objectif @2 désactivé")
            parts.append("#maximize { 0@2,S : isolated(S) }.")  # neutre
        if not self.prefer_mixage:
            parts.append("% objectif @3 désactivé")
            parts.append("#minimize { 0@3,S1,S2 : same_gender_pair(S1,S2) }.")  # neutre
        return ("\n".join(parts) + "\n") if parts else ""

    # ----------------------- Lecture du modèle -----------------------------

    @staticmethod
    def _lire_modele(model: clingo.Model) -> Dict[int, Tuple[int, int, int]]:
        """ Extrait assign(S,X,Y,Seat) (#show) -> dict S -> (X,Y,Seat). """
        res: Dict[int, Tuple[int, int, int]] = {}
        for atom in model.symbols(shown=True):
            if atom.name == "assign" and len(atom.arguments) == 4:
                s: int = int(str(atom.arguments[0]))
                x: int = int(str(atom.arguments[1]))
                y: int = int(str(atom.arguments[2]))
                sg: int = int(str(atom.arguments[3]))
                res[s] = (x, y, sg)
        return res

    # ------------------- Vérifications préalables --------------------------

    @staticmethod
    def _sanity_check(salle: Salle, eleves: Sequence[Eleve], contraintes: Sequence[Contrainte]) -> None:
        """
        Valide rapidement des conditions simples avant de lancer Clingo.

        Vérifie :
        - nombre de sièges suffisant,
        - absence de collision sur des sièges imposés (DoitEtreExactementIci),
        - absence d’incohérence entre sièges imposés et tables interdites.

        Lève ValueError en cas d’anomalie.
        """
        # 1) Nombre de sièges suffisant
        total_seats: int = sum(len(ps) for ps in salle.positions_par_table().values())
        nb_eleves: int = len(eleves)
        if nb_eleves > total_seats:
            raise ValueError(f"{nb_eleves} élèves pour {total_seats} sièges disponibles.")

        # 2) Collisions de sièges exacts
        exact_positions: Set[Tuple[int, int, int]] = set()
        nom_exact: str = "DoitEtreExactementIci"  # import tardif évité
        for c in contraintes:
            if c.__class__.__name__ == nom_exact:
                p: Position = getattr(c, "ou")  # attendu : Position
                key: Tuple[int, int, int] = (p.x, p.y, p.siege)
                if key in exact_positions:
                    raise ValueError("Deux élèves ne peuvent pas avoir le même siège imposé.")
                exact_positions.add(key)

        # 3) Conflits avec tables interdites
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
