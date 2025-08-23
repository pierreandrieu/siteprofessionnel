# sitepro/logging_filters.py
from __future__ import annotations
import logging
from django.core.exceptions import DisallowedHost


class IgnoreDisallowedHost(logging.Filter):
    """Filtre qui ignore les exceptions DisallowedHost (Host non autorisé)."""

    def filter(self, record: logging.LogRecord) -> bool:
        exc = record.exc_info
        return not (exc and isinstance(exc[1], DisallowedHost))
