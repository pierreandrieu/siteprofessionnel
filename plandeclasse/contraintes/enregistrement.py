from __future__ import annotations

from typing import Any, Mapping

from .types import TypeContrainte
from .registre import enregistrer, ContexteFabrique
from .unaires import (
    DoitEtreDansPremieresRangees,
    DoitEtreDansDernieresRangees,
    DoitEtreSeulALaTable,
    DoitAvoirVoisinVide,
    DoitEtreExactementIci, DoitNePasAvoirVoisinAdjacent,
)
from .binaires import (
    DoiventEtreEloignes,
    DoiventEtreSurMemeTable,
    DoiventEtreAdjacents,
)
from .structurelles import TableDoitEtreVide, SiegeDoitEtreVide
from ..modele.position import Position


@enregistrer(TypeContrainte.PREMIERES_RANGEES)
def _fab_premieres_rangees(code: Mapping[str, Any], ctx: ContexteFabrique):
    """
    Construit une contrainte "premières rangées".

    Supporte un champ optionnel `metric`:
      - "grid" (défaut): comparaison sur y logique,
      - "px"           : comparaison visuelle (py), si le solveur a une géométrie.
    """
    nom: str = str(code["eleve"])
    k: int = int(code["k"])
    c = DoitEtreDansPremieresRangees(eleve=ctx.index_eleves_par_nom[nom], k=k)
    metric_raw: str = str(code.get("metric", "grid")).strip().lower()
    if metric_raw in {"grid", "px"}:
        setattr(c, "metric", metric_raw)
    return c


@enregistrer(TypeContrainte.DERNIERES_RANGEES)
def _fab_dernieres_rangees(code: Mapping[str, Any], ctx: ContexteFabrique):
    """
    Construit une contrainte "dernières rangées".

    Supporte `metric` comme ci-dessus ("grid" par défaut, "px" si souhaité).
    """
    nom: str = str(code["eleve"])
    k: int = int(code["k"])
    c = DoitEtreDansDernieresRangees(eleve=ctx.index_eleves_par_nom[nom], k=k, salle=ctx.salle)
    metric_raw: str = str(code.get("metric", "grid")).strip().lower()
    if metric_raw in {"grid", "px"}:
        setattr(c, "metric", metric_raw)
    return c


@enregistrer(TypeContrainte.ELOIGNES)
def _fab_eloignes(code: Mapping[str, Any], ctx: ContexteFabrique):
    """
    Construit une contrainte d’éloignement (Manhattan).

    Champs :
      - d : int (>=1)
      - metric : "grid" (défaut) ou "px"
      - en_pixels : bool (héritage; équivalent à metric="px")
    """
    a_nom: str = str(code["a"])
    b_nom: str = str(code["b"])
    d: int = int(code["d"])
    c = DoiventEtreEloignes(a=ctx.index_eleves_par_nom[a_nom],
                            b=ctx.index_eleves_par_nom[b_nom],
                            d=d)

    # Compatibilité : en_pixels (bool) ou metric="px"
    metric_raw: str = str(code.get("metric", "grid")).strip().lower()
    en_pixels: bool = bool(code.get("en_pixels", False))
    if en_pixels or metric_raw == "px":
        setattr(c, "metric", "px")
        setattr(c, "en_pixels", True)
    return c


@enregistrer(TypeContrainte.SEUL_A_TABLE)
def _fab_seul_table(code: Mapping[str, Any], ctx: ContexteFabrique):
    nom: str = str(code["eleve"])
    return DoitEtreSeulALaTable(eleve=ctx.index_eleves_par_nom[nom])


@enregistrer(TypeContrainte.VOISIN_VIDE)
def _fab_voisin_vide(code: Mapping[str, Any], ctx: ContexteFabrique):
    nom: str = str(code["eleve"])
    return DoitAvoirVoisinVide(eleve=ctx.index_eleves_par_nom[nom])


@enregistrer(TypeContrainte.EXACT_SEAT)
def _fab_exact_seat(code: Mapping[str, Any], ctx: ContexteFabrique):
    nom: str = str(code["eleve"])
    x: int = int(code["x"])
    y: int = int(code["y"])
    seat: int = int(code["seat"])
    return DoitEtreExactementIci(eleve=ctx.index_eleves_par_nom[nom], ou=Position(x=x, y=y, siege=seat))


@enregistrer(TypeContrainte.MEME_TABLE)
def _fab_meme_table(code: Mapping[str, Any], ctx: ContexteFabrique):
    a_nom: str = str(code["a"])
    b_nom: str = str(code["b"])
    return DoiventEtreSurMemeTable(a=ctx.index_eleves_par_nom[a_nom], b=ctx.index_eleves_par_nom[b_nom])


@enregistrer(TypeContrainte.ADJACENTS)
def _fab_adjacents(code: Mapping[str, Any], ctx: ContexteFabrique):
    a_nom: str = str(code["a"])
    b_nom: str = str(code["b"])
    return DoiventEtreAdjacents(a=ctx.index_eleves_par_nom[a_nom], b=ctx.index_eleves_par_nom[b_nom])


@enregistrer(TypeContrainte.TABLE_INTERDITE)
def _fab_table_interdite(code: Mapping[str, Any], ctx: ContexteFabrique):
    x: int = int(code["x"])
    y: int = int(code["y"])
    return TableDoitEtreVide(x=x, y=y)


@enregistrer(TypeContrainte.SIEGE_INTERDIT)
def _fab_siege_interdit(code: Mapping[str, Any], ctx):
    x: int = int(code["x"])
    y: int = int(code["y"])
    seat: int = int(code["seat"])
    return SiegeDoitEtreVide(x=x, y=y, seat=seat)


@enregistrer(TypeContrainte.NO_ADJACENT)
def _fab_no_adjacent(code, ctx):
    nom: str = str(code["eleve"])
    return DoitNePasAvoirVoisinAdjacent(eleve=ctx.index_eleves_par_nom[nom])

