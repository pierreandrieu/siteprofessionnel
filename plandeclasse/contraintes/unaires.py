from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Sequence

from .base import Contrainte, meme_table, ASPContext
from .types import TypeContrainte
from ..modele.eleve import Eleve
from ..modele.position import Position
from ..modele.salle import Salle


class DoitEtreDansPremieresRangees(Contrainte):
    """Exige que l'élève soit dans les `k` premières rangées (y < k)."""

    def __init__(self, eleve: Eleve, k: int) -> None:
        assert k >= 1, "k doit être >= 1"
        self.eleve: Eleve = eleve
        self.k: int = k

    def type_contrainte(self) -> TypeContrainte:
        return TypeContrainte.PREMIERES_RANGEES

    def implique(self) -> Sequence[Eleve]:
        return [self.eleve]

    def places_autorisees(self, eleve: Eleve, salle: Salle) -> Optional[Iterable[Position]]:
        if eleve is not self.eleve:
            return None
        return [p for p in salle.toutes_les_places() if p.y < self.k]

    def est_satisfaite(self, affectation: Dict[Eleve, Position]) -> bool:
        pos: Optional[Position] = affectation.get(self.eleve)
        return True if pos is None else (pos.y < self.k)

    def texte_humain(self) -> str:
        return f"{self.eleve.affichage_nom()} doit être dans les {self.k} premières rangées"

    def code_machine(self) -> Dict[str, Any]:
        return {"type": self.type_contrainte().value, "eleve": self.eleve.nom, "k": self.k}

    def regles_asp(self, ctx: ASPContext) -> list[str]:
        s = ctx.id_par_eleve[self.eleve]
        return [f":- assign({s},_,Y,_), Y >= {int(self.k)}."]


class DoitEtreDansDernieresRangees(Contrainte):
    """Exige que l'élève soit dans les `k` dernières rangées (y ≥ max_y − k + 1)."""

    def __init__(self, eleve: Eleve, k: int, salle: Salle) -> None:
        assert k >= 1
        self.eleve: Eleve = eleve
        self.k: int = k
        self._max_y: int = salle.max_y()

    def type_contrainte(self) -> TypeContrainte:
        return TypeContrainte.DERNIERES_RANGEES

    def implique(self) -> Sequence[Eleve]:
        return [self.eleve]

    def places_autorisees(self, eleve: Eleve, salle: Salle) -> Optional[Iterable[Position]]:
        if eleve is not self.eleve:
            return None
        min_rang: int = max(0, self._max_y - self.k + 1)
        return [p for p in salle.toutes_les_places() if p.y >= min_rang]

    def est_satisfaite(self, affectation: Dict[Eleve, Position]) -> bool:
        pos: Optional[Position] = affectation.get(self.eleve)
        if pos is None:
            return True
        min_rang: int = max(0, self._max_y - self.k + 1)
        return pos.y >= min_rang

    def texte_humain(self) -> str:
        return f"{self.eleve.affichage_nom()} doit être dans les {self.k} dernières rangées"

    def code_machine(self) -> Dict[str, Any]:
        return {"type": self.type_contrainte().value, "eleve": self.eleve.nom, "k": self.k}

    def regles_asp(self, ctx: ASPContext) -> list[str]:
        s = ctx.id_par_eleve[self.eleve]
        min_rang = max(0, self._max_y - self.k + 1)
        return [f":- assign({s},_,Y,_), Y < {min_rang}."]


class DoitEtreSeulALaTable(Contrainte):
    """Exige que l'élève soit seul à sa table (aucun autre élève sur (x, y))."""

    def __init__(self, eleve: Eleve) -> None:
        self.eleve: Eleve = eleve

    def type_contrainte(self) -> TypeContrainte:
        return TypeContrainte.SEUL_A_TABLE

    def implique(self) -> Sequence[Eleve]:
        return [self.eleve]

    def est_satisfaite(self, affectation: Dict[Eleve, Position]) -> bool:
        pos: Optional[Position] = affectation.get(self.eleve)
        if pos is None:
            return True
        for autre, p in affectation.items():
            if autre is self.eleve:
                continue
            if p is not None and meme_table(pos, p):
                return False
        return True

    def texte_humain(self) -> str:
        return f"{self.eleve.affichage_nom()} doit être seul à sa table"

    def code_machine(self) -> Dict[str, Any]:
        return {"type": self.type_contrainte().value, "eleve": self.eleve.nom}

    def regles_asp(self, ctx: ASPContext) -> list[str]:
        s = ctx.id_par_eleve[self.eleve]
        return [f":- assign({s},X,Y,_), assign(S2,X,Y,_), S2 != {s}."]


class DoitAvoirVoisinVide(Contrainte):
    """Exige qu'au moins un siège de la table soit vide pour cet élève.

    La décision finale dépend de la capacité de la table et du nombre d'occupants.
    Le solveur effectue une validation finale une fois l'affectation complète.
    """

    def __init__(self, eleve: Eleve) -> None:
        self.eleve: Eleve = eleve

    def type_contrainte(self) -> TypeContrainte:
        return TypeContrainte.VOISIN_VIDE

    def implique(self) -> Sequence[Eleve]:
        return [self.eleve]

    def est_satisfaite(self, affectation: Dict[Eleve, Position]) -> bool:
        return True

    def texte_humain(self) -> str:
        return f"{self.eleve.affichage_nom()} doit avoir au moins un siège vide à côté"

    def code_machine(self) -> Dict[str, Any]:
        return {"type": self.type_contrainte().value, "eleve": self.eleve.nom}

    def regles_asp(self, ctx: ASPContext) -> Sequence[str]:
        s = ctx.sid(self.eleve)
        # "au moins un siège vide" <=> nb_occupants < capacité
        return [f":- assign({s},X,Y,_), table(X,Y,C), C <= #count{{S2: assign(S2,X,Y,_)}}."]


class DoitEtreExactementIci(Contrainte):
    """Exige que l'élève soit à une position exacte (x, y, siège)."""

    def __init__(self, eleve: Eleve, ou: Position) -> None:
        self.eleve: Eleve = eleve
        self.ou: Position = ou

    def type_contrainte(self) -> TypeContrainte:
        return TypeContrainte.EXACT_SEAT

    def implique(self) -> Sequence[Eleve]:
        return [self.eleve]

    def places_autorisees(self, eleve: Eleve, salle: Salle) -> Optional[Iterable[Position]]:
        return [self.ou] if eleve is self.eleve else None

    def est_satisfaite(self, affectation: Dict[Eleve, Position]) -> bool:
        pos: Optional[Position] = affectation.get(self.eleve)
        return True if pos is None else (pos == self.ou)

    def texte_humain(self) -> str:
        return (
            f"{self.eleve.affichage_nom()} "
            f"doit être à la position (x={self.ou.x}, y={self.ou.y}, siège={self.ou.siege})"
        )

    def code_machine(self) -> Dict[str, Any]:
        return {
            "type": self.type_contrainte().value,
            "eleve": self.eleve.nom,
            "x": self.ou.x,
            "y": self.ou.y,
            "seat": self.ou.siege,
        }

    def regles_asp(self, ctx: ASPContext) -> list[str]:
        s = ctx.id_par_eleve[self.eleve]
        return [f":- not assign({s},{self.ou.x},{self.ou.y},{self.ou.siege})."]


class DoitNePasAvoirVoisinAdjacent(Contrainte):
    """
    Interdit qu’un autre élève soit assis sur un siège *adjacent* à celui de l’élève,
    sur la même table (|seat_i - seat_j| == 1).
    """

    def __init__(self, eleve: Eleve) -> None:
        self.eleve: Eleve = eleve

    def type_contrainte(self) -> TypeContrainte:
        return TypeContrainte.NO_ADJACENT

    def implique(self) -> Sequence[Eleve]:
        return [self.eleve]

    def est_satisfaite(self, affectation: Dict[Eleve, Position]) -> bool:
        pos: Optional[Position] = affectation.get(self.eleve)
        if pos is None:
            return True
        # On refuse dès qu’on trouve quelqu’un sur la même table ET siège adjacent
        for autre, p in affectation.items():
            if autre is self.eleve or p is None:
                continue
            if p.x == pos.x and p.y == pos.y and abs(p.siege - pos.siege) == 1:
                return False
        return True

    def texte_humain(self) -> str:
        return f"{self.eleve.affichage_nom()} ne doit avoir aucun voisin adjacent"

    def code_machine(self) -> Dict[str, Any]:
        return {"type": self.type_contrainte().value, "eleve": self.eleve.nom}

    def regles_asp(self, ctx: ASPContext) -> Sequence[str]:
        s = ctx.sid(self.eleve)
        # “Il n’existe pas S2 adjacent à S sur la même table”
        # encode via un interdit quand deux sièges adjacents de même (X,Y)
        return [
            # même table X, Y forcé implicitement par assign/assign
            # |S1 - S2| == 1 sur la *même table*
            f":- assign({s},X,Y,S1), assign(S2,X,Y,S2i), |S1-S2i| == 1, S2 != {s}."
        ]

