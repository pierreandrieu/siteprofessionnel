from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Sequence

from ..modele.eleve import Eleve
from ..modele.position import Position
from ..modele.salle import Salle
from .types import TypeContrainte


@dataclass(frozen=True)
class ASPContext:
    id_par_eleve: dict[Eleve, int]

    def sid(self, e: Eleve) -> int:
        return self.id_par_eleve[e]


class Contrainte(ABC):
    """Classe de base pour les contraintes (unaires, binaires, structurelles).

    Méthodes à implémenter
    ----------------------
    - `type_contrainte()` : retourne un membre de `TypeContrainte`.
    - `implique()` : renvoie les élèves concernés (taille 0, 1 ou 2).
    - `places_autorisees(eleve, salle)` : optionnel, restreint le domaine d'un élève.
    - `est_satisfaite(affectation)` : valide l'affectation partielle/complète.
    - `texte_humain()` : texte lisible pour l'interface.
    - `code_machine()` : représentation stable et sérialisable (dict JSON-friendly).
    """

    dure: bool = True  # uniquement des contraintes dures pour le moment

    @abstractmethod
    def type_contrainte(self) -> TypeContrainte:
        """Retourne le type logique de la contrainte."""
        raise NotImplementedError

    @abstractmethod
    def implique(self) -> Sequence[Eleve]:
        """Retourne la liste des élèves impliqués (0, 1 ou 2)."""
        raise NotImplementedError

    def places_autorisees(self, eleve: Eleve, salle: Salle) -> Optional[Iterable[Position]]:
        """Retourne les places autorisées pour `eleve`, ou `None` si aucun filtrage.

        Une contrainte *globale* (sans élève impliqué) peut fournir ici un filtrage
        applicable à tous les élèves ; le solveur l'appliquera aux domaines de chacun.
        """
        return None

    @abstractmethod
    def est_satisfaite(self, affectation: Dict[Eleve, Position]) -> bool:
        """Indique si la contrainte est satisfaite sous l'affectation courante."""
        raise NotImplementedError

    @abstractmethod
    def texte_humain(self) -> str:
        """Texte concis, lisible par un humain."""
        raise NotImplementedError

    @abstractmethod
    def code_machine(self) -> Dict[str, Any]:
        """Représentation sérialisable, stable et exploitable par des outils."""
        raise NotImplementedError

    def regles_asp(self, ctx: "ASPContext") -> Sequence[str]:
        """
        Retourne des règles/contraintes ASP (strings) pour cette contrainte.
        Par défaut, rien (contrainte non encodée côté ASP).
        """
        return []


def distance_manhattan(a: Position, b: Position) -> int:
    """Calcule la distance de Manhattan entre deux positions."""
    dx: int = abs(a.x - b.x)
    dy: int = abs(a.y - b.y)
    return dx + dy


def meme_table(a: Position, b: Position) -> bool:
    """Retourne `True` si `a` et `b` appartiennent à la même table (mêmes x et y)."""
    return a.x == b.x and a.y == b.y
