# comments in French
from __future__ import annotations

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path
from django.views.generic import TemplateView

from sitepro.views import importmap_json


def healthz(_request) -> HttpResponse:
    """endpoint très simple pour les sondes de liveness."""
    return HttpResponse("ok", content_type="text/plain")

urlpatterns = [
    # admin django (chemin obscurci déjà en place si tu le souhaites)
    path("super-portal-f0b2b3/", admin.site.urls),

    # pages vitrines (accueil, à-propos, etc.)
    path("", include(("pages.urls", "pages"), namespace="pages")),

    # app cours (index, par niveau, détail)
    path("cours/", include(("cours.urls", "cours"), namespace="cours")),

    path("plandeclasse/", include(("plandeclasse.urls", "plandeclasse"), namespace="plandeclasse")),

    path(
        "robots.txt",
        TemplateView.as_view(template_name="pages/robots.txt", content_type="text/plain"),
        name="robots_txt",
    ),
    path("healthz", healthz),
    path("importmap.json", importmap_json, name="importmap"),

]

# en dev seulement : servir les fichiers media via django
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
