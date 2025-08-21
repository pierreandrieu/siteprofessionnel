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

RUN_MIGRATIONS="${RUN_MIGRATIONS:-1}"
RUN_COLLECTSTATIC="${RUN_COLLECTSTATIC:-1}"

if [ "$RUN_MIGRATIONS" = "1" ]; then
  python manage.py migrate --noinput
fi
if [ "$RUN_COLLECTSTATIC" = "1" ]; then
  python manage.py collectstatic --noinput
fi

# Only run the deployment checklist in production
if [ "${ENVIRONMENT:-}" = "production" ]; then
  # Hard-fail if prod without a real secret key
  if [ -z "${DJANGO_SECRET_KEY:-}" ] || [ "${DJANGO_SECRET_KEY}" = "dev-only-change-me" ]; then
    echo "Missing/unsafe DJANGO_SECRET_KEY in production. Aborting." >&2
    exit 1
  fi
  python manage.py check --deploy
fi

exec "$@"
