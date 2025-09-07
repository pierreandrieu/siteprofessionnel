import json
from .importmap import _build_scope

from cours.views import current_school_year


def school_year(request):
    return {"cur_year": current_school_year()}


def csp_nonce(request):
    return {"csp_nonce": getattr(request, "csp_nonce", "")}


def importmap_json(_request):
    scope = _build_scope("plandeclasse/js")
    data = {
        "imports": {},
        "scopes": {
            "/static/plandeclasse/js/": scope,
        },
    }
    # compact pour réduire la taille
    return {"importmap_json": json.dumps(data, separators=(",", ":"))}
