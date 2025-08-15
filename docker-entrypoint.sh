#!/usr/bin/env bash
set -euo pipefail

# Ensure settings are defined; production must set prod module.
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-sitepro.settings.dev}"

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec "$@"
