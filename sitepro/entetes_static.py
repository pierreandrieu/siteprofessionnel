# sitepro/entetes_static.py
import re

_RE_HASH = re.compile(r"\.[0-9a-f]{8,}\.")  # ex: fichier.55e7cbb9ba48.js


def ajouter_entetes(headers, path, url):
    """Force no-store sur les JS non fingerprintés de plandeclasse."""
    if url.startswith("/static/plandeclasse/js/") and url.endswith(".js") and not _RE_HASH.search(url):
        headers["Cache-Control"] = "no-store"
