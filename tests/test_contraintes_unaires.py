from __future__ import annotations

import random

from plandeclasse.modele.salle import Salle
from plandeclasse.modele.position import Position
from plandeclasse.modele.eleve import Eleve
from plandeclasse.contraintes.unaires import (
    DoitEtreDansPremieresRangees,
    DoitEtreDansDernieresRangees,
    DoitEtreSeulALaTable,
    DoitEtreExactementIci,
)
from plandeclasse.solveurs.aleatoire import SolveurAleatoireRetourArriere


def test_front_rows_places_autorisees():
    salle = Salle.depuis_mode_compact(4, [2, 2])
    e = Eleve("DUPONT A", "F")
    c = DoitEtreDansPremieresRangees(e, k=2)
    autor = list(c.places_autorisees(e, salle))
    assert all(p.y < 2 for p in autor)


def test_back_rows_places_autorisees():
    salle = Salle.depuis_mode_compact(4, [2, 2])
    e = Eleve("DUPONT B", "M")
    c = DoitEtreDansDernieresRangees(e, k=2, salle=salle)
    autor = list(c.places_autorisees(e, salle))
    assert all(p.y >= 2 for p in autor)  # max_y=3 -> dernières = y>=2


def test_exact_seat_satisfaction():
    salle = Salle.depuis_mode_compact(2, [2])
    e = Eleve("DUPONT A", "F")
    pos = Position(0, 0, 1)
    c = DoitEtreExactementIci(e, pos)
    assert c.est_satisfaite({}) is True
    assert c.est_satisfaite({e: pos}) is True


def test_solo_table_rule():
    e1 = Eleve("DUPONT A", "F")
    e2 = Eleve("DUPONT B", "M")
    c = DoitEtreSeulALaTable(e1)
    # e1 et e2 sur la même table -> violation
    assert c.est_satisfaite({e1: Position(0, 0, 0), e2: Position(0, 0, 1)}) is False


def test_solver_with_unary_constraints():
    # seed pour reproductibilité
    random.seed(12345)

    salle = Salle.depuis_mode_compact(3, [2, 3, 2])
    e1 = Eleve("DUPONT A", "F")
    e2 = Eleve("DUPONT B", "M")
    e3 = Eleve("DUPONT C", "F")
    cts = [
        DoitEtreDansPremieresRangees(e1, k=1),
        DoitEtreExactementIci(e2, Position(1, 0, 0)),
        DoitEtreSeulALaTable(e3),
    ]
    sol = SolveurAleatoireRetourArriere()
    res = sol.resoudre(salle, [e1, e2, e3], cts, essais_max=80_000)
    assert res.affectation is not None
    # vérifie l'exact seat
    assert res.affectation[e2] == Position(1, 0, 0)
