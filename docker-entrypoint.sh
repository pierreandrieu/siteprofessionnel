#!/usr/bin/env bash
set -euo pipefail

# Default to dev settings if nothing is specified (useful locally).
# In production, ENVIRONMENT=production is set to enforce the check below.
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-sitepro.settings.dev}"

# Fail fast if looks like production but not using production settings.
if [[ "${ENVIRONMENT:-}" == "production" && "${DJANGO_SETTINGS_MODULE}" != "sitepro.settings.prod" ]]; then
  echo "Refusing to start: ENVIRONMENT=production but DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE}" >&2
  exit 1
fi

if [[ "${RUN_MIGRATIONS:-1}" == "1" ]]; then
  python manage.py migrate --noinput
fi

if [[ "${RUN_COLLECTSTATIC:-1}" == "1" ]]; then
  python manage.py collectstatic --noinput
fi

exec "$@"
