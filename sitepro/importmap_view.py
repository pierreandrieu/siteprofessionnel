import json
from django.templatetags.static import static
from django.http import HttpResponse

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


def importmap_view(_request):
    data = {"imports": {k: static(v) for k, v in MODULES.items()}}
    resp = HttpResponse(json.dumps(data, separators=(",", ":")),
                        content_type="application/importmap+json")
    resp["Cache-Control"] = "no-store"  # en dev: toujours frais
    return resp
