from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from .base import Contrainte, distance_manhattan, meme_table, ASPContext
from .types import TypeContrainte
from ..modele.eleve import Eleve
from ..modele.position import Position


class DoiventEtreEloignes(Contrainte):
    """Exige que A et B soient séparés d'au moins `d` (distance de Manhattan)."""

    def __init__(self, a: Eleve, b: Eleve, d: int) -> None:
        assert d >= 1, "d doit être >= 1"
        self.a: Eleve = a
        self.b: Eleve = b
        self.d: int = d

    def type_contrainte(self) -> TypeContrainte:
        return TypeContrainte.ELOIGNES

    def implique(self) -> Sequence[Eleve]:
        return [self.a, self.b]

    def est_satisfaite(self, affectation: Dict[Eleve, Position]) -> bool:
        pa: Optional[Position] = affectation.get(self.a)
        pb: Optional[Position] = affectation.get(self.b)
        if pa is None or pb is None:
            return True
        return distance_manhattan(pa, pb) >= self.d

    def texte_humain(self) -> str:
        return f"{self.a.affichage_nom()} et {self.b.affichage_nom()} doivent être éloignés d'au moins {self.d}"

    def code_machine(self) -> Dict[str, Any]:
        return {"type": self.type_contrainte().value, "a": self.a.nom, "b": self.b.nom, "d": self.d}

    def regles_asp(self, ctx: ASPContext) -> list[str]:
        a, b = ctx.sid(self.a), ctx.sid(self.b)
        d = int(self.d)
        return [f":- assign({a},X1,Y1,_), assign({b},X2,Y2,_), |X1-X2| + |Y1-Y2| < {d}."]


class DoiventEtreSurMemeTable(Contrainte):
    """Exige que A et B soient sur la même table (mêmes x, y)."""

    def __init__(self, a: Eleve, b: Eleve) -> None:
        self.a: Eleve = a
        self.b: Eleve = b

    def type_contrainte(self) -> TypeContrainte:
        return TypeContrainte.MEME_TABLE

    def implique(self) -> Sequence[Eleve]:
        return [self.a, self.b]

    def est_satisfaite(self, affectation: Dict[Eleve, Position]) -> bool:
        pa: Optional[Position] = affectation.get(self.a)
        pb: Optional[Position] = affectation.get(self.b)
        if pa is None or pb is None:
            return True
        return meme_table(pa, pb)

    def texte_humain(self) -> str:
        return f"{self.a.affichage_nom()} et {self.b.affichage_nom()} doivent être sur la même table"

    def code_machine(self) -> Dict[str, Any]:
        return {"type": self.type_contrainte().value, "a": self.a.nom, "b": self.b.nom}

    def regles_asp(self, ctx: ASPContext) -> Sequence[str]:
        a, b = ctx.sid(self.a), ctx.sid(self.b)
        return [
            f":- assign({a},X1,Y1,_), assign({b},X2,Y2,_), X1 != X2.",
            f":- assign({a},X1,Y1,_), assign({b},X2,Y2,_), Y1 != Y2.",
        ]


class DoiventEtreAdjacents(Contrainte):
    """Exige que A et B soient sur des sièges adjacents de la même table (|i-j| = 1)."""

    def __init__(self, a: Eleve, b: Eleve) -> None:
        self.a: Eleve = a
        self.b: Eleve = b

    def type_contrainte(self) -> TypeContrainte:
        return TypeContrainte.ADJACENTS

    def implique(self) -> Sequence[Eleve]:
        return [self.a, self.b]

    def est_satisfaite(self, affectation: Dict[Eleve, Position]) -> bool:
        pa: Optional[Position] = affectation.get(self.a)
        pb: Optional[Position] = affectation.get(self.b)
        if pa is None or pb is None:
            return True
        return meme_table(pa, pb) and abs(pa.siege - pb.siege) == 1

    def texte_humain(self) -> str:
        return f"{self.a.affichage_nom()} et {self.b.affichage_nom()} doivent être adjacents à la même table"

    def code_machine(self) -> Dict[str, Any]:
        return {"type": self.type_contrainte().value, "a": self.a.nom, "b": self.b.nom}

    def regles_asp(self, ctx: ASPContext) -> Sequence[str]:
        a, b = ctx.sid(self.a), ctx.sid(self.b)
        return [
            f":- assign({a},X1,Y1,_), assign({b},X2,Y2,_), X1 != X2.",
            f":- assign({a},X1,Y1,_), assign({b},X2,Y2,_), Y1 != Y2.",
            f":- assign({a},_,_,S1), assign({b},_,_,S2), |S1-S2| != 1.",
        ]
