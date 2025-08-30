# plandeclasse/apps.py
from django.apps import AppConfig


class PlandeclasseConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "plandeclasse"

    def ready(self):
        from .contraintes import enregistrement
