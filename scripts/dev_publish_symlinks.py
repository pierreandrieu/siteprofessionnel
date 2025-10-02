#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Publie les ressources du dépôt « enseignement-lycee » vers le miroir
servi par Django/Nginx (MEDIA_ROOT/documents), en créant **soit** des
liens symboliques (mode dev), **soit** des copies (mode prod), **soit**
des hardlinks (si le FS le permet).

Nouveauté : publication de fichiers complémentaires par thématique sous
le dossier `data/`, avec la convention suivante :

    <SRC>/<année>/<établissement>/<niveau>/<thème>/
    ├── out/*.pdf                     # PDFs du cours (inchangé)
    └── data/
        ├── <NN>/...                  # pièces jointes pour le cours NN_* (ex: 01/)
        └── commun/...                # pièces communes au thème (optionnel)

Le script :
  1) détecte les PDFs (obligatoire pour « découvrir » les thèmes actifs),
  2) publie les compléments Markdown/Assets de `exos_web_md/` (historique),
  3) publie les fichiers de `data/` (nouveau),
  4) purge éventuellement les obsolètes côté miroir,
  5) met à jour le token `.v` pour invalider les caches applicatifs.

Utilisation typique (depuis la racine du projet Django « siteprofessionnel ») :
    python scripts/dev_publish_symlinks.py \
        --src ../enseignement-lycee \
        --dst ./media/documents \
        --relative \
        --prune

Recommandations :
  - DEV  : garder --mode symlink (défaut) pour itérer rapidement.
  - PROD : préférer --mode copy pour ne pas exposer l’arborescence source.

Le script est tolérant aux dossiers/fichiers « cachés » (préfixe .),
qu’il ignore systématiquement.
"""

from __future__ import annotations

import argparse
import filecmp
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Motifs d’arbres attendus
# ---------------------------------------------------------------------------

YEAR_RE: re.Pattern[str] = re.compile(r"^20\d{2}-20\d{2}$")  # ex : 2025-2026
LEVEL_RE: re.Pattern[str] = re.compile(r"^[-A-Za-z0-9_]+$")  # ex : NSI_1e, NSI_Tle, SNT
THEME_RE: re.Pattern[str] = re.compile(r"^[-A-Za-z0-9_]+$")  # ex : 01_programmation_init

# Sous-dossiers autorisés dans `data/`
DATA_ALLOWED_SUBS: Set[str] = {"commun"}  # + sous-dossiers numérotés (01, 02, …)
DATA_NUM_RE: re.Pattern[str] = re.compile(r"^\d{1,3}$")


# ---------------------------------------------------------------------------
# Structures de données
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PdfEntry:
    """
    Représente un PDF source trouvé dans le dépôt « enseignement-lycee ».

    Attributes
    ----------
    year : str
        Nom du dossier d’année (YYYY-YYYY).
    level : str
        Nom du dossier de niveau (ex : NSI_1e).
    theme : str
        Nom du dossier de thème (parent de « out »).
    src : Path
        Chemin ABSOLU du PDF source.
    dst : Path
        Chemin ABSOLU de la cible dans le miroir (DST), sous
        <DST>/<year>/<etab>/<level>/<theme>/out/<file.pdf>.
    """
    year: str
    level: str
    theme: str
    src: Path
    dst: Path


@dataclass(frozen=True)
class MdAssetEntry:
    """
    Représente un fichier « complément web » sous exos_web_md.

    Attributes
    ----------
    year : str
        Année (YYYY-YYYY).
    level : str
        Niveau (ex : NSI_1e).
    theme : str
        Thème (ex : 05_systeme).
    src : Path
        Chemin ABSOLU du fichier source (dans exos_web_md).
    dst : Path
        Chemin ABSOLU de la cible (dans le miroir DST).
    """
    year: str
    level: str
    theme: str
    src: Path
    dst: Path


@dataclass(frozen=True)
class DataEntry:
    """
    Représente un fichier « pièce jointe » sous `data/`.

    Attributes
    ----------
    year : str
        Année (YYYY-YYYY).
    level : str
        Niveau (ex : NSI_1e).
    theme : str
        Thème (ex : 01_programmation_init).
    rel_dst : Path
        Chemin RELATIF sous le miroir (à concaténer à <DST>).
    src : Path
        Chemin ABSOLU du fichier source.
    """
    year: str
    level: str
    theme: str
    rel_dst: Path
    src: Path


# ---------------------------------------------------------------------------
# Helpers génériques
# ---------------------------------------------------------------------------

def is_hidden(p: Path) -> bool:
    """
    Indique si un chemin doit être considéré comme « caché ».

    Parameters
    ----------
    p : Path
        Chemin à tester.

    Returns
    -------
    bool
        True si le nom commence par « . », False sinon.
    """
    return p.name.startswith(".")


def files_identical(src: Path, dst: Path) -> bool:
    """
    Retourne True si src et dst sont (très probablement) identiques.
    Heuristique rapide (taille + mtime), puis comparaison byte-à-byte si doute.

    Parameters
    ----------
    src : Path
        Fichier source.
    dst : Path
        Fichier destination existant.

    Returns
    -------
    bool
        True si identiques, False sinon.
    """
    try:
        s1 = src.stat()
        s2 = dst.stat()
    except FileNotFoundError:
        return False

    if s1.st_size != s2.st_size:
        return False

    # Même inode/dev → même fichier (hardlink déjà pointé sur la bonne cible)
    try:
        if os.stat(src).st_dev == os.stat(dst).st_dev and os.stat(src).st_ino == os.stat(dst).st_ino:
            return True
    except FileNotFoundError:
        return False

    # Même mtime arrondi à la seconde + même taille : on suppose identique
    if int(s1.st_mtime) == int(s2.st_mtime):
        return True

    # Vérif stricte
    return filecmp.cmp(str(src), str(dst), shallow=False)


def ensure_parent_dir(path: Path, dry_run: bool) -> None:
    """
    S’assure que le dossier parent de `path` existe (mkdir -p).

    Parameters
    ----------
    path : Path
        Chemin cible (fichier ou lien).
    dry_run : bool
        Si True, ne fait qu’afficher l’action.
    """
    parent: Path = path.parent
    if parent.is_dir():
        return
    if dry_run:
        print(f"[dry-run] mkdir -p {parent}")
        return
    parent.mkdir(parents=True, exist_ok=True)


def make_symlink(src: Path, dst: Path, relative: bool, dry_run: bool) -> None:
    """
    Crée/remplace un lien symbolique `dst` pointant vers `src`.

    Parameters
    ----------
    src : Path
        Cible ABSOLUE (fichier source).
    dst : Path
        Emplacement ABSOLU du lien à créer.
    relative : bool
        True pour un lien relatif, False pour un lien absolu.
    dry_run : bool
        Si True, ne fait qu’afficher l’action.
    """
    target: Path
    if relative:
        try:
            target = Path(os.path.relpath(src, start=dst.parent))
        except Exception:
            # Volumes différents → retombe sur absolu
            target = src
    else:
        target = src

    # Si un lien existe déjà et pointe vers la même cible réelle, ne rien faire
    if dst.is_symlink():
        try:
            current: Path = dst.readlink()
            if (dst.parent / current).resolve() == (dst.parent / target).resolve():
                return
        except OSError:
            pass

    # Si un fichier existe (lien ou régulier), on remplace
    if dst.exists() or dst.is_symlink():
        if dry_run:
            print(f"[dry-run] rm {dst}")
        else:
            dst.unlink(missing_ok=True)

    # Création du lien
    if dry_run:
        print(f"[dry-run] ln -s {target} -> {dst}")
    else:
        ensure_parent_dir(dst, dry_run=False)
        dst.symlink_to(target)


def install_file(src: Path, dst: Path, mode: str, relative: bool, dry_run: bool) -> None:
    """
    Installe `src` dans `dst` selon `mode` :
      - "symlink" : création d’un lien symbolique
      - "copy"    : copie (avec métadonnées ; shutil.copy2)
      - "hardlink": hardlink (nécessite même FS)

    Parameters
    ----------
    src : Path
        Chemin ABSOLU du fichier source.
    dst : Path
        Chemin ABSOLU de la cible (miroir).
    mode : str
        "symlink" | "copy" | "hardlink".
    relative : bool
        Pertinent uniquement pour "symlink".
    dry_run : bool
        Si True, ne fait qu’afficher l’action.
    """
    if mode == "symlink":
        make_symlink(src=src, dst=dst, relative=relative, dry_run=dry_run)
        return

    ensure_parent_dir(dst, dry_run=dry_run)

    if mode == "copy":
        if dst.exists() and dst.is_file() and files_identical(src, dst):
            if dry_run:
                print(f"[dry-run] keep {dst} (unchanged)")
            return

        if dry_run:
            if dst.exists() or dst.is_symlink():
                print(f"[dry-run] rm {dst}")
            print(f"[dry-run] cp -p {src} {dst}")
            return

        tmp: Path = dst.with_suffix(dst.suffix + ".tmp~")
        try:
            if tmp.exists() or tmp.is_symlink():
                tmp.unlink()
            shutil.copy2(src, tmp)  # préserve mtime/perm
            os.replace(tmp, dst)  # move atomique
        finally:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass
        return

    # mode == "hardlink"
    if dst.exists():
        try:
            s1, s2 = os.stat(src), os.stat(dst)
            if s1.st_dev == s2.st_dev and s1.st_ino == s2.st_ino:
                return  # déjà le même hardlink
        except FileNotFoundError:
            pass
        if dry_run:
            print(f"[dry-run] rm {dst}")
        else:
            dst.unlink(missing_ok=True)

    if dry_run:
        print(f"[dry-run] ln {src} -> {dst}")
    else:
        os.link(src, dst)


def bump_version(dst_root: Path, dry_run: bool) -> None:
    """
    Met à jour le token « .v » sous <DST>, utilisé par Django pour invalider
    le cache LRU (on passe ce token en argument de fonctions @lru_cache).

    Concrètement, on écrit un timestamp (str(int(time.time()))).

    Parameters
    ----------
    dst_root : Path
        Racine ABSOLUE du miroir (MEDIA_ROOT/documents).
    dry_run : bool
        Si True, ne fait qu’afficher l’action.
    """
    vfile: Path = dst_root / ".v"
    token: str = str(int(time.time()))
    if dry_run:
        print(f"[dry-run] echo {token} > {vfile}")
        return
    ensure_parent_dir(vfile, dry_run=False)
    vfile.write_text(token, encoding="utf-8")


def prune_obsolete(dst_root: Path, valid_targets: Iterable[Path], dry_run: bool) -> int:
    """
    Supprime du miroir <DST> les fichiers/liens qui ne sont plus « attendus »
    (PDF, compléments exos_web_md, et fichiers data/), ou les liens cassés.

    Parameters
    ----------
    dst_root : Path
        Racine ABSOLUE du miroir (MEDIA_ROOT/documents).
    valid_targets : Iterable[Path]
        Itérable de **chemins absolus sous <DST>** qui doivent rester en place.
    dry_run : bool
        Si True, ne fait qu’afficher les suppressions.

    Returns
    -------
    int
        Nombre d’entrées supprimées.
    """
    deletions: int = 0
    dst_root_abs: Path = dst_root.resolve()

    valid_rel: Set[Path] = set()
    for p in valid_targets:
        try:
            rel = Path(p).relative_to(dst_root_abs)
        except ValueError:
            # Une cible 'attendue' n'est pas sous <DST> → on ignore mais on log
            print(f"[warn] cible attendue hors DST, ignorée: {p}", file=sys.stderr)
            continue
        valid_rel.add(rel)

    if not dst_root.is_dir():
        return 0

    for path in dst_root.rglob("*"):
        if path.is_dir() or path.name == ".v":
            continue

        rel = path.relative_to(dst_root_abs)
        broken: bool = path.is_symlink() and (not path.exists())

        if (rel not in valid_rel) or broken:
            if dry_run:
                print(f"[dry-run] rm obsolete {path}")
            else:
                path.unlink(missing_ok=True)
            deletions += 1

    return deletions


# ---------------------------------------------------------------------------
# Détection des niveaux/thèmes et itération sources
# ---------------------------------------------------------------------------

def dir_has_themes(level_dir: Path) -> bool:
    """
    Heuristique : ce dossier de niveau contient-il des thèmes avec au moins un PDF ?
    On regarde `th/out/*.pdf` si `out` existe, sinon `th/*.pdf`.

    Parameters
    ----------
    level_dir : Path
        Dossier du niveau à inspecter.

    Returns
    -------
    bool
        True si au moins un PDF est détecté, False sinon.
    """
    try:
        for th in level_dir.iterdir():
            if is_hidden(th) or not th.is_dir():
                continue
            out_dir: Path = th / "out"
            if out_dir.is_dir() and any(f.suffix.lower() == ".pdf" and not is_hidden(f) for f in out_dir.iterdir()):
                return True
            if any(f.suffix.lower() == ".pdf" and not is_hidden(f) for f in th.iterdir()):
                return True
    except OSError:
        return False
    return False


def has_themes(level_dir: Path) -> bool:
    """
    Variante non « safe » (usage interne) : indique s’il existe un PDF sous ce niveau.
    """
    if not level_dir.is_dir():
        return False

    for th in level_dir.iterdir():
        if is_hidden(th) or not th.is_dir():
            continue
        out_dir: Path = th / "out"
        if out_dir.is_dir() and any(f.suffix.lower() == ".pdf" and not is_hidden(f) for f in out_dir.iterdir()):
            return True
        if any(f.suffix.lower() == ".pdf" and not is_hidden(f) for f in th.iterdir()):
            return True

    return False


def _iter_level_dirs(year_dir: Path) -> Iterator[Path]:
    """
    Rend des dossiers « niveau » quel que soit le layout source.

    Deux layouts possibles dans la pratique :
      - ancien : <year>/<level>/<theme>/...
      - nouveau : <year>/<institution>/<level>/<theme>/...

    Pour la **publication**, on encourage fortement le *nouveau* layout.
    """
    for first in sorted((p for p in year_dir.iterdir() if p.is_dir() and not is_hidden(p))):
        if dir_has_themes(first):
            # Ancien layout : <year>/<level>/...
            yield first
        else:
            for lvl in sorted((p for p in first.iterdir() if p.is_dir() and not is_hidden(p))):
                if dir_has_themes(lvl):
                    # Nouveau layout : <year>/<institution>/<level>/...
                    yield lvl


def iter_pdfs(src_root: Path, dst_root: Path) -> Iterator[PdfEntry]:
    """
    Itère sur tous les PDF `out/*.pdf` sous <SRC>, et calcule la
    destination sous <DST>/.../out/.

    On **ignore** :
      - tout dossier/fichier caché (préfixe « . »),
      - l’« ancien layout » directement sous <year>/<level>/... (pour publier,
        on préfère le layout avec établissement).

    Parameters
    ----------
    src_root : Path
        Racine ABSOLUE du dépôt « enseignement-lycee ».
    dst_root : Path
        Racine ABSOLUE du miroir « media/documents ».

    Yields
    ------
    PdfEntry
        Une entrée par PDF détecté.
    """
    for year_dir in sorted((p for p in src_root.iterdir() if p.is_dir() and not is_hidden(p))):
        year: str = year_dir.name
        if not YEAR_RE.match(year):
            continue

        for institution_dir in sorted((p for p in year_dir.iterdir() if p.is_dir() and not is_hidden(p))):
            # Ancien layout : <year>/<level>/...  → ignore pour la publication
            if LEVEL_RE.match(institution_dir.name) and has_themes(institution_dir):
                print(f"[warn] ancien layout sans établissement ignoré: {institution_dir}")
                continue

            for level_dir in sorted(
                    (p for p in institution_dir.iterdir() if p.is_dir() and not is_hidden(p) and LEVEL_RE.match(p.name))
            ):
                if not has_themes(level_dir):
                    continue

                for theme_dir in sorted((p for p in level_dir.iterdir() if p.is_dir() and not is_hidden(p))):
                    out_dir: Path = theme_dir / "out"
                    if not out_dir.is_dir():
                        continue

                    for pdf in sorted(out_dir.glob("*.pdf")):
                        if is_hidden(pdf) or not pdf.is_file():
                            continue
                        rel_dst: Path = Path(
                            year) / institution_dir.name / level_dir.name / theme_dir.name / "out" / pdf.name
                        yield PdfEntry(
                            year=year,
                            level=level_dir.name,
                            theme=theme_dir.name,
                            src=pdf.resolve(),
                            dst=(dst_root / rel_dst).resolve(),
                        )


# ---------------------------------------------------------------------------
# Compléments exos_web_md (historique)
# ---------------------------------------------------------------------------

def iter_md_assets_for_theme(
        year: str,
        level: str,
        theme: str,
        src_theme_dir: Path,
        dst_root: Path,
        asset_exts: Set[str],
) -> Iterator[MdAssetEntry]:
    """
    Itère sur les fichiers d’un dossier `exos_web_md` (s’il existe) pour un couple
    (année, niveau, thème) donné. On publie :

      - tous les *.md
      - tous les fichiers dont l’extension (minuscule) est dans `asset_exts`

    On ne descend pas récursivement ; on reste à la racine de `exos_web_md`.

    Parameters
    ----------
    year : str
    level : str
    theme : str
    src_theme_dir : Path
    dst_root : Path
    asset_exts : Set[str]

    Yields
    ------
    MdAssetEntry
    """
    src_md_dir: Path = src_theme_dir / "exos_web_md"
    if not src_md_dir.is_dir() or is_hidden(src_md_dir):
        return

    dst_theme_dir: Path = (dst_root / year / level / theme / "exos_web_md").resolve()

    # 1) Markdown
    for md in sorted(src_md_dir.glob("*.md")):
        if md.is_file() and not is_hidden(md):
            yield MdAssetEntry(year, level, theme, md.resolve(), (dst_theme_dir / md.name).resolve())

    # 2) Assets
    for f in sorted(src_md_dir.iterdir()):
        if not f.is_file() or is_hidden(f):
            continue
        ext: str = f.suffix.lower()
        if ext in asset_exts:
            yield MdAssetEntry(year, level, theme, f.resolve(), (dst_theme_dir / f.name).resolve())


# ---------------------------------------------------------------------------
# Fichiers complémentaires `data/` (nouveau)
# ---------------------------------------------------------------------------

def iter_data_files_for_theme(
        year: str,
        level: str,
        theme: str,
        src_theme_dir: Path,
        dst_root: Path,
) -> Iterator[DataEntry]:
    """
    Itère sur les fichiers d’un dossier `data/` (s’il existe) pour un couple
    (année, niveau, thème). On publie *tous* les fichiers des sous-dossiers
    autorisés :
      - `data/<NN>/...` avec <NN> ∈ [1..999] (format « 01 », « 2 », « 105 », etc.)
      - `data/commun/...` (fichiers génériques du thème)

    L’arborescence relative sous <DST> est conservée :
      <DST>/<year>/<level>/<theme>/data/<NN>/*  et  .../data/commun/*

    Parameters
    ----------
    year : str
        Année scolaire YYYY-YYYY.
    level : str
        Dossier de niveau (ex : NSI_1e).
    theme : str
        Dossier de thème (ex : 01_programmation_init).
    src_theme_dir : Path
        Chemin ABSOLU du dossier de thème côté source.
    dst_root : Path
        Racine ABSOLUE du miroir (MEDIA_ROOT/documents).

    Yields
    ------
    DataEntry
        Une entrée par fichier à publier.
    """
    src_data_dir: Path = src_theme_dir / "data"
    if not src_data_dir.is_dir() or is_hidden(src_data_dir):
        return

    for sub in sorted((p for p in src_data_dir.iterdir() if p.is_dir() and not is_hidden(p))):
        nom: str = sub.name
        if not (nom in DATA_ALLOWED_SUBS or DATA_NUM_RE.match(nom)):
            # Ignore silencieusement les sous-dossiers non conformes
            continue

        for f in sorted(sub.rglob("*")):
            if f.is_dir() or is_hidden(f):
                continue
            rel: Path = Path(year) / level / theme / "data" / nom / f.relative_to(sub)
            yield DataEntry(
                year=year,
                level=level,
                theme=theme,
                rel_dst=rel,
                src=f.resolve(),
            )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_exts(exts_csv: str) -> Set[str]:
    """
    Convertit une liste CSV d’extensions en ensemble normalisé
    (minuscule, **avec** le point).

    Exemple : "png,jpg,svg,webp" → {".png",".jpg",".svg",".webp"}
    """
    items: List[str] = [e.strip().lower() for e in exts_csv.split(",") if e.strip()]
    normed: Set[str] = set()
    for e in items:
        normed.add(e if e.startswith(".") else f".{e}")
    return normed


def main(argv: Optional[List[str]] = None) -> int:
    """
    Point d’entrée CLI.

    Étapes :
      1) Lister tous les PDF à publier (entries_pdf)
      2) Pour chaque (année, niveau, thème) :
         a) lister/composer les compléments exos_web_md (entries_md)
         b) lister/composer les pièces jointes sous data/ (entries_data)
      3) Créer les cibles (liens/copies/hardlinks)
      4) Purger les fichiers obsolètes (optionnel)
      5) Mettre à jour le token .v

    Returns
    -------
    int
        Code de retour process (0 = OK).
    """
    parser = argparse.ArgumentParser(
        description="Publie les PDF 'out/*.pdf', les compléments 'exos_web_md/*' et les fichiers 'data/*' vers MEDIA_ROOT/documents"
    )
    parser.add_argument(
        "--src",
        type=Path,
        default=Path("../enseignement-lycee"),
        help="Racine du dépôt 'enseignement-lycee' (défaut : ../enseignement-lycee)",
    )
    parser.add_argument(
        "--dst",
        type=Path,
        default=Path("./media/documents"),
        help="Racine du miroir destination (défaut : ./media/documents)",
    )
    parser.add_argument(
        "--relative",
        action="store_true",
        help="Créer des liens symboliques RELATIFS (par défaut : absolus).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Afficher les actions sans modifier le disque.",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Supprimer les fichiers obsolètes côté destination (DST).",
    )
    parser.add_argument(
        "--assets-ext",
        type=str,
        default="png,jpg,jpeg,gif,svg,webp",
        help="Extensions d’assets à publier depuis exos_web_md (CSV). Ex : png,jpg,svg,webp",
    )
    parser.add_argument(
        "--mode",
        choices=("symlink", "copy", "hardlink"),
        default="symlink",
        help="Méthode de publication : symlink (dev), copy (prod), hardlink (même FS).",
    )

    args = parser.parse_args(argv)

    src_root: Path = args.src.resolve()
    dst_root: Path = args.dst.resolve()
    asset_exts: Set[str] = parse_exts(args.assets_ext)
    dry_run: bool = bool(args.dry_run)
    relative: bool = bool(args.relative)
    mode: str = str(args.mode)
    do_prune: bool = bool(args.prune)

    # --- Validation des chemins ---
    if not src_root.is_dir():
        print(f"ERREUR : --src introuvable ou non dossier : {src_root}", file=sys.stderr)
        return 2

    # --- 1) Lister tous les PDF ---
    entries_pdf: List[PdfEntry] = list(iter_pdfs(src_root, dst_root))
    if not entries_pdf:
        print("Aucun PDF trouvé sous '<SRC>/<année>/<etab>/<niveau>/<thème>/out/'. Rien à publier.")
        # On crée quand même <DST> et le .v pour éviter les 404 côté Django
        if not dry_run:
            dst_root.mkdir(parents=True, exist_ok=True)
            bump_version(dst_root, dry_run=False)
        return 0

    # --- 2a) Compléments exos_web_md par thème ---
    seen_themes: Set[Tuple[str, str, str]] = set()
    entries_md: List[MdAssetEntry] = []
    entries_data: List[DataEntry] = []

    for e in entries_pdf:
        key: Tuple[str, str, str] = (e.year, e.level, e.theme)
        if key in seen_themes:
            continue
        seen_themes.add(key)

        src_theme_dir: Path = e.src.parent.parent  # .../<theme>/out/<file>.pdf → parent.parent = <theme>

        # exos_web_md (historique)
        entries_md.extend(
            list(
                iter_md_assets_for_theme(
                    year=e.year,
                    level=e.level,
                    theme=e.theme,
                    src_theme_dir=src_theme_dir,
                    dst_root=dst_root,
                    asset_exts=asset_exts,
                )
            )
        )

        # data/ (nouveau)
        entries_data.extend(
            list(
                iter_data_files_for_theme(
                    year=e.year,
                    level=e.level,
                    theme=e.theme,
                    src_theme_dir=src_theme_dir,
                    dst_root=dst_root,
                )
            )
        )

    # --- 3) Création des cibles ---
    for entry in entries_pdf:
        ensure_parent_dir(entry.dst, dry_run=dry_run)
        install_file(src=entry.src, dst=entry.dst, mode=mode, relative=relative, dry_run=dry_run)

    for m in entries_md:
        ensure_parent_dir(m.dst, dry_run=dry_run)
        install_file(src=m.src, dst=m.dst, mode=mode, relative=relative, dry_run=dry_run)

    for d in entries_data:
        dst: Path = (dst_root / d.rel_dst).resolve()
        ensure_parent_dir(dst, dry_run=dry_run)
        install_file(src=d.src, dst=dst, mode=mode, relative=relative, dry_run=dry_run)

    # --- 4) Purge optionnelle des obsolètes ---
    if do_prune:
        valid_dsts: List[Path] = [e.dst for e in entries_pdf] + [m.dst for m in entries_md] + \
                                 [(dst_root / d.rel_dst).resolve() for d in entries_data]
        deleted: int = prune_obsolete(dst_root, valid_dsts, dry_run=dry_run)
        if dry_run:
            print(f"[dry-run] fichiers obsolètes à supprimer : {deleted}")
        else:
            print(f"Obsolètes supprimés : {deleted}")

    # --- 5) Bump du token .v ---
    bump_version(dst_root, dry_run=dry_run)

    # --- Résumé ---
    total_pdfs: int = len(entries_pdf)
    total_md: int = len(entries_md)
    total_data: int = len(entries_data)
    if dry_run:
        print("\n[dry-run] Terminé (aucune modification effectuée).")
        print(f"[dry-run] {total_pdfs} PDF détectés, {total_md} compléments exos_web_md, {total_data} fichiers data/")
    else:
        print("Publication terminée.")
        print(f"- Source : {src_root}")
        print(f"- Miroir : {dst_root}")
        print(f"- {total_pdfs} PDF publiés")
        print(f"- {total_md} compléments exos_web_md publiés")
        print(f"- {total_data} fichiers data/ publiés")
        print("- Token '.v' mis à jour (invalidation du cache LRU)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
