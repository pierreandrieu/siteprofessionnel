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
    - `id_par_eleve` : mapping Eleve -> identifiant entier (côté ASP)
    - `eleve_par_id` : mapping inverse identifiant -> Eleve (reconstruction)
    """
    id_par_eleve: Dict[Eleve, int]
    eleve_par_id: Dict[int, Eleve]


class SolveurClingo(Solveur):
    """
    Solveur basé sur Clingo (Answer Set Programming) sans I/O fichiers.

    Principe
    --------
    - Les contraintes « dures » exposent des règles via `regles_asp()`.
    - Certaines contraintes unaires/structurelles réduisent le domaine des sièges
      via `places_autorisees(...)`. Ces filtrages sont compilés en faits `allow/4`
      et la règle d'affectation s'appuie **uniquement** sur ces `allow/4`.
    - Trois objectifs optionnels et *lexicographiquement ordonnés* :
        (1) Minimiser la distance au tableau (somme des rangs Y) — toujours actif
        (2) Maximiser les élèves seuls à une table — option `prefer_alone`
        (3) Minimiser les paires adjacentes de même genre — option `prefer_mixage`

    Paramètres
    ----------
    prefer_alone : bool
        Active l’objectif (2) si True.
    prefer_mixage : bool
        Active l’objectif (3) si True.
    models : int
        Limite de modèles renvoyés par Clingo (par défaut 1).

    Remarque
    --------
    Le solveur capture le **premier modèle optimal** (lexicographiquement)
    renvoyé par Clingo, conformément à `--opt-mode=optN`.
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

    # --- API exigée par la classe de base ---------------------------------

    def resoudre(
            self,
            salle: Salle,
            eleves: Sequence[Eleve],
            contraintes: Sequence[Contrainte],
            *,
            essais_max: int = 10_000,  # ignoré côté ASP (compat API)
            budget_temps_ms: Optional[int] = None,  # limite mur en millisecondes
    ) -> ResultatResolution:
        """
        Construit et résout le programme ASP, puis reconstruit l’affectation.

        Étapes :
        - vérifications rapides (sièges suffisants, collisions, incohérences),
        - construction des faits ASP (salle, élèves, contraintes, allow/4, objectifs),
        - appel Clingo avec `--time-limit` si fourni,
        - lecture du premier modèle optimal et reconstruction Eleve -> Position,
        - validations finales locales dépendant des capacités de tables.
        """
        # 1) Vérifications rapides pour économiser le temps de résolution
        self._sanity_check(salle, eleves, contraintes)

        # 2) Contexte d’identifiants pour les élèves
        ctx: _ContexteASP = self._contexte(eleves)

        # 3) Programme ASP (squelette + faits)
        parts: List[str] = [
            self._programme_fixe(),
            self._faits_salle(salle),
            self._faits_eleves(eleves),
            self._faits_contraintes(contraintes, ctx=ctx),
            SolveurClingo._faits_allow(salle, eleves, contraintes, ctx=ctx),
            self._faits_objectifs(),
        ]
        prg_str: str = "\n".join(parts)

        # 4) Configuration Clingo
        args: List[str] = ["--opt-mode=optN"]
        # Optionnel : un profil généralement performant
        # args += ["--configuration=trendy"]
        if budget_temps_ms and budget_temps_ms > 0:
            # Clingo attend des secondes entières
            args.append(f"--time-limit={int(budget_temps_ms // 1000)}")
        ctl: clingo.Control = clingo.Control(args)
        ctl.configuration.solve.models = self.models

        # 5) Charge et ground le programme (pas d’I/O fichiers)
        ctl.add("base", [], prg_str)
        ctl.ground([("base", [])])

        # 6) Résolution (capture du premier modèle optimal)
        modele_assign: Dict[int, Tuple[int, int, int]] = {}

        def on_model(m: clingo.Model) -> None:
            nonlocal modele_assign
            if not modele_assign:  # capture uniquement le premier modèle
                modele_assign = self._lire_modele(m)

        res: clingo.SolveResult = ctl.solve(on_model=on_model)

        # 7) Gestion des cas sans solution
        if not res.satisfiable or not modele_assign:
            return ResultatResolution(affectation=None, essais=0, verifications=0)

        # 8) Reconstruction Eleve -> Position
        affectation: Dict[Eleve, Position] = {}
        for sid, (x, y, s) in modele_assign.items():
            e: Eleve = ctx.eleve_par_id[sid]
            affectation[e] = Position(x=x, y=y, siege=s)

        # 9) Vérifications finales locales (ex : voisin vide)
        if not self.valider_final(salle, affectation, contraintes):
            return ResultatResolution(affectation=None, essais=0, verifications=0)

        return ResultatResolution(affectation=affectation, essais=0, verifications=0)

    # ---------- Construction du programme ASP ------------------------------

    @staticmethod
    def _programme_fixe() -> str:
        """
        Squelette ASP indépendant des instances.

        Règles :
        - Génère les sièges (via `seat/3`) à partir de `table/3`.
        - Chaque élève prend exactement un siège **parmi `allow/4`**.
        - Pas de double-occupation de siège.
        - Interdit les tables bannies (si présentes via `ban_table/2`).
        - Définit des prédicats auxiliaires pour objectifs (dist, alone, pairs, etc.).
        - Montre `assign/4` pour la lecture du modèle.
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

% (1) distance au tableau
dist(S,Y) :- assign(S,_,Y,_).
#minimize { Y@1,S : dist(S,Y) }.

% (2) "sans voisins" : aucun élève adjacent (|I-J|=1) à la même table
neighbor(I,J) :- I=0..100, J=0..100, |I-J|=1.
isolated(S) :- assign(S,X,Y,I), 0 = #count{ S2 : assign(S2,X,Y,J), neighbor(I,J) }.
% activé via #maximize ajouté dynamiquement

% (3) mixage de genre (paires adjacentes même genre)
pair(S1,S2) :- assign(S1,X,Y,I), assign(S2,X,Y,J), S1 < S2, |I - J| = 1.
same_gender_pair(S1,S2) :- pair(S1,S2), gender(S1,G), gender(S2,G).

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
        Construit les faits `allow(S,X,Y,Sg).` en combinant les filtrages
        proposés par `places_autorisees(eleve, salle)`.

        Stratégie :
        - Domaine de base = tous les sièges possibles pour chaque élève.
        - Pour chaque contrainte fournissant un filtrage pour un élève,
          on **intersecte** ce filtrage avec le domaine courant de cet élève.
        - Le résultat final (par élève) est sérialisé en faits `allow/4`.
        """
        # Domaine de base : tous sièges pour tous les élèves
        base_allowed: Set[Tuple[int, int, int, int]] = {
            (ctx.id_par_eleve[e], p.x, p.y, p.siege)
            for e in eleves
            for p in salle.toutes_les_places()
        }

        # Filtres par élève issus des contraintes (intersection progressive)
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
            filt: Optional[Set[Tuple[int, int, int, int]]] = per_student_filters.get(sid)
            if filt is None or (sid, x, y, sg) in filt:
                final.add((sid, x, y, sg))

        # Sérialisation en faits ASP
        return "".join(f"allow({sid},{x},{y},{sg}).\n" for sid, x, y, sg in final)

    @staticmethod
    def _faits_salle(salle: Salle) -> str:
        """
        Traduit la salle en faits `table(X,Y,C).`
        où C est la capacité (nombre de sièges) de la table (X,Y).
        """
        caps: Dict[Tuple[int, int], int] = salle.capacite_par_table()
        return "".join(f"table({x},{y},{c}).\n" for (x, y), c in caps.items())

    @staticmethod
    def _faits_eleves(eleves: Sequence[Eleve]) -> str:
        """
        Traduit les élèves en :
          - `student(ID).`
          - `gender(ID,f).` ou `gender(ID,m).` si le genre est fourni.

        NB : `gender/2` est utilisé par l’objectif de mixage, mais **facultatif**.
        """
        parts: List[str] = []
        for i, e in enumerate(eleves):
            parts.append(f"student({i}).")
            g_raw: Optional[str] = getattr(e, "genre", None)
            if g_raw:
                g: str = g_raw.strip().lower()
                if g.startswith("f"):
                    parts.append(f"gender({i},f).")
                elif g.startswith("m"):
                    parts.append(f"gender({i},m).")
        return "\n".join(parts) + "\n"

    @staticmethod
    def _contexte(eleves: Sequence[Eleve]) -> _ContexteASP:
        """
        Construit les mappings entre objets `Eleve` et identifiants ASP (entiers).
        """
        id_par_eleve: Dict[Eleve, int] = {e: i for i, e in enumerate(eleves)}
        eleve_par_id: Dict[int, Eleve] = {i: e for i, e in enumerate(eleves)}
        return _ContexteASP(id_par_eleve=id_par_eleve, eleve_par_id=eleve_par_id)

    @staticmethod
    def _faits_contraintes(contraintes: Sequence[Contrainte], *, ctx: _ContexteASP) -> str:
        """
        Agrège les règles ASP fournies par chaque contrainte via `regles_asp()`.

        Si une contrainte ne fournit pas d’encodage ASP, elle est silencieusement ignorée
        côté ASP (mais pourra être vérifiée en post-traitement si nécessaire).
        """
        asp_ctx: ASPContext = ASPContext(id_par_eleve=ctx.id_par_eleve)
        parts: List[str] = []
        for c in contraintes:
            parts.extend(c.regles_asp(asp_ctx))
        return "\n".join(parts) + ("\n" if parts else "")

    def _faits_objectifs(self) -> str:
        """
        Émet les directives d’optimisation dépendant des options du solveur.

        Ordre lexicographique :
          - @1 : distance (toujours présente dans le squelette)
          - @2 : maximiser `alone(S)` (si `prefer_alone`)
          - @3 : minimiser `same_gender_pair/2` (si `prefer_mixage`)
        """
        parts: List[str] = []
        if self.prefer_alone:
            parts.append("#maximize { 1@2,S : isolated(S) }.")
        if self.prefer_mixage:
            parts.append("#minimize { 1@3,S1,S2 : same_gender_pair(S1,S2) }.")
        return ("\n".join(parts) + "\n") if parts else ""

    # ---------- Lecture du modèle -----------------------------------------

    @staticmethod
    def _lire_modele(model: clingo.Model) -> Dict[int, Tuple[int, int, int]]:
        """
        Extrait les atomes `assign(S,X,Y,Seat)` montrés (#show) et les convertit
        en dictionnaire `S -> (X, Y, Seat)`.
        """
        res: Dict[int, Tuple[int, int, int]] = {}
        for atom in model.symbols(shown=True):
            if atom.name == "assign" and len(atom.arguments) == 4:
                s: int = int(str(atom.arguments[0]))
                x: int = int(str(atom.arguments[1]))
                y: int = int(str(atom.arguments[2]))
                sg: int = int(str(atom.arguments[3]))
                res[s] = (x, y, sg)
        return res

    # ---------- Vérifications préalables (“fail fast”) ---------------------

    @staticmethod
    def _sanity_check(salle: Salle, eleves: Sequence[Eleve], contraintes: Sequence[Contrainte]) -> None:
        """
        Valide rapidement des conditions simples avant de lancer Clingo.

        Vérifie :
        - nombre de sièges suffisant,
        - absence de collision sur des sièges imposés (`DoitEtreExactementIci`),
        - absence d’incohérence entre sièges imposés et tables interdites.
        Lève `ValueError` en cas d’anomalie.
        """
        # 1) Nombre de sièges suffisant
        total_seats: int = sum(len(ps) for ps in salle.positions_par_table().values())
        nb_eleves: int = len(eleves)
        if nb_eleves > total_seats:
            raise ValueError(f"{nb_eleves} élèves pour {total_seats} sièges disponibles.")

        # 2) Collisions de sièges exacts
        exact_positions: Set[Tuple[int, int, int]] = set()
        # Import tardif doux pour éviter un import circulaire (nom symbolique)
        nom_exact: str = "DoitEtreExactementIci"
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
