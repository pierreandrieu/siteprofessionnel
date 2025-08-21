from .base import *
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env.dev into process env for local development only.
load_dotenv(Path(BASE_DIR) / ".env.dev")


DEBUG = True
ALLOWED_HOSTS = []

SEND_REAL = os.getenv("SEND_REAL_EMAILS", "0") == "1"


if SEND_REAL:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.getenv("EMAIL_HOST", "")
    EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() == "true"
    EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "false").lower() == "true"

else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"


# From identities in dev (safe defaults)
SERVER_EMAIL = os.getenv("SERVER_EMAIL", "django@pierreandrieu.fr")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "noreply-dev@pierreandrieu.fr")
