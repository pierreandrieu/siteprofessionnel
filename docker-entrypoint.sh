#!/usr/bin/env bash
set -euo pipefail

# Ensure files are created with sane perms (e.g., 0644 / 0755).
umask "${UMASK:-0022}"   # comments in English

# Default to dev settings if nothing is specified (useful locally).
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

if [ "${ENVIRONMENT:-}" = "production" ]; then
  if [ -z "${DJANGO_SECRET_KEY:-}" ] || [ "${DJANGO_SECRET_KEY}" = "dev-only-change-me" ]; then
    echo "Missing/unsafe DJANGO_SECRET_KEY in production. Aborting." >&2
    exit 1
  fi
  python manage.py check --deploy
fi

exec "$@"
