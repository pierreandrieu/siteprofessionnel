# tests/test_solveur_clingo_simple_contraintes.py
from __future__ import annotations

import pytest

# Skip propre si clingo n'est pas dispo
pytest.importorskip("clingo", reason="clingo n'est pas installé")

from plandeclasse.solveurs.asp import SolveurClingo
from plandeclasse.modele.salle import Salle
from plandeclasse.modele.eleve import Eleve
from plandeclasse.modele.position import Position

from plandeclasse.contraintes.unaires import (
    DoitEtreDansPremieresRangees,
    DoitEtreSeulALaTable,
    DoitEtreExactementIci,
)
from plandeclasse.contraintes.binaires import (
    DoiventEtreEloignes,
    DoiventEtreSurMemeTable,
    DoiventEtreAdjacents,
)
from plandeclasse.contraintes.structurelles import TableDoitEtreVide


def test_solveur_clingo_respecte_les_contraintes():
    # Salle compacte et généreuse en sièges : 3 rangs, 2 tables par rang, capacités [2, 3]
    salle = Salle.depuis_mode_compact(nb_lignes=3, capacites_par_table=[2, 3])

    # Une petite classe
    eleves = [Eleve(nom=f"E{i}", genre=("F" if i % 2 == 0 else "M")) for i in range(10)]

    # Un petit mix de contraintes variées
    contraintes = [
        DoitEtreDansPremieresRangees(eleve=eleves[0], k=2),
        DoitEtreSeulALaTable(eleve=eleves[1]),
        DoiventEtreEloignes(a=eleves[2], b=eleves[3], d=3),
        DoiventEtreSurMemeTable(a=eleves[4], b=eleves[5]),
        DoiventEtreAdjacents(a=eleves[6], b=eleves[7]),
        TableDoitEtreVide(x=1, y=1),
        DoitEtreExactementIci(eleve=eleves[8], ou=Position(x=0, y=0, siege=0)),
    ]

    solveur = SolveurClingo()
    res = solveur.resoudre(salle=salle, eleves=eleves, contraintes=contraintes)

    # Le solveur doit trouver une affectation
    assert res.affectation is not None, "Pas d'affectation trouvée"

    # Chaque contrainte s’auto-valide via est_satisfaite()
    for c in contraintes:
        assert c.est_satisfaite(res.affectation), f"Contrainte non satisfaite: {c}"

    # Et on couvre les vérifications finales (capacités, voisins vides, etc.)
    assert solveur.valider_final(salle, res.affectation, contraintes), "Vérifications finales échouées"
