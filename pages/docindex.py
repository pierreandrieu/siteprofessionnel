"""
Module utilitaire pour indexer les documents (PDF) stockés sous MEDIA_ROOT/documents,
avec un cache LRU et un mécanisme d'invalidation simple basé sur un fichier ".v".

Hypothèses :
- Arborescence : media/documents/<annee>/<niveau>/<theme>/<slug>.pdf
- Le "slug" est le nom de fichier sans l'extension .pdf
- On ne lit jamais le contenu des PDF, on ne fait que lister/stat-er.

Conseils d'exploitation :
- Après toute publication de nouveaux PDF, écrire un nouveau "token" dans
  media/documents/.v (par exemple l'epoch courant) pour invalider le cache.
"""

from __future__ import annotations

from pathlib import Path
from functools import lru_cache
from typing import Dict, List, TypedDict
from django.conf import settings
import re


class DocumentItem(TypedDict):
    """
    Représente un fichier PDF individuel.
    - name      : nom "joli" pour affichage (sans préfixes numériques, underscores, etc.)
    - slug      : nom technique (nom de fichier sans .pdf)
    - rel_path  : chemin relatif à MEDIA_ROOT/documents (ex: "2025-2026/NSI_premiere/01_programmation/out/cours.pdf")
    - size      : taille du fichier en octets (0 si non disponible)
    """
    name: str
    slug: str
    rel_path: str
    size: int


# Types imbriqués pour l'arbre des archives :
# archives[year][level][theme] = List[DocumentItem]
ThemeMap = Dict[str, List[DocumentItem]]
LevelMap = Dict[str, ThemeMap]
ArchiveTree = Dict[str, LevelMap]

# Précompilation d'un motif pour retirer des préfixes numériques "01_", "02-"...
_PREFIX_RE = re.compile(r"^\d+[\-_]\s*")

# Fichier "version" : s'il change, on invalide le cache LRU
_VERSION_FILE: Path = Path(settings.MEDIA_ROOT) / "documents" / ".v"


def prettify(name: str) -> str:
    """
    Rend un nom de fichier plus lisible :
    - supprime un éventuel préfixe numérique "01_", "02-"...
    - remplace "_" et "-" par des espaces
    - retire l'extension s'il y en a une

    :param name: Nom de fichier ou base à nettoyer.
    :return: Libellé lisible pour l'utilisateur.
    """
    base: str = name.rsplit(".", 1)[0]
    base = _PREFIX_RE.sub("", base)
    base = base.replace("_", " ").replace("-", " ").strip()
    return base


def version_token() -> str:
    """
    Lit un petit "token de version" depuis media/documents/.v.
    Si le fichier n'existe pas, renvoie "0".

    Remarque : ce token n'est pas interprété, il sert juste de clé
    pour invalider le cache LRU quand il change.

    :return: Chaîne représentant la version courante.
    """
    try:
        return _VERSION_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return "0"


@lru_cache(maxsize=8)
def scan(version: str) -> ArchiveTree:
    """
    Explore MEDIA_ROOT/documents et construit une structure hiérarchique :
    { année: { niveau: { thème: [ DocumentItem, ... ] } } }

    Détail important :
    - on cherche d'abord des PDF dans <theme>/out/*.pdf (cas standard)
    - si out/ n'existe pas, on retombe sur <theme>/*.pdf (fallback)
    """
    base: Path = Path(settings.MEDIA_ROOT) / "documents"
    archives: ArchiveTree = {}

    if not base.exists():
        return archives

    # tri décroissant des années (ex: 2025-2026 d'abord)
    for year_dir in sorted((p for p in base.iterdir() if p.is_dir()), reverse=True):
        levels: LevelMap = {}

        for lvl_dir in sorted((p for p in year_dir.iterdir() if p.is_dir())):
            themes: ThemeMap = {}

            for th_dir in sorted((p for p in lvl_dir.iterdir() if p.is_dir())):
                items: List[DocumentItem] = []

                # 1) priorité au sous-dossier out/
                # 1) priorité au sous-dossier out/
                pdf_dir: Path = th_dir / "out"
                if pdf_dir.is_dir():
                    candidates = sorted(pdf_dir.glob("*.pdf"))
                else:
                    # 2) fallback : PDF directement à la racine du thème
                    candidates = sorted(th_dir.glob("*.pdf"))

                for f in candidates:
                    if not f.is_file():
                        continue
                    rel_path: str = f.relative_to(
                        base).as_posix()  # ex: "2024-2025/NSI_premiere/05_systeme/out/01_processus.pdf"
                    try:
                        size: int = f.stat().st_size
                    except OSError:
                        size = 0

                    items.append(
                        DocumentItem(
                            name=prettify(f.name),
                            slug=f.stem,
                            rel_path=rel_path,
                            size=size,
                        )
                    )

                if items:
                    themes[th_dir.name] = items

            if themes:
                levels[lvl_dir.name] = themes

        if levels:
            archives[year_dir.name] = levels

    return archives


def prewarm() -> None:
    """
    Pré-chauffe le cache LRU en effectuant un scan immédiat.
    Utile si on souhaite déclencher le scan depuis un hook de démarrage
    (ou un healthcheck HTTP).

    Exceptions :
    - Toute exception est volontairement absorbée pour ne pas bloquer un démarrage.
    """
    try:
        scan(version_token())
    except Exception:
        # On évite de casser le démarrage en cas d'erreur transitoire de FS.
        pass
