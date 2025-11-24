# comments in French
from __future__ import annotations

from django.urls import path
from . import views

app_name = "pages"

urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("vie-privee-hebergement/", views.privacy, name="privacy"),
    path("initiatives/", views.initiatives, name="initiatives"),
    path("contact/", views.contact, name="contact"),
]
