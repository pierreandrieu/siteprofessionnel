from __future__ import annotations

from plandeclasse.modele.salle import Salle
from plandeclasse.modele.position import Position
from plandeclasse.modele.eleve import Eleve
from plandeclasse.contraintes.binaires import (
    DoiventEtreEloignes,
    DoiventEtreSurMemeTable,
    DoiventEtreAdjacents,
)


def test_same_table():
    e1, e2 = Eleve("DUPONT A", "F"), Eleve("DUPONT B", "M")
    c = DoiventEtreSurMemeTable(e1, e2)
    assert c.est_satisfaite({}) is True  # partiel
    assert c.est_satisfaite({e1: Position(0, 0, 0), e2: Position(0, 0, 1)}) is True
    assert c.est_satisfaite({e1: Position(0, 0, 0), e2: Position(1, 0, 0)}) is False


def test_adjacent():
    e1, e2 = Eleve("DUPONT A", "F"), Eleve("DUPONT B", "M")
    c = DoiventEtreAdjacents(e1, e2)
    assert c.est_satisfaite({e1: Position(0, 0, 0), e2: Position(0, 0, 1)}) is True
    assert c.est_satisfaite({e1: Position(0, 0, 0), e2: Position(0, 0, 2)}) is False


def test_far_apart_manhattan():
    e1, e2 = Eleve("DUPONT A", "F"), Eleve("DUPONT B", "M")
    c = DoiventEtreEloignes(e1, e2, d=3)
    # distance |dx|+|dy|
    assert c.est_satisfaite({e1: Position(0, 0, 0), e2: Position(2, 1, 0)}) is True  # 3
    assert c.est_satisfaite({e1: Position(0, 0, 0), e2: Position(1, 1, 0)}) is False  # 2
