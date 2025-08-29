from __future__ import annotations

from typing import Iterable, List

from .position import Position


class Table:
    """Représente une table à une position (x, y) avec un certain nombre de sièges.


    Paramètres
    ----------
    x : int
    Colonne (0 à gauche).
    y : int
    Rangée (0 au premier rang, côté tableau).
    capacite : int
    Nombre de sièges (>= 1).
    """

    def __init__(self, x: int, y: int, capacite: int) -> None:
        assert capacite > 0, "La capacité d'une table doit être > 0"

        self._x: int = x
        self._y: int = y
        self._capacite: int = capacite
        self._valides: List[bool] = [True for _ in range(capacite)]

    @property
    def x(self) -> int:
        """
        colonne (abscisse) de la table.
        expose l'attribut interne _x en lecture seule.
        """
        return self._x

    @property
    def y(self) -> int:
        """
        rangée (ordonnée) de la table.
        expose l'attribut interne _y en lecture seule.
        """
        return self._y

    def position_xy(self) -> tuple[int, int]:
        """Retourne la paire (x, y) de la table."""
        return self._x, self._y

    def capacite(self) -> int:
        """Retourne la capacité (nombre de sièges)."""
        return self._capacite

    def siege_valide(self, indice: int) -> bool:
        """Indique si le siège `indice` est utilisable."""
        return 0 <= indice < self._capacite and self._valides[indice]

    def invalider_siege(self, indice: int) -> None:
        """Rend le siège `indice` indisponible."""
        if 0 <= indice < self._capacite:
            self._valides[indice] = False

    def revalider_siege(self, indice: int) -> None:
        """Rend le siège `indice` à nouveau disponible."""
        if 0 <= indice < self._capacite:
            self._valides[indice] = True

    def sieges(self) -> Iterable[Position]:
        """Itère sur les positions des sièges valides de cette table."""
        indice: int
        for indice in range(self._capacite):
            if self._valides[indice]:
                yield Position(self._x, self._y, indice)

    def __str__(self) -> str:
        return f"Table({self._x},{self._y})x{self._capacite}"
