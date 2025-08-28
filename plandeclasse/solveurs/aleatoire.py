from __future__ import annotations

import random
from typing import Dict, List, Optional, Sequence, Set

from .base import Solveur, ResultatResolution
from ..modele.eleve import Eleve
from ..modele.position import Position
from ..modele.salle import Salle
from ..contraintes.base import Contrainte


class SolveurAleatoireRetourArriere(Solveur):
    """Retour arrière (backtracking) avec pruning unaire, contraintes globales et MRV.

    Caractéristiques
    ----------------
    - Réduction de domaine via `places_autorisees` (unaires et structurelles/globales).
    - Heuristique MRV (Minimum Remaining Values) sur l'ordre des élèves.
    - Validation finale pour les contraintes dépendant des capacités.
    """

    def resoudre(
        self,
        salle: Salle,
        eleves: Sequence[Eleve],
        contraintes: Sequence[Contrainte],
        *,
        essais_max: int = 100_000,
        budget_temps_ms: Optional[int] = None,
    ) -> ResultatResolution:
        toutes_les_places: List[Position] = salle.toutes_les_places()
        if len(toutes_les_places) < len(eleves):
            return ResultatResolution(None, essais=0, verifications=0)

        # Contraintes unaires par élève et contraintes globales (sans élève impliqué)
        unaires_par_eleve: Dict[Eleve, List[Contrainte]] = {}
        globales: List[Contrainte] = []
        for c in contraintes:
            impliques = c.implique()
            if len(impliques) == 1:
                unaires_par_eleve.setdefault(impliques[0], []).append(c)
            elif len(impliques) == 0:
                globales.append(c)

        # Domaines initiaux avec intersection des filtrages
        domaines: Dict[Eleve, List[Position]] = {}
        for e in eleves:
            listes: List[List[Position]] = []
            for c in unaires_par_eleve.get(e, []):
                autorise = c.places_autorisees(e, salle)
                if autorise is not None:
                    listes.append(list(autorise))
            for c in globales:
                autorise_g = c.places_autorisees(e, salle)
                if autorise_g is not None:
                    listes.append(list(autorise_g))
            if listes:
                inter: Set[Position] = set(listes[0])
                for L in listes[1:]:
                    inter.intersection_update(L)
                domaine: List[Position] = [p for p in toutes_les_places if p in inter]
            else:
                domaine = list(toutes_les_places)
            random.shuffle(domaine)
            domaines[e] = domaine

        # Ordre des élèves : MRV puis nom pour la stabilité
        ordre: List[Eleve] = sorted(eleves, key=lambda el: (len(domaines[el]), el.nom()))

        essais: int = 0
        verifications: int = 0
        affectation: Dict[Eleve, Position] = {}
        utilises: Set[Position] = set()

        def placement_coherent(eleve: Eleve, pos: Position) -> bool:
            nonlocal verifications
            if pos in utilises:
                return False
            affectation[eleve] = pos
            for contrainte in contraintes:
                impliques_c = contrainte.implique()
                # On vérifie :
                # - les contraintes globales (0 élève) en permanence (all([]) == True)
                # - les autres lorsqu'elles sont entièrement instanciées
                if all(p in affectation for p in impliques_c):
                    verifications += 1
                    if not contrainte.est_satisfaite(affectation):
                        del affectation[eleve]
                        return False
            del affectation[eleve]
            return True

        def retour_arriere(i: int) -> bool:
            nonlocal essais
            if i == len(ordre):
                return self.valider_final(salle, affectation, contraintes)
            eleve: Eleve = ordre[i]
            for pos in domaines[eleve]:
                essais += 1
                if essais > essais_max:
                    return False
                if placement_coherent(eleve, pos):
                    affectation[eleve] = pos
                    utilises.add(pos)
                    if retour_arriere(i + 1):
                        return True
                    utilises.remove(pos)
                    del affectation[eleve]
            return False

        succes: bool = retour_arriere(0)
        return ResultatResolution(affectation.copy() if succes else None, essais=essais, verifications=verifications)
