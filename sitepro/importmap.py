import os
import re
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.cache import cache_page
from django.contrib.staticfiles.storage import staticfiles_storage

_RE_HASH_JS = re.compile(r"^(?P<basename>.+?)\.[0-9a-f]{8,}\.js$")  # foo.<hash>.js


def _list_js(subdir: str):
    root = settings.STATIC_ROOT
    path = os.path.join(root, subdir)
    try:
        return [f for f in os.listdir(path) if f.endswith(".js")]
    except FileNotFoundError:
        return []


def _build_scope(prefix: str):
    """
    Mappe './state.js' -> URL hashée servie par Django (via Manifest).
    """
    files = _list_js(prefix)
    scope = {}
    for fname in files:
        m = _RE_HASH_JS.match(fname)
        if not m:
            continue
        basename = m.group('basename')         # ex: "importers"
        key = f"./{basename}.js"               # spec ESM côté app
        original = f"{prefix}/{basename}.js"   # **nom source non-hashé**
        url = staticfiles_storage.url(original)  # Django renvoie /.../<hash>.js
        scope[key] = url
    return scope


@cache_page(60)
def importmap_view(request):
    scope = _build_scope("plandeclasse/js")
    data = {
        "imports": {},
        "scopes": {
            "/static/plandeclasse/js/": scope
        },
    }
    return JsonResponse(data, content_type="application/importmap+json")
