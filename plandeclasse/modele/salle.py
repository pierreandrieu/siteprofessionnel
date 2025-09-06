from __future__ import annotations

from typing import List

from .position import Position
from .table import Table


class Salle:
    """
    Modélise une salle à partir d'un schéma de rangées.

    Convention additionnelle :
    - Une valeur **négative** dans le schéma (ex. -2) représente un **trou**
      de largeur équivalente à 2 emplacements de table (côté rendu UI).
    - Le solveur ignore ces trous (aucune Table/Position créée), mais les
      indices (x, y) restent alignés avec le schéma pour garder la cohérence
      des clés côté frontend.

    Exemple :
        schema = [
            [2, 3, -2, 2],   # 2 places, 3 places, trou de 2, 2 places
            [2, 2],
        ]
    """

    def __init__(self, schema: List[List[int]]) -> None:
        """
        Construit toutes les tables à partir du schéma.

        Args:
            schema: liste de rangées ; chaque rangée est une liste des capacités
                    des tables, de gauche à droite. Les valeurs <= 0 sont
                    interprétées comme des **trous** (pas de table créée).
        """
        # Copie défensive
        self._schema: List[List[int]] = [list(ligne) for ligne in schema]
        self._tables: List[Table] = []

        # Parcours rangée par rangée (y), puis colonne par colonne (x)
        for y, ligne in enumerate(self._schema):
            for x, capacite in enumerate(ligne):
                # Nouv.: on **ignore** les capacités <= 0 (trous visuels côté UI)
                if capacite > 0:
                    self._tables.append(Table(x=x, y=y, capacite=capacite))

    @classmethod
    def depuis_mode_compact(cls, nb_lignes: int, capacites_par_table: List[int]) -> "Salle":
        """
        Construit une salle avec `nb_lignes` identiques, chacune ayant
        les capacités listées dans `capacites_par_table`.

        Remarque : si `capacites_par_table` contient des valeurs négatives,
        elles seront considérées comme des trous **dans chaque rangée**.
        """
        schema: List[List[int]] = [list(capacites_par_table) for _ in range(nb_lignes)]
        return cls(schema)

    # --- Accès de base -----------------------------------------------------

    def tables(self) -> List[Table]:
        """Retourne l'ensemble des tables de la salle."""
        return self._tables

    def schema(self) -> List[List[int]]:
        """Retourne une copie du schéma brut (liste de listes)."""
        return [list(ligne) for ligne in self._schema]

    def capacite_par_table(self) -> dict[tuple[int, int], int]:
        """
        Retourne un dictionnaire {(x, y): capacite} pour chaque table de la salle.
        Utile au solveur pour vérifier des contraintes dépendantes de la capacité.
        """
        caps: dict[tuple[int, int], int] = {}
        for t in self._tables:
            caps[(t.x, t.y)] = t.capacite()
        return caps

    def positions_par_table(self) -> dict[tuple[int, int], list[Position]]:
        """
        Retourne un dictionnaire {(x, y): [Position(...), ...]} listant toutes
        les positions-sièges par table. Pratique pour des vérifications locales.
        """
        m: dict[tuple[int, int], list[Position]] = {}
        for t in self._tables:
            key = (t.x, t.y)
            lst = m.setdefault(key, [])
            for s in range(t.capacite()):
                lst.append(Position(x=t.x, y=t.y, siege=s))
        return m

    # --- Utilitaires pour le solveur / tests -------------------------------

    def toutes_les_places(self) -> List[Position]:
        """
        Énumère **toutes** les places (positions de sièges) de la salle.

        Retour:
            Liste de Position, une par siège, pour chaque table. L'ordre est
            (par rangée de y croissant) puis (par x croissant) puis (siège 0..cap-1).
        """
        toutes: List[Position] = []
        for table in self._tables:
            x, y = table.x, table.y
            cap: int = table.capacite()
            # Ajoute une Position pour chaque siège de la table.
            for s in range(cap):
                toutes.append(Position(x=x, y=y, siege=s))
        return toutes

    def max_y(self) -> int:
        """Renvoie l'indice de rangée maximal existant (ou -1 si aucune table)."""
        return max((t.y for t in self._tables), default=-1)

    def max_x(self) -> int:
        """Renvoie l'indice de colonne maximal existant (ou -1 si aucune table)."""
        return max((t.x for t in self._tables), default=-1)

    def __str__(self) -> str:
        """
        Représentation texte simple : rangée par rangée.
        Utile pour debug.
        """
        lignes: dict[int, List[Table]] = {}
        for t in self._tables:
            lignes.setdefault(t.y, []).append(t)
        parts: List[str] = []
        for y in sorted(lignes):
            ligne = " | ".join(f"({t.x},{t.y})x{t.capacite()}" for t in sorted(lignes[y], key=lambda t_2: t_2.x))
            parts.append(ligne)
        return "\n".join(parts)
