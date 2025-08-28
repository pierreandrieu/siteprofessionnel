from __future__ import annotations

from typing import Optional

from .position import Position


class Eleve:
    """Modélise un élève plaçable dans un plan de classe.


    Paramètres du constructeur
    --------------------------
    nom : str
    Nom complet tel que saisi (ex. « DUPONT Alice »).
    genre : str
    Genre (libre selon le contexte, ex. « F », « M »).


    Détails d'implémentation
    ------------------------
    - Le nom est découpé en *nom de famille* (préfixe en MAJUSCULES) et *prénom*.
    - `position` vaut `None` tant que l'élève n'est pas placé.
    - `fixe` indique un placement imposé manuellement.
    """

    def __init__(self, nom: str, genre: str) -> None:
        nom_epure: str = nom.strip()
        genre_epure: str = genre.strip()

        self._nom: str = nom_epure
        self._genre: str = genre_epure
        self._position: Optional[Position] = None
        self._fixe: bool = False

        mots: list[str] = self._nom.split()
        i: int = 0
        while i < len(mots) and mots[i].isupper():
            i += 1
        self._nom_famille: str = " ".join(mots[:i])
        self._prenom: str = " ".join(mots[i:])
        self._affichage_nom: str = nom_epure

    def nom(self) -> str:
        """Retourne le nom complet saisi."""
        return self._nom

    def nom_famille(self) -> str:
        """Retourne la partie détectée comme nom de famille."""
        return self._nom_famille

    def prenom(self) -> str:
        """Retourne la partie détectée comme prénom."""
        return self._prenom

    def affichage_nom(self) -> str:
        """Retourne la chaîne à afficher pour cet élève."""
        return self._affichage_nom

    def definir_affichage_nom(self, nouveau: str) -> None:
        """Modifie la chaîne d'affichage pour cet élève."""
        self._affichage_nom = nouveau

    def genre(self) -> str:
        """Retourne le genre de l'élève."""
        return self._genre

    def position(self) -> Optional[Position]:
        """Retourne la position actuelle ou `None` si non placé."""
        return self._position

    def definir_position(self, position: Optional[Position]) -> None:
        """Affecte une position (ou `None` pour libérer)."""
        self._position = position

    def est_fixe(self) -> bool:
        """Indique si l'élève est fixé manuellement."""
        return self._fixe

    def fixer(self) -> None:
        """Marque l'élève comme fixé manuellement."""
        self._fixe = True

    def liberer(self) -> None:
        """Libère l'élève de la contrainte de fixation."""
        self._fixe = False

    # --- Protocole de comparaison / hachage ---
    def __str__(self) -> str:  # pragma: no cover - représentation
        return f"{self._nom} ({self._genre})"

    def __repr__(self) -> str:  # pragma: no cover - représentation
        return str(self)

    def __hash__(self) -> int:
        # Hachage sur le nom complet : supposé unique dans un plan donné
        return hash(self._nom)

    def __eq__(self, autre: object) -> bool:
        return isinstance(autre, Eleve) and self._nom == autre._nom

    def __lt__(self, autre: "Eleve") -> bool:
        # Tri : nom de famille puis prénom
        if self.nom_famille() != autre.nom_famille():
            return self.nom_famille() < autre.nom_famille()
        return self.prenom() < autre.prenom()
