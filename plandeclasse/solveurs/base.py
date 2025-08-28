from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Optional, Sequence

from ..modele.eleve import Eleve
from ..modele.position import Position
from ..modele.salle import Salle
from ..contraintes.base import Contrainte


class ResultatResolution:
    """Résultat d'une tentative de résolution.

    Attributs
    ---------
    affectation : Optional[Dict[Eleve, Position]]
        Dictionnaire des affectations trouvées (ou `None` si échec).
    essais : int
        Nombre de placements testés.
    verifications : int
        Nombre de validations de contraintes effectuées.
    """

    def __init__(self, affectation: Optional[Dict[Eleve, Position]], essais: int, verifications: int) -> None:
        self.affectation: Optional[Dict[Eleve, Position]] = affectation
        self.essais: int = essais
        self.verifications: int = verifications


class Solveur(ABC):
    """Interface abstraite des solveurs (ASP, backtracking, etc.)."""

    @abstractmethod
    def resoudre(
        self,
        salle: Salle,
        eleves: Sequence[Eleve],
        contraintes: Sequence[Contrainte],
        *,
        essais_max: int = 10_000,
        budget_temps_ms: Optional[int] = None,
    ) -> ResultatResolution:
        """Construit une affectation satisfaisant toutes les contraintes, si possible."""
        raise NotImplementedError

    def valider_final(self, salle: Salle, affectation: Dict[Eleve, Position], contraintes: Sequence[Contrainte]) -> bool:
        """Vérifications finales dépendant de la capacité des tables.

        Exemple : `DoitAvoirVoisinVide` nécessite de garantir au moins un siège
        libre sur la table de l'élève concerné.
        """
        capacites: dict[tuple[int, int], int] = salle.capacite_par_table()

        occupation: dict[tuple[int, int], int] = {}
        pos: Position
        for pos in affectation.values():
            cle: tuple[int, int] = (pos.x, pos.y)
            occupation[cle] = occupation.get(cle, 0) + 1

        from ..contraintes.unaires import DoitAvoirVoisinVide

        for contrainte in contraintes:
            if isinstance(contrainte, DoitAvoirVoisinVide):
                pos_eleve: Optional[Position] = affectation.get(contrainte.eleve)
                if pos_eleve is None:
                    return False
                cle_t: tuple[int, int] = (pos_eleve.x, pos_eleve.y)
                occ: int = occupation.get(cle_t, 0)
                cap: int = capacites.get(cle_t, 0)
                if occ >= cap:
                    return False
        return True
