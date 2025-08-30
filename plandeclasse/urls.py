from django.urls import path
from . import views

app_name = "plandeclasse"

urlpatterns = [
    path("", views.index, name="index"),
    path("sante", views.sante, name="sante"),
    path("demande/creer", views.demande_creer, name="demande_creer"),
    path("demande/statut/<uuid:demande_id>", views.demande_statut, name="demande_statut"),
    path("solve/start", views.solve_start, name="solve_start"),
    path("solve/status/<str:task_id>", views.solve_status, name="solve_status"),
    path("download/<str:token>/<str:fmt>", views.download_artifact, name="download_artifact"),
    path("export", views.export_plan, name="export_plan"),  # <-- nouveau
]