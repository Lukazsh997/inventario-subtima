#!/bin/sh
# Ponto de entrada do container. Uso: web | scheduler | backup [rótulo] | restore <arquivo> | manage <comando>
set -eu

cd /app/src
export PGPASSWORD="${DB_PASSWORD:-}"
PG="-h ${DB_HOST:-db} -p ${DB_PORT:-5432} -U ${DB_USER:-patrimonio}"

wait_for_db() {
  tries=0
  until pg_isready $PG -d "${DB_NAME:-patrimonio}" -q; do
    tries=$((tries + 1))
    if [ "$tries" -ge 60 ]; then
      echo "Banco de dados indisponível após 120 s" >&2
      exit 1
    fi
    sleep 2
  done
}

database_initialized() {
  [ "$(psql $PG -d "${DB_NAME:-patrimonio}" -tAc "SELECT to_regclass('public.django_migrations') IS NOT NULL")" = "t" ]
}

case "${1:-web}" in
  web)
    wait_for_db
    if database_initialized && ! python manage.py migrate --check >/dev/null 2>&1; then
      echo "Migrações pendentes: gerando backup de segurança antes de aplicá-las"
      /app/scripts/backup.sh pre-migracao
    fi
    python manage.py migrate --noinput
    python manage.py ensure_admin
    exec gunicorn config.wsgi:application \
      --bind 0.0.0.0:8000 \
      --workers "${GUNICORN_WORKERS:-3}" \
      --timeout "${GUNICORN_TIMEOUT:-60}" \
      --access-logfile - \
      --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-127.0.0.1}"
    ;;
  scheduler)
    wait_for_db
    exec python manage.py run_scheduler
    ;;
  backup)
    wait_for_db
    exec /app/scripts/backup.sh "${2:-manual}"
    ;;
  restore)
    wait_for_db
    exec /app/scripts/restore.sh "${2:-}" "${3:-}"
    ;;
  manage)
    shift
    exec python manage.py "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
