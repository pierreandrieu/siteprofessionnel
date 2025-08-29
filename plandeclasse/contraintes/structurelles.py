from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Sequence

from .base import Contrainte, ASPContext
from .types import TypeContrainte
from ..modele.eleve import Eleve
from ..modele.position import Position
from ..modele.salle import Salle


class TableDoitEtreVide(Contrainte):
    """Interdit toute occupation de la table située en (x, y)."""

    def __init__(self, x: int, y: int) -> None:
        self.x: int = x
        self.y: int = y

    def type_contrainte(self) -> TypeContrainte:
        return TypeContrainte.TABLE_INTERDITE

    def implique(self) -> Sequence[Eleve]:
        return []  # contrainte globale

    def places_autorisees(self, eleve: Eleve, salle: Salle) -> Optional[Iterable[Position]]:
        # Exclut les sièges de la table (x, y) pour tous les élèves.
        return [p for p in salle.toutes_les_places() if not (p.x == self.x and p.y == self.y)]

    def est_satisfaite(self, affectation: Dict[Eleve, Position]) -> bool:
        p: Position
        for p in affectation.values():
            if p is not None and p.x == self.x and p.y == self.y:
                return False
        return True

    def texte_humain(self) -> str:
        return f"La table en (x={self.x}, y={self.y}) doit rester vide"

    def code_machine(self) -> Dict[str, Any]:
        return {"type": self.type_contrainte().value, "x": self.x, "y": self.y}

    def regles_asp(self, ctx: ASPContext) -> Sequence[str]:
        return [f"ban_table({self.x},{self.y})."]


class SiegeDoitEtreVide(Contrainte):
    """Interdit l'occupation du siège (x, y, seat) pour tout élève."""

    def __init__(self, x: int, y: int, seat: int) -> None:
        self.x: int = x
        self.y: int = y
        self.seat: int = seat

    def type_contrainte(self) -> TypeContrainte:
        return TypeContrainte.SIEGE_INTERDIT

    def implique(self) -> Sequence[Eleve]:
        return []

    def places_autorisees(self, eleve: Eleve, salle: Salle) -> Optional[Iterable[Position]]:
        # Exclut exactement ce siège pour tous
        return [p for p in salle.toutes_les_places() if not (p.x == self.x and p.y == self.y and p.siege == self.seat)]

    def est_satisfaite(self, affectation: Dict[Eleve, Position]) -> bool:
        for p in affectation.values():
            if p is not None and p.x == self.x and p.y == self.y and p.siege == self.seat:
                return False
        return True

    def texte_humain(self) -> str:
        return f"Le siège (x={self.x}, y={self.y}, s={self.seat}) doit rester vide"

    def code_machine(self) -> Dict[str, Any]:
        return {"type": self.type_contrainte().value, "x": self.x, "y": self.y, "seat": self.seat}

    def regles_asp(self, ctx: ASPContext) -> Sequence[str]:
        return [f"ban_seat({self.x},{self.y},{self.seat})."]

