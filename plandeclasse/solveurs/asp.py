from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Optional

import clingo

from ..modele.eleve import Eleve
from ..modele.position import Position
from ..modele.salle import Salle
from ..contraintes.base import Contrainte, ASPContext
from ..solveurs.base import ResultatResolution, Solveur

# Contraintes pour isinstance()
from ..contraintes.unaires import (
    DoitEtreDansPremieresRangees,
    DoitEtreExactementIci,
    DoitEtreSeulALaTable,
)
from ..contraintes.binaires import (
    DoiventEtreAdjacents,
    DoiventEtreEloignes,
    DoiventEtreSurMemeTable,
)
from ..contraintes.structurelles import TableDoitEtreVide


@dataclass
class _ContexteASP:
    id_par_eleve: Dict[Eleve, int]
    eleve_par_id: Dict[int, Eleve]


class SolveurClingo(Solveur):
    """Solveur ASP/Clingo sans I/O fichiers."""

    def __init__(self, models: int = 1) -> None:
        super().__init__()
        self.models = models

    # --- API exigée par la classe de base ---
    def resoudre(
            self,
            salle: Salle,
            eleves: Sequence[Eleve],
            contraintes: Sequence[Contrainte],
            *,
            essais_max: int = 10_000,  # ignoré côté ASP, maintenu pour compat
            budget_temps_ms: Optional[int] = None,
    ) -> ResultatResolution:

        ctx = self._contexte(eleves)
        prg = []
        prg.append(self._programme_fixe())
        prg.append(self._faits_salle(salle))
        prg.append(self._faits_eleves(eleves))
        prg.append(self._faits_contraintes(contraintes, ctx=ctx))
        prg_str = "\n".join(prg)

        ctl = clingo.Control(["--opt-mode=optN"])
        if budget_temps_ms is not None and budget_temps_ms > 0:
            # Limite « wall clock » côté solver
            ctl.configuration.solve.solve_limit = f"umax,{budget_temps_ms}ms"

        ctl.add("base", [], prg_str)
        ctl.ground([("base", [])])

        modele_assign: Dict[int, tuple[int, int, int]] = {}

        def on_model(m: clingo.Model) -> None:
            nonlocal modele_assign
            if not modele_assign:  # premier modèle
                modele_assign = self._lire_modele(m)

        res = ctl.solve(on_model=on_model)
        if not res.satisfiable or not modele_assign:
            return ResultatResolution(affectation=None, essais=0, verifications=0)

        # Reconstruction Eleve -> Position
        affectation: Dict[Eleve, Position] = {}
        for sid, (x, y, s) in modele_assign.items():
            e = ctx.eleve_par_id[sid]
            affectation[e] = Position(x=x, y=y, siege=s)

        # Vérifs finales facultatives (ex: voisin vide)
        if not self.valider_final(salle, affectation, contraintes):
            return ResultatResolution(affectation=None, essais=0, verifications=0)

        return ResultatResolution(affectation=affectation, essais=0, verifications=0)

    # ---------- Construction du programme ----------
    def _programme_fixe(self) -> str:
        return r"""
% tables/sièges
seat(X,Y,S) :- table(X,Y,C), S=0..C-1.

% chaque élève occupe exactement un siège
1 { assign(S,X,Y,Sg) : seat(X,Y,Sg) } 1 :- student(S).

% un siège au plus pour une personne
:- assign(S1,X,Y,Sg), assign(S2,X,Y,Sg), S1 != S2.

% tables interdites
:- ban_table(X,Y), assign(_,X,Y,_).

#show assign/4.
"""

    def _faits_salle(self, salle: Salle) -> str:
        caps = salle.capacite_par_table()  # dict[(x,y)] -> cap
        return "".join(f"table({x},{y},{c}).\n" for (x, y), c in caps.items())

    def _faits_eleves(self, eleves: Sequence[Eleve]) -> str:
        return "".join(f"student({i}).\n" for i, _ in enumerate(eleves))

    def _contexte(self, eleves: Sequence[Eleve]) -> _ContexteASP:
        id_par_eleve = {e: i for i, e in enumerate(eleves)}
        eleve_par_id = {i: e for i, e in enumerate(eleves)}
        return _ContexteASP(id_par_eleve=id_par_eleve, eleve_par_id=eleve_par_id)

    def _faits_contraintes(self, contraintes: Sequence[Contrainte], *, ctx: _ContexteASP) -> str:
        asp_ctx = ASPContext(id_par_eleve=ctx.id_par_eleve)
        parts: list[str] = []
        for c in contraintes:
            parts.extend(c.regles_asp(asp_ctx))
        return "\n".join(parts) + ("\n" if parts else "")
            # sinon : contrainte non gérée -> silencieux
            # parts.append(f"% non gérée: {type(c).__name__}")

    # ---------- Lecture du modèle ----------
    def _lire_modele(self, model: clingo.Model) -> Dict[int, tuple[int, int, int]]:
        res: Dict[int, tuple[int, int, int]] = {}
        for atom in model.symbols(shown=True):
            if atom.name == "assign" and len(atom.arguments) == 4:
                s = int(str(atom.arguments[0]))
                x = int(str(atom.arguments[1]))
                y = int(str(atom.arguments[2]))
                sg = int(str(atom.arguments[3]))
                res[s] = (x, y, sg)
        return res
