#!/bin/sh
# Gera um backup completo: banco (pg_dump, formato custom) + arquivos do volume de dados.
# Saída: $BACKUP_DIR/patrimonio-AAAAMMDD-HHMMSS-<rótulo>.tar
set -eu

LABEL="${1:-manual}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
DATA_DIR="${DATA_DIR:-/data}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
STAMP="$(date +%Y%m%d-%H%M%S)"
NAME="patrimonio-${STAMP}-${LABEL}"
WORK="${BACKUP_DIR}/.${NAME}.tmp"

export PGPASSWORD="${DB_PASSWORD:-}"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

mkdir -p "$WORK" "${DATA_DIR}/media"

pg_dump -h "${DB_HOST:-db}" -p "${DB_PORT:-5432}" -U "${DB_USER:-patrimonio}" -d "${DB_NAME:-patrimonio}" \
  --format=custom --no-owner --file "$WORK/database.dump"
tar -C "${DATA_DIR}/media" -czf "$WORK/media.tar.gz" .
{
  echo "sistema=patrimonio-ti"
  echo "versao=${APP_VERSION:-desconhecida}"
  echo "data=$(date -Iseconds)"
  echo "rotulo=${LABEL}"
} > "$WORK/info.txt"
( cd "$WORK" && sha256sum database.dump media.tar.gz > SHA256SUMS )

tar -C "$WORK" -cf "${BACKUP_DIR}/${NAME}.tar.partial" .
mv "${BACKUP_DIR}/${NAME}.tar.partial" "${BACKUP_DIR}/${NAME}.tar"

# Retenção: remove backups automáticos mais antigos que o prazo (os manuais também entram na regra).
find "$BACKUP_DIR" -maxdepth 1 -name 'patrimonio-*.tar' -mtime +"$RETENTION_DAYS" -print -delete

echo "${BACKUP_DIR}/${NAME}.tar"
