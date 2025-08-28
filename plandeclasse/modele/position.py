from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Position:
    """Représente une *place précise* dans la salle.
    Attributs
    ---------
    x : int
    Indice de colonne de la table, de gauche à droite (0-indexé).
    y : int
    Indice de rangée, du tableau vers le fond (0-indexé, 0 = premier rang).
    siege : int
    Indice du siège sur la table (0-indexé).


    Cette classe est immuable pour garantir la stabilité des clés
    dans les dictionnaires/ensembles pendant la recherche.
    """

    x: int
    y: int
    siege: int
