#!/usr/bin/env bash
set -Eeuo pipefail

echo "Starting UserService"

# Migrations are applied from committed files only. Never generate migrations
# during container startup because that makes deployments non-deterministic.
if [[ "${AUTO_MIGRATE:-true}" == "true" ]]; then
  python manage.py migrate --noinput
fi

if [[ "${CREATE_SUPERUSER:-false}" == "true" ]]; then
  : "${DJANGO_SUPERUSER_USERNAME:?DJANGO_SUPERUSER_USERNAME is required}"
  : "${DJANGO_SUPERUSER_EMAIL:?DJANGO_SUPERUSER_EMAIL is required}"
  : "${DJANGO_SUPERUSER_PASSWORD:?DJANGO_SUPERUSER_PASSWORD is required}"
  python manage.py shell <<'PY'
import os
from django.contrib.auth import get_user_model

User = get_user_model()
username = os.environ['DJANGO_SUPERUSER_USERNAME']
if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(
        username,
        os.environ['DJANGO_SUPERUSER_EMAIL'],
        os.environ['DJANGO_SUPERUSER_PASSWORD'],
    )
PY
fi

if [[ "${SEED_DATA:-false}" == "true" ]]; then
  python manage.py seed_data --users "${SEED_USERS:-10}"
fi

python manage.py collectstatic --noinput >/dev/null

python grpc_server.py &
GRPC_PID=$!
trap 'kill "$GRPC_PID" 2>/dev/null || true; wait "$GRPC_PID" 2>/dev/null || true' EXIT INT TERM

if [[ "${DEBUG:-true}" == "true" || "${DEBUG:-true}" == "True" ]]; then
  python manage.py runserver 0.0.0.0:8000 &
else
  gunicorn user_service.wsgi:application --bind 0.0.0.0:8000 --workers "${WEB_CONCURRENCY:-3}" --access-logfile - --error-logfile - &
fi
WEB_PID=$!

wait -n "$GRPC_PID" "$WEB_PID"
status=$?
kill "$GRPC_PID" "$WEB_PID" 2>/dev/null || true
wait "$GRPC_PID" "$WEB_PID" 2>/dev/null || true
exit "$status"
