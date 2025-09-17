from __future__ import annotations

import json
import random
from typing import List

from .modele.eleve import Eleve
from .modele.salle import Salle
from .modele.position import Position
from .solveurs.cpsat import SolveurCPSAT
from .contraintes.unaires import DoitEtreDansPremieresRangees, DoitEtreSeulALaTable, DoitEtreExactementIci
from .contraintes.binaires import DoiventEtreEloignes, DoiventEtreSurMemeTable, DoiventEtreAdjacents
from .contraintes.structurelles import TableDoitEtreVide

from .contraintes.enregistrement import *
from .contraintes.registre import ContexteFabrique, contrainte_depuis_code


def construire_exemple() -> None:
    """
    construit une salle, une liste d'élèves, un jeu de contraintes et lance le solveur.

    affiche l'affectation si une solution est trouvée, et un export JSON des contraintes.
    """
    # pour la reproductibilité de la démonstration
    random.seed(42)

    # salle : 4 rangs, trois tables par rang (capacités 2, 3, 2)
    salle: Salle = Salle.depuis_mode_compact(nb_lignes=4, capacites_par_table=[2, 3, 2])

    # élèves : 20 élèves nommés, genres alternés pour l'exemple
    eleves: List[Eleve] = [
        Eleve(nom=f"DUPONT {chr(65 + i)}", genre="F" if i % 2 == 0 else "M")
        for i in range(20)
    ]

    # contraintes variées
    contraintes = [
        DoitEtreDansPremieresRangees(eleve=eleves[0], k=2),
        DoitEtreSeulALaTable(eleve=eleves[1]),
        DoiventEtreEloignes(a=eleves[2], b=eleves[3], d=3),
        DoiventEtreSurMemeTable(a=eleves[4], b=eleves[5]),
        DoiventEtreAdjacents(a=eleves[6], b=eleves[7]),
        TableDoitEtreVide(x=1, y=2),
        DoitEtreExactementIci(eleve=eleves[8], ou=Position(x=0, y=0, siege=0)),
    ]

    solveur = SolveurCPSAT(prefer_alone=True, prefer_mixage=True, seed=42)
    res = solveur.resoudre(salle=salle, eleves=eleves, contraintes=contraintes, essais_max=200_000)

    if res.affectation is None:
        print("aucune solution trouvée.")
        return

    # affichage de l'affectation
    print("=== affectation trouvée ===")
    for e in sorted(eleves):
        pos = res.affectation.get(e)
        if pos is None:
            print(f" - {e.affichage_nom():20s} : non placé")
        else:
            print(f" - {e.affichage_nom():20s} -> table(x={pos.x}, y={pos.y}), siège {pos.siege}")

    # export JSON « code_machine » + démonstration de rechargement via la fabrique
    codes = [c.code_machine() for c in contraintes]
    print("\n=== export JSON des contraintes ===")
    print(json.dumps(codes, ensure_ascii=False, indent=2))

    # reconstruction
    ctx = ContexteFabrique(salle=salle, index_eleves_par_nom={e.nom: e for e in eleves})
    reconstruites = [contrainte_depuis_code(code, ctx) for code in codes]
    assert all(c1.code_machine() == c2.code_machine() for c1, c2 in zip(contraintes, reconstruites))
    print("\n(reconstruction via fabrique : OK)")


def main() -> None:
    """point d'entrée du module CLI."""
    construire_exemple()


def run_exemple() -> None:
    # alias rétro-compatible pour __main__.py
    return construire_exemple()


if __name__ == "__main__":
    main()
