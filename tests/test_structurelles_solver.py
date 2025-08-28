from __future__ import annotations

import random

from plandeclasse.modele.salle import Salle
from plandeclasse.modele.eleve import Eleve
from plandeclasse.contraintes.structurelles import TableDoitEtreVide
from plandeclasse.contraintes.unaires import DoitEtreDansPremieresRangees
from plandeclasse.solveurs.aleatoire import SolveurAleatoireRetourArriere


def test_forbid_table_pruning_and_solver():
    # seed pour reproductibilité
    random.seed(9876)

    salle = Salle.depuis_mode_compact(3, [2, 2, 2])
    eleves = [Eleve(f"DUPONT {i}", "F") for i in range(5)]
    contraintes = [
        TableDoitEtreVide(x=1, y=1),  # interdit la table du milieu sur la rangée du milieu
        DoitEtreDansPremieresRangees(eleves[0], k=2),
    ]
    sol = SolveurAleatoireRetourArriere()
    res = sol.resoudre(salle, eleves, contraintes, essais_max=80_000)
    assert res.affectation is not None
    # vérifie que personne n'est sur la table (1,1)
    assert all(not (p.x == 1 and p.y == 1) for p in res.affectation.values())
