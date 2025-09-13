import json
from .importmap import _build_scope
from django.templatetags.static import static

from cours.views import current_school_year

MODULES = {
    "plandeclasse/index": "plandeclasse/js/plandeclasse.js",
    "plandeclasse/state": "plandeclasse/js/state.js",
    "plandeclasse/utils": "plandeclasse/js/utils.js",
    "plandeclasse/render": "plandeclasse/js/render.js",
    "plandeclasse/constraints": "plandeclasse/js/constraints.js",
    "plandeclasse/interactions": "plandeclasse/js/interactions.js",
    "plandeclasse/schema": "plandeclasse/js/schema.js",
    "plandeclasse/export": "plandeclasse/js/export.js",
    "plandeclasse/importers": "plandeclasse/js/importers.js",
    "plandeclasse/csv": "plandeclasse/js/csv.js",
    "plandeclasse/solver": "plandeclasse/js/solver.js",
}


def school_year(request):
    return {"cur_year": current_school_year()}


def csp_nonce(request):
    return {"csp_nonce": getattr(request, "csp_nonce", "")}



def importmap_json(_request):
    imports = {k: static(v) for k, v in MODULES.items()}  # renvoie les chemins fingerprintés après collectstatic
    data = {"imports": imports}
    return {"importmap_json": json.dumps(data, separators=(",", ":"))}
