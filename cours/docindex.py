from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict, List, TypedDict
import re

from django.conf import settings


class DocumentItem(TypedDict):
    name: str
    slug: str
    rel_path: str
    size: int


ThemeMap = Dict[str, List[DocumentItem]]
LevelMap = Dict[str, ThemeMap]
ArchiveTree = Dict[str, LevelMap]

_PREFIX_RE = re.compile(r"^\d+[\-_]\s*")
_VERSION_FILE: Path = Path(settings.MEDIA_ROOT) / "documents" / ".v"


def prettify(name: str) -> str:
    base = name.rsplit(".", 1)[0]
    base = _PREFIX_RE.sub("", base)
    base = base.replace("_", " ").replace("-", " ").strip()
    return base


def version_token() -> str:
    try:
        return _VERSION_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return "0"


def _dir_has_themes(level_dir: Path) -> bool:
    try:
        for th in level_dir.iterdir():
            if not th.is_dir():
                continue
            out_dir = th / "out"
            if out_dir.is_dir() and any(out_dir.glob("*.pdf")):
                return True
            if any(th.glob("*.pdf")):
                return True
    except OSError:
        return False
    return False


@lru_cache(maxsize=8)
def scan(version: str) -> ArchiveTree:
    """
    Construit {année: {niveau: {thème: [DocumentItem...]}}}
    en supportant :
      - <year>/<level>/<theme>/out/*.pdf
      - <year>/<institution>/<level>/<theme>/out/*.pdf
    """
    base: Path = Path(settings.MEDIA_ROOT) / "documents"
    archives: ArchiveTree = {}
    if not base.exists():
        return archives

    for year_dir in sorted((p for p in base.iterdir() if p.is_dir()), key=lambda p: p.name, reverse=True):
        levels: LevelMap = {}

        for first in sorted((p for p in year_dir.iterdir() if p.is_dir()), key=lambda p: p.name):
            level_dirs: List[Path] = []
            if _dir_has_themes(first):
                level_dirs.append(first)  # ancien layout
            else:
                try:
                    for lvl in sorted((p for p in first.iterdir() if p.is_dir()), key=lambda p: p.name):
                        if _dir_has_themes(lvl):
                            level_dirs.append(lvl)  # nouveau layout
                except OSError:
                    pass

            for lvl_dir in level_dirs:
                themes: ThemeMap = levels.setdefault(lvl_dir.name, {})

                try:
                    for th_dir in sorted((p for p in lvl_dir.iterdir() if p.is_dir()), key=lambda p: p.name):
                        items: List[DocumentItem] = []
                        pdf_root = th_dir / "out" if (th_dir / "out").is_dir() else th_dir
                        for f in sorted(pdf_root.glob("*.pdf"), key=lambda p: p.name):
                            if not f.is_file():
                                continue
                            rel_path = f.relative_to(base).as_posix()
                            try:
                                size = f.stat().st_size
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
                except OSError:
                    continue

        if levels:
            archives[year_dir.name] = levels

    return archives


def prewarm() -> None:
    try:
        scan(version_token())
    except Exception:
        pass
