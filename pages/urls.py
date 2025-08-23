from __future__ import annotations
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, re_path
from . import views


app_name: str = "pages"

urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    # index unique "documents"
    path("documents/", views.documents, name="documents"),
    # détail d'un document (on accepte lettres/chiffres/_/- dans level/theme/slug)
    re_path(
        r"^documents/(?P<year>\d{4}-\d{4})/(?P<level>[-A-Za-z0-9_]+)/(?P<theme>[-A-Za-z0-9_]+)/(?P<slug>[-A-Za-z0-9_]+)/$",
        views.document_detail,
        name="document_detail",
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)