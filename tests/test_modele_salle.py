from __future__ import annotations

from plandeclasse.modele.position import Position
from plandeclasse.modele.table import Table
from plandeclasse.modele.salle import Salle


def test_salle_places_count():
    # 2 tables (2,3) sur y=0 ; 2 tables (2,2) sur y=1 -> 2+3+2+2 = 9
    salle = Salle([[2, 3], [2, 2]])
    places = salle.toutes_les_places()
    assert len(places) == 9


def test_position_immutable_hashable():
    a = Position(0, 0, 0)
    b = Position(0, 0, 0)
    s = {a}
    assert b in s  # même valeur -> hash/eq
