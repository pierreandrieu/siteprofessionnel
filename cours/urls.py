# cours/urls.py
from django.urls import path, re_path
from . import views

app_name = "cours"

urlpatterns = [
    path("", views.index, name="index"),
    path("<str:year>/<str:level>/", views.year_level, name="year_level"),
    re_path(
        r"^(?P<year>\d{4}-\d{4})/(?P<level>[-A-Za-z0-9_]+)/(?P<theme>[-A-Za-z0-9_]+)/(?P<slug>[-A-Za-z0-9_]+)/$",
        views.detail,
        name="detail",
    ),
]
