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
    nom: str = str(code["eleve"])  # nom stable
    k: int = int(code["k"])       # nombre de rangées
    return DoitEtreDansPremieresRangees(eleve=ctx.index_eleves_par_nom[nom], k=k)


@enregistrer(TypeContrainte.DERNIERES_RANGEES)
def _fab_dernieres_rangees(code: Mapping[str, Any], ctx: ContexteFabrique):
    nom: str = str(code["eleve"])
    k: int = int(code["k"])
    return DoitEtreDansDernieresRangees(eleve=ctx.index_eleves_par_nom[nom], k=k, salle=ctx.salle)


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


@enregistrer(TypeContrainte.ELOIGNES)
def _fab_eloignes(code: Mapping[str, Any], ctx: ContexteFabrique):
    a_nom: str = str(code["a"])  # élève A
    b_nom: str = str(code["b"])  # élève B
    d: int = int(code["d"])      # distance min (Manhattan)
    return DoiventEtreEloignes(a=ctx.index_eleves_par_nom[a_nom], b=ctx.index_eleves_par_nom[b_nom], d=d)


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

