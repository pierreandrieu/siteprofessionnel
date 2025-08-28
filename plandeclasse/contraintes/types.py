from __future__ import annotations

from enum import Enum


class TypeContrainte(str, Enum):
    """Enum centralisant les types logiques de contraintes.

    Hérite de `str` pour une sérialisation JSON directe (valeur = nom stable).
    """

    # Unaires (élève)
    PREMIERES_RANGEES = "front_rows"
    DERNIERES_RANGEES = "back_rows"
    SEUL_A_TABLE = "solo_table"
    VOISIN_VIDE = "empty_neighbor"
    EXACT_SEAT = "exact_seat"

    # Binaires (paire d'élèves)
    ELOIGNES = "far_apart"
    MEME_TABLE = "same_table"
    ADJACENTS = "adjacent"

    # Structurelles (salle/table)
    TABLE_INTERDITE = "forbid_table"
