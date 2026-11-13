# Imagem do Sistema de Patrimônio e Estoque de TI
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Cliente PostgreSQL 17 (pg_dump/pg_restore na mesma versão do banco), tini como init e
# bibliotecas/fontes do WeasyPrint (PDF). Liberation, Carlito e Caladea têm as mesmas
# métricas de Arial/Times, Calibri e Cambria, usadas nos modelos do órgão.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg tini \
 && install -d /usr/share/postgresql-common/pgdg \
 && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
      -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
 && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client-17 \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
      fonts-liberation2 fonts-dejavu-core fonts-crosextra-carlito fonts-crosextra-caladea \
 && apt-get purge -y gnupg curl && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src/ /app/src/
COPY scripts/ /app/scripts/
COPY docker/entrypoint.sh /app/docker/entrypoint.sh

RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin app \
 && mkdir -p /data/media /data/logs /backups \
 && chown -R app:app /data /backups \
 && chmod +x /app/docker/entrypoint.sh /app/scripts/*.sh

WORKDIR /app/src
RUN DEBUG=false SECRET_KEY=build-only LOG_TO_FILE=false python manage.py collectstatic --noinput

ARG APP_VERSION=0.3.0
ENV APP_VERSION=${APP_VERSION} \
    DATA_DIR=/data \
    BACKUP_DIR=/backups

USER app
EXPOSE 8000
VOLUME ["/data", "/backups"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/', timeout=8).status == 200 else 1)"

ENTRYPOINT ["tini", "--", "/app/docker/entrypoint.sh"]
CMD ["web"]
