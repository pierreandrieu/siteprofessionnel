from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Final, Iterable, List, Tuple, Optional
import re

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from urllib.parse import quote

from scripts.dev_publish_symlinks import dir_has_themes  # réutilisé
from sitepro.utils import current_school_year
from .docindex import version_token


@dataclass(frozen=True)
class DocItem:
    """
    Représente un document .pdf découvert sur le disque.

    Attributes
    ----------
    year : str
        Année scolaire (ex: "2024-2025").
    institution : str
        Nom du dossier établissement si présent (ex: "Lycée Jacques Prévert"), sinon "".
    level : str
        Nom du dossier niveau (ex: "NSI_1e").
    theme : str
        Nom du dossier thème (ex: "01_programmation_init").
    slug : str
        Base du nom de fichier sans extension (ex: "01_operateurs_python").
    title : str
        Titre humain (slug nettoyé et sans préfixe numérique).
    size_bytes : int
        Taille du PDF en octets.
    pdf_rel_path : str
        Chemin relatif à MEDIA_ROOT (ex: "documents/.../file.pdf").
    url : str
        URL Django de la page détail (ex: "/cours/2024-2025/NSI_1e/.../slug/").
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
    "nsi-premiere": "NSI_1e",
    "nsi-terminale": "NSI_Tle",
    "snt": "SNT",
    # Prépare les futurs niveaux Université (tu pourras renommer si besoin)
    "diu-nsi": "DIU_NSI",
    "m2-meef": "M2_MEEF",
}

# mapping inverse utile pour fabriquer des liens
LEVEL_DIR_TO_SLUG: Final[Dict[str, str]] = {v: k for k, v in LEVEL_SLUG_TO_DIR.items()}

# Préfixe numérique « 01_ », « 02- », « 10 » (1 à 3 chiffres + séparateur)
_INSTITUTION_PREFIX_RE: re.Pattern[str] = re.compile(r"^(\d{1,3})[ _-]+")
_NUM_PREFIX_RE: re.Pattern[str] = re.compile(r"^(\d{1,3})[ _-]")  # pour extraire NN du slug (01_, 2-, 105 )


# ---------------------------------------------------------------------------
# Helpers d’affichage et de FS
# ---------------------------------------------------------------------------

def _cle_tri_institution(nom: str) -> tuple[int, str]:
    """
    Clé de tri : (ordre numérique si présent, libellé pour ordre alpha).
    Les noms SANS préfixe sont envoyés en fin via un grand nombre sentinelle.
    """
    m = _INSTITUTION_PREFIX_RE.match(nom)
    if m:
        ordre: int = int(m.group(1))
        libelle_sans_prefixe: str = nom[m.end():]
        return ordre, libelle_sans_prefixe.lower()
    return 10 ** 6, nom.lower()


def _libelle_institution(nom: str) -> str:
    """Enlève le préfixe numérique pour l’affichage."""
    m = _INSTITUTION_PREFIX_RE.match(nom)
    return nom[m.end():] if m else nom


def _media_root() -> Path:
    """Racine MEDIA_ROOT en tant que Path."""
    return Path(settings.MEDIA_ROOT)


def _human_title(slug: str) -> str:
    """
    Transforme "01_operateurs_python" → "operateurs python".
    - enlève un éventuel préfixe numérique "01_", "02-"
    - remplace "_" par espaces
    """
    title: str = slug.replace("_", " ")
    if len(title) >= 3 and title[:3].isdigit():
        title = title[3:].lstrip(" _-")
    return title


def _hidden(p: Path) -> bool:
    """Renvoie True si le fichier/dossier est « caché » (commence par .)."""
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
    """
    Parcourt tous les thèmes du niveau pour fabriquer la liste des DocItem.
    """
    items: List[DocItem] = []
    for theme_dir in sorted((p for p in level_dir.iterdir() if p.is_dir() and not _hidden(p)), key=lambda p: p.name):
        pdf_dir: Path = theme_dir / "out"
        candidates: List[Path] = sorted(pdf_dir.glob("*.pdf")) if pdf_dir.is_dir() else sorted(theme_dir.glob("*.pdf"))
        for pdf in candidates:
            if _hidden(pdf) or not pdf.is_file():
                continue
            size: int = pdf.stat().st_size
            slug: str = pdf.stem
            title: str = _human_title(slug)
            rel: str = str(pdf.relative_to(_media_root()))
            url: str = f"/cours/{year}/{level_dir.name}/{theme_dir.name}/{slug}/"
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
    base: Path = _media_root() / "documents"
    items: List[DocItem] = []
    if not base.exists():
        return items
    for year_dir in sorted((p for p in base.iterdir() if p.is_dir() and not _hidden(p)), key=lambda p: p.name):
        year: str = year_dir.name
        for institution, level_dir in _iter_level_dirs(year_dir):
            items.extend(_collect_docs_under_level(year, institution, level_dir))
    return items


def _numero_depuis_slug(slug: str) -> Optional[str]:
    """
    Extrait le numéro initial (1 à 3 chiffres) d’un slug : "01_xxx", "2-yyy", "105_zzz".
    Retourne None si aucun préfixe numérique n’est présent.
    """
    m: Optional[re.Match[str]] = _NUM_PREFIX_RE.match(slug)
    return m.group(1) if m else None


def _lister_pieces_jointes(doc: DocItem) -> List[Dict[str, str]]:
    """
    Liste les fichiers à afficher en pièces jointes pour un document donné.

    Recherche sous MEDIA_ROOT/documents :
      - <year>/<institution>/<level>/<theme>/data/
      - (fallback) <year>/<level>/<theme>/data/  (ancien layout)

    Règles de collecte :
      - data/<NN>/...  où NN est le numéro extrait du slug (ex: "02" pour "02_modele_relationnel")
      - data/commun/...
    """
    roots: List[Path] = []
    base = _media_root() / "documents"

    # Layout « nouveau » avec établissement
    if doc.institution:
        roots.append(base / doc.year / doc.institution / doc.level / doc.theme)
    # Fallback « ancien » sans établissement
    roots.append(base / doc.year / doc.level / doc.theme)

    pieces: List[Dict[str, str]] = []
    num: Optional[str] = _numero_depuis_slug(doc.slug)

    for base_theme in roots:
        data_dir: Path = base_theme / "data"
        if not data_dir.is_dir():
            continue

        sous_dossiers: List[Path] = []
        if num:
            sous_dossiers.append(data_dir / num)
        sous_dossiers.append(data_dir / "commun")

        for sd in sous_dossiers:
            if not sd.is_dir():
                continue
            for f in sorted(sd.rglob("*")):
                if f.is_dir() or _hidden(f):
                    continue
                rel: str = f.relative_to(_media_root()).as_posix()
                try:
                    size: int = f.stat().st_size
                except OSError:
                    size = 0
                pieces.append(
                    {
                        "name": f.name,
                        "rel_path": rel,
                        "url": settings.MEDIA_URL + quote(rel, safe="/"),
                        "size": str(size),
                    }
                )

        # si on a trouvé des pièces dans le layout avec établissement, inutile de continuer
        if pieces and doc.institution:
            break

    return pieces


# ---------------------------------------------------------------------------
# Vues
# ---------------------------------------------------------------------------

def index(request: HttpRequest) -> HttpResponse:
    """
    /cours/ : Années (desc) → Établissements → Niveaux (cliquables)
    """
    base: Path = _media_root() / "documents"

    if not base.exists():  # garde-fou prod
        ctx: Dict[str, object] = {
            "current_year_block": None,
            "archive_blocks": [],
            "debug": settings.DEBUG,
        }
        return render(request, "cours/index.html", ctx)

    # 1) Construire un dict year -> [(institution, [levels...]), ...]
    year_blocks: Dict[str, List[Tuple[str, List[str]]]] = {}
    for year_dir in (p for p in base.iterdir() if p.is_dir() and not _hidden(p)):
        year: str = year_dir.name
        inst_to_levels: Dict[str, set] = defaultdict(set)

        for institution, level_dir in _iter_level_dirs(year_dir):
            inst_to_levels[institution].add(level_dir.name)

        if inst_to_levels:
            # On construit des triples (nom_brut, libellé_affiché, niveaux)
            triples: List[Tuple[str, str, List[str]]] = [
                (inst, _libelle_institution(inst), sorted(levels))
                for inst, levels in inst_to_levels.items()
            ]
            # Tri par clé "intuitive" : préfixe numérique si présent, sinon alpha
            triples.sort(key=lambda t: _cle_tri_institution(t[0]))
            # On n’expose au template que (libellé_affiché, niveaux)
            inst_blocks: List[Tuple[str, List[str]]] = [(t[1], t[2]) for t in triples]

            year_blocks[year] = inst_blocks

    if not year_blocks:
        ctx: Dict[str, object] = {
            "current_year_block": None,
            "archive_blocks": [],
            "debug": settings.DEBUG,
        }
        return render(request, "cours/index.html", ctx)

    # 2) Déterminer l'année scolaire courante
    cur_year: str = current_school_year()

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

    ctx: Dict[str, object] = {
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
    ver: str = version_token()
    docs: List[DocItem] = [it for it in build_index(ver) if it.year == year and it.level == level]
    if not docs:
        raise Http404("Aucun document pour cette année/niveau.")

    # Groupement par thème
    theme_map: Dict[str, List[DocItem]] = defaultdict(list)
    for it in docs:
        theme_map[it.theme].append(it)
    # tri interne par slug pour un rendu stable
    for th in theme_map:
        theme_map[th].sort(key=lambda d: d.slug)

    ctx: Dict[str, object] = {
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
    Détecte et liste également les pièces jointes sous data/<NN>/ et data/commun/.
    """
    ver: str = version_token()
    match: Optional[DocItem] = next(
        (it for it in build_index(ver)
         if it.year == year and it.level == level and it.theme == theme and it.slug == slug),
        None
    )
    if not match:
        raise Http404("document introuvable")

    pdf_url: str = settings.MEDIA_URL + quote(match.pdf_rel_path, safe="/")
    attachments: List[Dict[str, str]] = _lister_pieces_jointes(match)

    ctx: Dict[str, object] = {
        "doc": match,
        "pdf_url": pdf_url,
        "attachments": attachments,
        "debug": settings.DEBUG,
    }
    return render(request, "cours/detail.html", ctx)
