from django.http import JsonResponse
from django.conf import settings
from django.templatetags.static import static


def importmap_json(_request):
    """Import map externe pour remapper les imports relatifs ESM vers les URLs fingerprintées."""
    # base de portée : tous les modules situés sous /static/plandeclasse/js/
    portee = settings.STATIC_URL.rstrip("/") + "/plandeclasse/js/"

    # remapping : specifier relatif -> URL statique hashée
    mappage = {
        "./state.js": static("plandeclasse/js/state.js"),
        "./utils.js": static("plandeclasse/js/utils.js"),
        "./render.js": static("plandeclasse/js/render.js"),
        "./constraints.js": static("plandeclasse/js/constraints.js"),
        "./interactions.js": static("plandeclasse/js/interactions.js"),
        "./schema.js": static("plandeclasse/js/schema.js"),
        "./csv.js": static("plandeclasse/js/csv.js"),
        "./export.js": static("plandeclasse/js/export.js"),
        "./importers.js": static("plandeclasse/js/importers.js"),
        "./solver.js": static("plandeclasse/js/solver.js"),
    }

    data = {"scopes": {portee: mappage}}
    resp = JsonResponse(data)
    # type conseillé par la spec (les navigateurs tolèrent aussi application/json)
    resp["Content-Type"] = "application/importmap+json"
    # on évite un cache collant du mapping
    resp["Cache-Control"] = "no-store"
    return resp
