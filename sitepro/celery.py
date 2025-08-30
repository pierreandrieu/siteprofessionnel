import os
from celery import Celery

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    os.environ.get("DJANGO_SETTINGS_MODULE", "sitepro.settings.dev")
)

app = Celery("sitepro")  # pas "proj"
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()