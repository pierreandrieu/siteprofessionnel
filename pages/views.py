from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, List, Optional
from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
import re
import markdown

from .docindex import scan, version_token, DocumentItem, ArchiveTree, prettify


def home(request: HttpRequest) -> HttpResponse:
    """
    Render the public homepage.
    """
    return render(request, "pages/home.html")


def about(request: HttpRequest) -> HttpResponse:
    """
    Render a simple 'about' page (professional profile).
    """
    return render(request, "pages/about.html")


def _rewrite_md_relative_urls(md_text: str, base_url: str) -> str:
    """
    Réécrit les URLs *relatives* dans le markdown pour qu'elles pointent
    vers le bon préfixe absolu (ex: /media/documents/.../exos_web_md/).

    - On cible à la fois les liens images ![...](...) et les liens [...](...).
    - Si l'URL commence par 'http', '/', 'data:' ou '#', on NE touche pas.
    - Sinon, on préfixe par base_url (avec un slash si besoin).

    :param md_text: Contenu markdown original.
    :param base_url: Préfixe absolu (terminé par '/') pour les ressources.
    :return: Markdown avec URLs relatives réécrites.
    """
    pattern = re.compile(r'(!?\[[^\]]*\]\()(?P<url>[^)]+)(\))')

    def _sub(m: re.Match) -> str:
        url = m.group('url').strip()
        lower = url.lower()
        if lower.startswith(('http://', 'https://', '/', 'data:', '#')):
            return m.group(0)
        # chemin relatif → on le colle derrière base_url
        sep = '' if base_url.endswith('/') else '/'
        return f"{m.group(1)}{base_url}{sep}{url}{m.group(3)}"

    return pattern.sub(_sub, md_text)


def _render_md_bundle(md_dir: Path, media_prefix: str, slug: str) -> str:
    """
    Rend un *bundle* de markdown en HTML.

    Règles :
    - si <md_dir>/<slug>.md existe → on rend ce fichier unique ;
    - sinon on prend *tous* les .md de <md_dir> (triés) et on les concatène,
      en insérant un petit titre basé sur le nom de fichier.

    On réécrit au passage les chemins relatifs (images, liens) pour viser
    le préfixe absolu /media fourni.

    :param md_dir: Dossier 'exos_web_md' publié sous MEDIA_ROOT.
    :param media_prefix: URL absolue vers ce dossier (ex: /media/documents/.../exos_web_md/).
    :param slug: Slug du cours (sert à cibler <slug>.md si présent).
    :return: HTML rendu (string) prêt à injecter dans le template.
    """
    parts: List[str] = []

    def _compile_one(md_path: Path, with_heading: bool) -> None:
        # lecture du fichier
        raw = md_path.read_text(encoding="utf-8")
        # réécriture des URLs relatives → /media/...
        raw = _rewrite_md_relative_urls(raw, media_prefix)
        # rendu HTML
        html = markdown.markdown(
            raw,
            extensions=["extra", "fenced_code", "tables", "attr_list", "sane_lists"],
            output_format="html",
        )
        if with_heading:
            title = prettify(md_path.stem)
            parts.append(f'<h3 class="h5 mt-4">{title}</h3>')
        parts.append(html)

    if not md_dir.exists():
        return ""

    # cas 1 : fichier précis "<slug>.md"
    main_md = md_dir / f"{slug}.md"
    if main_md.exists():
        _compile_one(main_md, with_heading=False)
        return "\n".join(parts)

    # cas 2 : tous les .md du dossier (triés)
    md_files = sorted(md_dir.glob("*.md"))
    if not md_files:
        return ""

    for p in md_files:
        _compile_one(p, with_heading=True)

    # petite séparation finale
    parts.append('<hr class="my-4">')
    return "\n".join(parts)


def documents(request: HttpRequest) -> HttpResponse:
    """
    Affiche l'index des documents (liste hiérarchique année → niveau → thème).
    L'arborescence provient d'un scan disque mis en cache (LRU).

    :param request: Requête HTTP Django.
    :return: Réponse HTML avec la liste des documents.
    """
    archives: ArchiveTree = scan(version_token())
    context: Dict[str, Any] = {"archives": archives}
    return render(request, "pages/documents.html", context)


def document_detail(request: HttpRequest, year: str, level: str, theme: str, slug: str) -> HttpResponse:
    """
    Affiche la page détaillée d'un document :
    - PDF intégré dans un cadre scrollable (iframe)
    - contenu complémentaire en markdown (facultatif)

    Le PDF est recherché dans l'arbre scanné (cache LRU), pour éviter de toucher
    le disque pendant une requête.

    :param request: Requête HTTP.
    :param year: Année au format "YYYY-YYYY" (ex: "2025-2026").
    :param level: Dossier de niveau (ex: "NSI_premiere").
    :param theme: Dossier de thème (ex: "01_programmation_init").
    :param slug: Nom technique du PDF (nom de fichier sans l'extension .pdf).
    :raises Http404: Si le document n'est pas trouvé.
    :return: Réponse HTML avec iframe PDF + markdown.
    """
    archives: ArchiveTree = scan(version_token())

    levels = archives.get(year) or {}
    themes = levels.get(level) or {}
    files: List[DocumentItem] = themes.get(theme) or []

    item: Optional[DocumentItem] = next((f for f in files if f["slug"] == slug), None)
    if item is None:
        raise Http404("document introuvable")

    # URL absolue du PDF côté /media/, sans requête disque ici
    pdf_url: str = f'{settings.MEDIA_URL}documents/{item["rel_path"]}'

    # Recherche du markdown complémentaire (fichier optionnel sur le disque)
    md_path: Path = Path(settings.BASE_DIR) / "content" / "documents" / year / level / theme / f"{slug}.md"
    md_html: str = ""
    if md_path.exists():
        md_html = markdown.markdown(
            md_path.read_text(encoding="utf-8"),
            extensions=["extra", "fenced_code", "tables", "attr_list", "sane_lists"],
            output_format="html",
        )

    context: Dict[str, Any] = {
        "title": item["name"],
        "year": year,
        "level": level,
        "theme": prettify(theme),
        "pdf_url": pdf_url,
        "md_html": md_html,
    }
    return render(request, "pages/document_detail.html", context)