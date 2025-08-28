from __future__ import annotations

from typing import Any, Callable, Dict, Mapping, Optional

from .types import TypeContrainte
from .base import Contrainte
from ..modele.eleve import Eleve
from ..modele.salle import Salle

FabriqueContrainte = Callable[[Mapping[str, Any], "ContexteFabrique"], Contrainte]


class ContexteFabrique:
    """Contexte nécessaire pour reconstruire une contrainte à partir d'un dict.

    Attributs
    ---------
    salle : Salle
        Salle visée par la reconstruction.
    index_eleves_par_nom : Mapping[str, Eleve]
        Index permettant de retrouver un `Eleve` à partir d'un nom stable.
    """

    def __init__(self, salle: Salle, index_eleves_par_nom: Mapping[str, Eleve]) -> None:
        self.salle: Salle = salle
        self.index_eleves_par_nom: Mapping[str, Eleve] = index_eleves_par_nom


_REGISTRE: Dict[TypeContrainte, FabriqueContrainte] = {}


def enregistrer(type_c: TypeContrainte):
    """Décorateur enregistrant une fabrique pour un `TypeContrainte`."""

    def deco(fabrique: FabriqueContrainte) -> FabriqueContrainte:
        _REGISTRE[type_c] = fabrique
        return fabrique

    return deco


def fabrique_de(type_c: TypeContrainte) -> Optional[FabriqueContrainte]:
    """Retourne la fabrique enregistrée pour `type_c`, ou `None` si absente."""
    return _REGISTRE.get(type_c)


def contrainte_depuis_code(code: Mapping[str, Any], contexte: ContexteFabrique) -> Contrainte:
    """Reconstitue une contrainte à partir d'un dictionnaire « code_machine ».

    Lève `ValueError` si le type est inconnu, `KeyError` si aucune fabrique
    n'est enregistrée pour ce type.
    """
    type_valeur: str = str(code.get("type", ""))
    try:
        type_c: TypeContrainte = TypeContrainte(type_valeur)
    except ValueError as exc:
        raise ValueError(f"Type de contrainte inconnu: {type_valeur!r}") from exc

    fab: Optional[FabriqueContrainte] = _REGISTRE.get(type_c)
    if fab is None:
        raise KeyError(f"Aucune fabrique enregistrée pour le type {type_c}")
    return fab(code, contexte)
