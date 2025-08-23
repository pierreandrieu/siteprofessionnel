#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Publie localement les ressources du dépôt "enseignement-lycee" vers
le dossier média attendu par le site (media/documents), en créant des
LIENS SYMBOLIQUES (pas de duplication de fichiers).

Ce script gère DEUX catégories de contenus :
  1) Les PDF compilés situés sous : <SRC>/<année>/<niveau>/<thème>/out/*.pdf
  2) Les compléments web situés sous : <SRC>/<année>/<niveau>/<thème>/exos_web_md/
     - fichiers .md (exercices, explications)
     - images/ressources (extensions configurables)

Côté destination (miroir web), on obtient :
  <DST>/<année>/<niveau>/<thème>/out/*.pdf
  <DST>/<année>/<niveau>/<thème>/exos_web_md/*.{md,png,jpg,...}
  <DST>/.v   (token de version pour invalider le cache Django)

Pourquoi des symlinks ?
- Instantané (pas de copie), idéal en développement.
- L'arborescence "DST" correspond exactement à ce que Django/Nginx servent.

Options utiles :
- --dry-run    : montre ce qui serait fait sans rien modifier
- --prune      : supprime les liens obsolètes côté DST (PDF ET compléments)
- --relative   : crée des liens symboliques RELATIFS (par défaut : absolus)
- --assets-ext : liste d'extensions d'assets à publier depuis exos_web_md
                (par défaut : .png,.jpg,.jpeg,.gif,.svg,.webp)

Usage typique (depuis la racine du projet Django "siteprofessionnel") :
    python scripts/dev_publish_symlinks.py \
        --src ../enseignement-lycee \
        --dst ./media/documents \
        --prune --relative
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Set, Tuple

# -----------------------------
# Motifs d'arbres attendus
# -----------------------------

YEAR_RE: re.Pattern[str] = re.compile(r"^20\d{2}-20\d{2}$")  # ex: 2025-2026
LEVEL_RE: re.Pattern[str] = re.compile(r"^[-A-Za-z0-9_]+$")  # ex: NSI_premiere, NSI_terminale, SNT
THEME_RE: re.Pattern[str] = re.compile(r"^[-A-Za-z0-9_]+$")  # ex: 05_systeme, 01_programmation_init


# -----------------------------
# Structures de données
# -----------------------------

@dataclass(frozen=True)
class PdfEntry:
    """
    Représente un PDF source trouvé dans le dépôt "enseignement-lycee".

    Attributs :
      - year : nom du dossier d'année (YYYY-YYYY)
      - level: nom du dossier de niveau
      - theme: nom du dossier de thème (parent de "out")
      - src  : chemin ABSOLU du PDF source
      - dst  : chemin ABSOLU du lien (futur) dans <DST>/<year>/<level>/<theme>/out/<file.pdf>
    """
    year: str
    level: str
    theme: str
    src: Path
    dst: Path  # pointe vers .../<year>/<level>/<theme>/out/<file.pdf> côté DST


@dataclass(frozen=True)
class MdAssetEntry:
    """
    Représente un fichier "complément web" (markdown ou asset) sous exos_web_md.

    Attributs :
      - year  : année (YYYY-YYYY)
      - level : niveau (ex: NSI_premiere)
      - theme : thème (ex: 05_systeme)
      - src   : chemin ABSOLU du fichier source dans exos_web_md
      - dst   : chemin ABSOLU du lien (futur) dans <DST>/<year>/<level>/<theme>/exos_web_md/<file>
    """
    year: str
    level: str
    theme: str
    src: Path
    dst: Path


# -----------------------------
# Parcours des sources (SRC)
# -----------------------------

def iter_pdfs(src_root: Path, dst_root: Path) -> Iterator[PdfEntry]:
    """
    Itère sur tous les PDF "out/*.pdf" sous <SRC>, et calcule
    le chemin de destination correspondant sous <DST>/.../out/.

    :param src_root: Racine du dépôt "enseignement-lycee".
    :param dst_root: Racine du miroir "media/documents".
    :yield: PdfEntry pour chaque PDF détecté.
    """
    # On parcourt <SRC>/<année>/<niveau>/<thème>/out/*.pdf
    for year_dir in sorted((p for p in src_root.iterdir() if p.is_dir())):
        year: str = year_dir.name
        if not YEAR_RE.match(year):
            continue

        for level_dir in sorted((p for p in year_dir.iterdir() if p.is_dir())):
            level: str = level_dir.name
            if not LEVEL_RE.match(level):
                continue

            for theme_dir in sorted((p for p in level_dir.iterdir() if p.is_dir())):
                theme: str = theme_dir.name
                if not THEME_RE.match(theme):
                    continue

                out_dir: Path = theme_dir / "out"
                if not out_dir.is_dir():
                    continue

                for pdf in sorted(out_dir.glob("*.pdf")):
                    if not pdf.is_file():
                        continue
                    # Destination = <DST>/<year>/<level>/<theme>/out/<file.pdf>
                    rel_dst: Path = Path(year) / level / theme / "out" / pdf.name
                    yield PdfEntry(
                        year=year,
                        level=level,
                        theme=theme,
                        src=pdf.resolve(),
                        dst=(dst_root / rel_dst).resolve(),
                    )


def iter_md_assets_for_theme(
        year: str,
        level: str,
        theme: str,
        src_theme_dir: Path,
        dst_root: Path,
        asset_exts: Set[str],
) -> Iterator[MdAssetEntry]:
    """
    Itère sur les fichiers d'un dossier exos_web_md (s'il existe) pour un couple
    (année, niveau, thème) donné. On publie :
      - tous les *.md
      - tous les fichiers dont l'extension (en minuscule) est présente dans `asset_exts`

    NB : on ne descend PAS dans des sous-dossiers de exos_web_md (simple et suffisant
         pour les besoins courants). Si besoin, faire évoluer vers un parcours récursif.

    :param year: Année (YYYY-YYYY).
    :param level: Niveau (ex: NSI_premiere).
    :param theme: Thème (ex: 05_systeme).
    :param src_theme_dir: Chemin ABSOLU du dossier du thème côté SRC.
    :param dst_root: Racine ABSOLUE de la destination (media/documents).
    :param asset_exts: Ensemble d'extensions à publier (ex: {".png", ".jpg", ...}).
    :yield: MdAssetEntry pour chaque fichier à publier (liens).
    """
    src_md_dir: Path = src_theme_dir / "exos_web_md"
    if not src_md_dir.is_dir():
        return

    dst_theme_dir: Path = (dst_root / year / level / theme / "exos_web_md").resolve()

    # 1) fichiers markdown
    for md in sorted(src_md_dir.glob("*.md")):
        if md.is_file():
            yield MdAssetEntry(year, level, theme, md.resolve(), (dst_theme_dir / md.name).resolve())

    # 2) assets (images, etc.) à la racine de exos_web_md
    for f in sorted(src_md_dir.iterdir()):
        if not f.is_file():
            continue
        ext: str = f.suffix.lower()
        if ext in asset_exts:
            yield MdAssetEntry(year, level, theme, f.resolve(), (dst_theme_dir / f.name).resolve())


# -----------------------------
# Fonctions d'E/S (liens, dossiers)
# -----------------------------

def ensure_parent_dir(path: Path, dry_run: bool) -> None:
    """
    S'assure que le dossier parent de "path" existe.

    :param path: Chemin cible (fichier ou lien à créer).
    :param dry_run: Si True, n'effectue aucune modification.
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
    Crée (ou remplace) un lien symbolique "dst" pointant vers "src".

    - Si "dst" existe déjà et pointe vers la même cible, on ne fait rien.
    - Sinon, on supprime "dst" et on recrée le lien.
    - "relative=True" fabrique des liens RELATIFS (plus portables si on déplace l'arbre).

    :param src: Chemin ABSOLU de la cible (source).
    :param dst: Chemin ABSOLU du lien à créer.
    :param relative: True pour un lien relatif, False pour absolu.
    :param dry_run: Si True, ne modifie rien.
    """
    # Déterminer la cible du lien (relative ou absolue)
    target: Path
    if relative:
        try:
            target = Path(os.path.relpath(src, start=dst.parent))
        except Exception:
            # En cas d'échec (volumes distincts), on retombe sur un chemin absolu
            target = src
    else:
        target = src

    # Si un lien existe déjà et pointe vers la même chose, ne rien faire
    if dst.is_symlink():
        try:
            current: Path = dst.readlink()
            if current == target:
                return
        except OSError:
            # Lien cassé → on remplace
            pass

    # Si un fichier (ou lien) existe, on le remplace
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


def bump_version(dst_root: Path, dry_run: bool) -> None:
    """
    Met à jour le token de version ".v" sous <DST> pour invalider le cache Django.

    :param dst_root: Racine du miroir "media/documents".
    :param dry_run: Si True, ne modifie rien.
    """
    vfile: Path = dst_root / ".v"
    token: str = str(int(time.time()))
    if dry_run:
        print(f"[dry-run] echo {token} > {vfile}")
        return
    # s'assure que media/documents existe
    ensure_parent_dir(vfile, dry_run=False)
    vfile.write_text(token, encoding="utf-8")


def prune_obsolete(dst_root: Path, valid_targets: Iterable[Path], dry_run: bool) -> None:
    """
    Supprime du miroir DST les liens symboliques qui ne correspondent plus
    à aucun fichier source listé (PDF OU compléments), ou dont la cible n'existe plus.

    Stratégie :
      - On constitue l'ensemble des chemins DEST attendus (valid_targets).
      - On parcourt TOUS les symlinks sous <DST> :
          * si le symlink ne figure pas dans valid_targets → suppression
          * si le symlink est "cassé" (cible inexistante) → suppression

    :param dst_root: Racine du miroir "media/documents".
    :param valid_targets: Itérable des chemins de destination attendus (c.-à-d. les chemins de liens).
    :param dry_run: Si True, ne modifie rien.
    """
    valid_set: Set[Path] = {p.resolve() for p in valid_targets}
    if not dst_root.is_dir():
        return

    for link in dst_root.rglob("*"):
        if not link.is_symlink():
            continue

        # lien cassé (cible absente) → suppression
        try:
            _ = link.resolve().exists()
        except FileNotFoundError:
            if dry_run:
                print(f"[dry-run] rm broken {link}")
            else:
                link.unlink(missing_ok=True)
            continue

        # si ce chemin de lien n'est pas attendu → suppression
        if link.resolve() and link.resolve() not in valid_set:
            if dry_run:
                print(f"[dry-run] rm obsolete {link}")
            else:
                link.unlink(missing_ok=True)


# -----------------------------
# Programme principal (CLI)
# -----------------------------

def parse_exts(exts_csv: str) -> Set[str]:
    """
    Convertit une liste CSV d'extensions en ensemble normalisé (avec point, en minuscule).
    Exemple : "png,jpg,svg,webp" → {".png",".jpg",".svg",".webp"}
    """
    items: List[str] = [e.strip().lower() for e in exts_csv.split(",") if e.strip()]
    normed: Set[str] = set()
    for e in items:
        normed.add(e if e.startswith(".") else f".{e}")
    return normed


def main(argv: Optional[List[str]] = None) -> int:
    """
    Point d'entrée CLI : crée un miroir par symlinks des PDF 'out/*.pdf' et
    des compléments 'exos_web_md/*' vers <DST>.

    Étapes :
      1) indexer les PDF sources (entries_pdf)
      2) pour chaque thème rencontré, indexer les compléments exos_web_md (entries_md)
      3) créer les dossiers et liens
      4) optionnellement purger les liens obsolètes
      5) mettre à jour le token .v pour invalider le cache Django
    """
    parser = argparse.ArgumentParser(
        description="Miroir local par symlinks des PDF 'out/*.pdf' et compléments 'exos_web_md/*' vers media/documents"
    )
    parser.add_argument("--src", type=Path, default=Path("../enseignement-lycee"),
                        help="Racine du dépôt 'enseignement-lycee' (par défaut: ../enseignement-lycee)")
    parser.add_argument("--dst", type=Path, default=Path("./media/documents"),
                        help="Racine du miroir destination (par défaut: ./media/documents)")
    parser.add_argument("--relative", action="store_true",
                        help="Créer des liens symboliques RELATIFS (par défaut: absolus)")
    parser.add_argument("--dry-run", action="store_true",
                        help="N'affiche que les actions sans modifier le disque")
    parser.add_argument("--prune", action="store_true",
                        help="Supprimer les liens obsolètes côté destination")
    parser.add_argument("--assets-ext", type=str, default="png,jpg,jpeg,gif,svg,webp",
                        help="Extensions d'assets à publier depuis exos_web_md (CSV). Ex: png,jpg,svg,webp")

    args = parser.parse_args(argv)

    src_root: Path = args.src.resolve()
    dst_root: Path = args.dst.resolve()
    asset_exts: Set[str] = parse_exts(args.assets_ext)

    if not src_root.is_dir():
        print(f"ERREUR: --src {src_root} introuvable.", file=sys.stderr)
        return 2

    # 1) Lister tous les PDF
    entries_pdf: List[PdfEntry] = list(iter_pdfs(src_root, dst_root))
    if not entries_pdf:
        print("Aucun PDF trouvé sous '<SRC>/*/*/*/out/'. Rien à publier.")
        # on crée quand même le dossier racine + .v pour éviter les erreurs d'absence
        if not args.dry_run:
            (dst_root).mkdir(parents=True, exist_ok=True)
            bump_version(dst_root, dry_run=False)
        return 0

    # 2) Pour chaque thème rencontré, préparer la liste des compléments exos_web_md
    seen_themes: Set[Tuple[str, str, str]] = set()
    entries_md: List[MdAssetEntry] = []

    for e in entries_pdf:
        key: Tuple[str, str, str] = (e.year, e.level, e.theme)
        if key in seen_themes:
            continue
        seen_themes.add(key)

        src_theme_dir: Path = e.src.parent.parent  # .../<theme>/out/<file>.pdf → parent=out, parent.parent=theme
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

    # 3) Créer les symlinks
    #    3a) PDF
    for e in entries_pdf:
        ensure_parent_dir(e.dst, dry_run=args.dry_run)
        make_symlink(src=e.src, dst=e.dst, relative=args.relative, dry_run=args.dry_run)

    #    3b) Compléments MD & assets
    for m in entries_md:
        ensure_parent_dir(m.dst, dry_run=args.dry_run)
        make_symlink(src=m.src, dst=m.dst, relative=args.relative, dry_run=args.dry_run)

    # 4) Optionnel : purge des liens obsolètes (PDF + compléments)
    if args.prune:
        valid_dsts: List[Path] = [e.dst for e in entries_pdf] + [m.dst for m in entries_md]
        prune_obsolete(dst_root, valid_dsts, dry_run=args.dry_run)

    # 5) Mettre à jour le token ".v" pour invalider le cache Django
    bump_version(dst_root, dry_run=args.dry_run)

    # 6) Affichage final
    total_pdfs: int = len(entries_pdf)
    total_md: int = len(entries_md)
    if args.dry_run:
        print(f"\n[dry-run] Terminé (aucune modification effectuée).")
        print(f"[dry-run] {total_pdfs} PDF détectés, {total_md} compléments MD/assets détectés.")
    else:
        print("Publication locale terminée.")
        print(f"- Source : {src_root}")
        print(f"- Miroir : {dst_root}")
        print(f"- {total_pdfs} PDF publiés")
        print(f"- {total_md} compléments (md/assets) publiés")
        print("- Cache LRU invalidé ('.v' mis à jour)")
    return 0


if __name__ == "__main__":
    # Important : appeler main() pour traiter les arguments (--help, --dry-run, etc.)
    raise SystemExit(main())
