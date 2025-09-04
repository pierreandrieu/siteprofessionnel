#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Liste le contenu d'un dossier (non récursif) en affichant :
- pour chaque sous-dossier : son nom suivi d'un slash (ex. "sousdossier/")
- pour chaque fichier : le nom du fichier puis son contenu

Usage :
    python lister_contenu.py chemin/relatif/vers/dossier
"""

import sys
from pathlib import Path


def est_texte(path: Path, nb_octets_test: int = 1024) -> bool:
    """Heuristique simple pour distinguer texte/binaire (sans lecture complète)."""
    try:
        extrait = path.read_bytes()[:nb_octets_test]
    except Exception:
        return False
    # Si l'extrait contient des NUL bytes, on suppose binaire
    if b"\x00" in extrait:
        return False
    # On tente un décodage UTF-8 permissif
    try:
        extrait.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def lire_fichier_texte(path: Path) -> str:
    """Lit un fichier texte avec une stratégie tolérante d'encodage."""
    # On tente d'abord UTF-8 strict, puis UTF-8 permissif, puis latin-1
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return path.read_text(encoding="latin-1", errors="replace")


def lister_dossier_non_recursif(chemin_rel: str) -> int:
    """Affiche le contenu immédiat du dossier indiqué par un chemin relatif.
    Retourne 0 si tout s'est bien passé, 1 sinon.
    """
    # Vérifications de base
    chemin = Path(chemin_rel)

    # On impose un chemin relatif (tel que demandé)
    if chemin.is_absolute():
        print("Erreur : merci de fournir un chemin RELATIF vers un dossier.", file=sys.stderr)
        return 1

    # Normalise par rapport au répertoire courant
    chemin = (Path.cwd() / chemin).resolve()

    if not chemin.exists():
        print(f"Erreur : le chemin n'existe pas : {chemin}", file=sys.stderr)
        return 1
    if not chemin.is_dir():
        print(f"Erreur : ce chemin n'est pas un dossier : {chemin}", file=sys.stderr)
        return 1

    # Récupération des entrées (non récursif) et tri alphabétique
    try:
        entrees = sorted(chemin.iterdir(), key=lambda p: p.name.lower())
    except PermissionError:
        print(f"Erreur : permission refusée pour lister {chemin}", file=sys.stderr)
        return 1

    # Affichage conforme à l'exemple
    for entree in entrees:
        nom = entree.name

        if entree.is_dir():
            print(f"{nom}/\n")  # Ligne avec le nom et un slash, puis une ligne vide
            continue

        if entree.is_file():
            print(nom)  # Nom du fichier
            print()  # Ligne vide

            # Si c'est du texte, on l'affiche ; sinon on signale un fichier binaire
            try:
                if est_texte(entree):
                    contenu = lire_fichier_texte(entree)
                    print(contenu.rstrip())  # évite une ligne vide supplémentaire en fin
                else:
                    taille = entree.stat().st_size
                    print(f"[fichier binaire de {taille} octets — contenu non affiché]")
            except Exception as e:
                print(f"[impossible de lire le fichier : {e}]")

            print()  # Ligne vide entre les fichiers

        else:
            # Autres types (lien symbolique, socket, etc.)
            print(f"{nom} [type non géré]\n")

    return 0


def main():
    if len(sys.argv) != 2:
        print("Usage : python lister_contenu.py chemin/relatif/vers/dossier", file=sys.stderr)
        sys.exit(1)

    sys.exit(lister_dossier_non_recursif(sys.argv[1]))


if __name__ == "__main__":
    main()
