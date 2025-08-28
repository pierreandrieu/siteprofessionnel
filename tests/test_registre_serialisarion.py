from __future__ import annotations

import json

from plandeclasse.modele.salle import Salle
from plandeclasse.modele.eleve import Eleve
from plandeclasse.modele.position import Position
from plandeclasse.contraintes.unaires import DoitEtreExactementIci, DoitEtreSeulALaTable
from plandeclasse.contraintes.structurelles import TableDoitEtreVide
# important : enregistre toutes les fabriques dans le registre
from plandeclasse.contraintes.enregistrement import *  # noqa: F403,F401
from plandeclasse.contraintes.registre import ContexteFabrique, contrainte_depuis_code


def test_serialisation_roundtrip():
    salle = Salle.depuis_mode_compact(2, [2, 2])
    eleves = [Eleve("DUPONT A", "F"), Eleve("DUPONT B", "M")]
    contraintes = [
        DoitEtreExactementIci(eleves[0], Position(0, 0, 0)),
        DoitEtreSeulALaTable(eleves[1]),
        TableDoitEtreVide(1, 1),
    ]

    # export JSON
    codes = [c.code_machine() for c in contraintes]
    data = json.dumps(codes, ensure_ascii=False)

    # reconstruction via registre/fabriques
    ctx = ContexteFabrique(salle=salle, index_eleves_par_nom={e.nom(): e for e in eleves})
    back = [contrainte_depuis_code(c, ctx) for c in json.loads(data)]

    assert [c.code_machine() for c in back] == codes
