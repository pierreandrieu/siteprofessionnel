from django.urls import path
from . import views

app_name = "plandeclasse"

urlpatterns = [
    # Page principale (UI côté client)
    path("", views.index, name="index"),

    # Petite sonde de santé (pratique pour Nginx / monitoring)
    path("sante", views.sante, name="sante"),

    # === BORNES JSON FACULTATIVES (DEV uniquement ; en mémoire) =========================
    # POST /plandeclasse/demandes/     → crée une “demande de résolution” (factice)
    # GET  /plandeclasse/demandes/<uuid>/ → statut/résultat de la demande (factice)
    path("demandes/", views.demande_creer, name="demande_creer"),
    path("demandes/<uuid:demande_id>/", views.demande_statut, name="demande_statut"),
]
