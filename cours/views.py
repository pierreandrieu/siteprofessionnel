from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Final, Iterable, List, Tuple, Optional
from datetime import date

from django.utils import timezone
from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from urllib.parse import quote

from scripts.dev_publish_symlinks import dir_has_themes
from .docindex import version_token


@dataclass(frozen=True)
class DocItem:
    """
    Représente un document .pdf découvert sur le disque.

    year            : année scolaire (ex: "2024-2025")
    institution     : nom du dossier établissement si présent (ex: "Lycée Jacques Prévert"), sinon ""
    level           : nom du dossier niveau (ex: "NSI_premiere")
    theme           : nom du dossier thème (ex: "01_programmation_init")
    slug            : base du nom de fichier (ex: "01_operateurs_python")
    title           : titre humain (slug nettoyé)
    size_bytes      : taille du PDF en octets
    pdf_rel_path    : chemin relatif à MEDIA_ROOT (ex: "documents/.../file.pdf")
    url             : URL Django de la page détail (ex: "/cours/2024-2025/NSI_premiere/.../slug/")
    """
    year: str
    institution: str
    level: str
    theme: str
    slug: str
    title: str
    size_bytes: int
    pdf_rel_path: str
    url: str


# mapping "slug d’URL" → "nom de dossier niveau sur disque"
LEVEL_SLUG_TO_DIR: Final[Dict[str, str]] = {
    "nsi-premiere": "NSI_premiere",
    "nsi-terminale": "NSI_terminale",
    "snt": "SNT",
    # Prépare les futurs niveaux Université (tu pourras renommer si besoin)
    "diu-nsi": "DIU_NSI",
    "m2-meef": "M2_MEEF",
}

# mapping inverse utile pour fabriquer des liens
LEVEL_DIR_TO_SLUG: Final[Dict[str, str]] = {v: k for k, v in LEVEL_SLUG_TO_DIR.items()}


def current_school_year(today: date | None = None) -> str:
    """
    Retourne l'année scolaire courante au format 'YYYY-YYYY'.

    Règle :
      - du 1er août au 31 décembre : "année_courante-(année_courante+1)"
      - du 1er janvier au 31 juillet      : "(année_courante-1)-année_courante"
    """
    d = today or timezone.localdate()
    # (si tu préfères éviter timezone : d = date.today())
    if d.month >= 8:
        start = d.year
        end = d.year + 1
    else:
        start = d.year - 1
        end = d.year
    return f"{start}-{end}"


def _media_root() -> Path:
    """Racine MEDIA_ROOT en tant que Path."""
    return Path(settings.MEDIA_ROOT)


def _human_title(slug: str) -> str:
    """
    Transforme "01_operateurs_python" → "operateurs python".
    - enlève un éventuel préfixe numérique "01_", "02-"
    - remplace "_" par espaces
    """
    title = slug.replace("_", " ")
    if len(title) >= 3 and title[:3].isdigit():
        title = title[3:].lstrip(" _-")
    return title


def _hidden(p: Path) -> bool:
    return p.name.startswith(".")


def _iter_level_dirs(year_dir: Path) -> Iterable[Tuple[str, Path]]:
    """
    Rend (institution, level_dir) pour gérer 2 layouts source :
      - ancien : <year>/<level>/<theme>/...
      - nouveau : <year>/<institution>/<level>/<theme>/...
    'institution' vaut "" dans l'ancien layout.
    """
    for inst in sorted((p for p in year_dir.iterdir() if p.is_dir() and not _hidden(p)), key=lambda p: p.name):
        for lvl in sorted((p for p in inst.iterdir() if p.is_dir() and not _hidden(p)), key=lambda p: p.name):
            if dir_has_themes(lvl):
                yield inst.name, lvl


def _collect_docs_under_level(year: str, institution: str, level_dir: Path) -> List[DocItem]:
    items: List[DocItem] = []
    for theme_dir in sorted((p for p in level_dir.iterdir() if p.is_dir() and not _hidden(p)), key=lambda p: p.name):
        pdf_dir = theme_dir / "out"
        candidates = sorted(pdf_dir.glob("*.pdf")) if pdf_dir.is_dir() else sorted(theme_dir.glob("*.pdf"))
        for pdf in candidates:
            if _hidden(pdf) or not pdf.is_file():
                continue
            size = pdf.stat().st_size
            slug = pdf.stem
            title = _human_title(slug)
            rel = str(pdf.relative_to(_media_root()))
            url = f"/cours/{year}/{level_dir.name}/{theme_dir.name}/{slug}/"
            items.append(
                DocItem(
                    year=year,
                    institution=institution,
                    level=level_dir.name,
                    theme=theme_dir.name,
                    slug=slug,
                    title=title,
                    size_bytes=size,
                    pdf_rel_path=rel,
                    url=url,
                )
            )
    return items


@lru_cache(maxsize=1)
def build_index(version: str) -> List[DocItem]:
    """
    Indexe tous les PDF sous MEDIA_ROOT/documents, en gérant :
      - <year>/<level>/...
      - <year>/<institution>/<level>/...
    """

    base = _media_root() / "documents"
    items: List[DocItem] = []
    if not base.exists():
        return items
    for year_dir in sorted((p for p in base.iterdir() if p.is_dir() and not _hidden(p)), key=lambda p: p.name):
        year = year_dir.name
        for institution, level_dir in _iter_level_dirs(year_dir):
            items.extend(_collect_docs_under_level(year, institution, level_dir))
    return items


def index(request: HttpRequest) -> HttpResponse:
    """
    /cours/ : Années (desc) → Établissements → Niveaux (cliquables)
    """
    base = _media_root() / "documents"

    if not base.exists():  # garde-fou prod
        ctx = {
            "current_year_block": None,
            "archive_blocks": [],
            "debug": settings.DEBUG,
        }
        return render(request, "cours/index.html", ctx)

    # 1) Construire un dict year -> [(institution, [levels...]), ...]
    year_blocks: Dict[str, List[Tuple[str, List[str]]]] = {}
    for year_dir in (p for p in base.iterdir() if p.is_dir() and not _hidden(p)):
        year = year_dir.name
        inst_to_levels: Dict[str, set] = defaultdict(set)
        for institution, level_dir in _iter_level_dirs(year_dir):
            inst_to_levels[institution].add(level_dir.name)

        if inst_to_levels:
            inst_blocks = [(inst, sorted(levels)) for inst, levels in inst_to_levels.items()]
            # tri alphabétique des établissements pour stabilité
            inst_blocks.sort(key=lambda t: t[0].lower())
            year_blocks[year] = inst_blocks

    if not year_blocks:
        ctx = {
            "current_year_block": None,
            "archive_blocks": [],
            "debug": settings.DEBUG,
        }
        return render(request, "cours/index.html", ctx)

    # 2) Déterminer l'année scolaire courante
    cur_year = current_school_year()

    def year_start_int(y: str) -> int:
        try:
            return int(y.split("-")[0])
        except Exception:
            return -1  # met les années "non standard" en fin

    # 3) Construire le bloc "courant" (optionnel) et la liste "archives" (desc)
    current_year_block: Optional[Tuple[str, List[Tuple[str, List[str]]]]] = None
    if cur_year in year_blocks:
        current_year_block = (cur_year, year_blocks[cur_year])

    archive_blocks: List[Tuple[str, List[Tuple[str, List[str]]]]] = [
        (y, year_blocks[y])
        for y in sorted(year_blocks.keys(), key=year_start_int, reverse=True)
        if y != cur_year
    ]

    ctx = {
        "current_year_block": current_year_block,
        "archive_blocks": archive_blocks,
        "debug": settings.DEBUG,
    }
    return render(request, "cours/index.html", ctx)

def year_level(request: HttpRequest, year: str, level: str) -> HttpResponse:
    """
    /cours/<année>/<niveau>/ : Thèmes -> PDFs (tous établissements confondus)
    """
    # Filtrer l'index
    ver = version_token()
    docs = [it for it in build_index(ver) if it.year == year and it.level == level]
    if not docs:
        raise Http404("Aucun document pour cette année/niveau.")

    # Groupement par thème
    theme_map: Dict[str, List[DocItem]] = defaultdict(list)
    for it in docs:
        theme_map[it.theme].append(it)
    # tri interne par slug pour un rendu stable
    for th in theme_map:
        theme_map[th].sort(key=lambda d: d.slug)

    ctx = {
        "year": year,
        "level_dir": level,
        "theme_map": dict(sorted(theme_map.items(), key=lambda kv: kv[0])),
        "debug": settings.DEBUG,
    }
    return render(request, "cours/year_level.html", ctx)


def detail(request: HttpRequest, year: str, level: str, theme: str, slug: str) -> HttpResponse:
    """
    Page de détail d’un document : iframe + lien "ouvrir dans un nouvel onglet".
    On cherche sur l’ensemble des établissements (URL inchangée).
    """

    ver = version_token()
    match: Optional[DocItem] = next(
        (it for it in build_index(ver)
         if it.year == year and it.level == level and it.theme == theme and it.slug == slug),
        None
    )
    if not match:
        raise Http404("document introuvable")

    pdf_url = settings.MEDIA_URL + quote(match.pdf_rel_path, safe="/")
    ctx = {"doc": match, "pdf_url": pdf_url, "debug": settings.DEBUG}
    return render(request, "cours/detail.html", ctx)
