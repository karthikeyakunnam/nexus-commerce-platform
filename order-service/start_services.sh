#!/usr/bin/env bash
set -Eeuo pipefail

echo "Starting OrderService"

if [[ "${AUTO_MIGRATE:-true}" == "true" ]]; then
  python manage.py migrate --noinput
fi

if [[ "${SEED_DATA:-false}" == "true" ]]; then
  python manage.py seed_data --orders "${SEED_ORDERS:-30}"
fi

python manage.py collectstatic --noinput >/dev/null

if [[ "${DEBUG:-true}" == "true" || "${DEBUG:-true}" == "True" ]]; then
  python manage.py runserver 0.0.0.0:8000
else
  exec gunicorn order_service.wsgi:application --bind 0.0.0.0:8000 --workers "${WEB_CONCURRENCY:-3}" --access-logfile - --error-logfile -
fi
