#!/bin/sh
# Restaura banco e arquivos a partir de um backup gerado por backup.sh.
# Uso: restore.sh <arquivo.tar | nome do arquivo em $BACKUP_DIR> --sim
# Antes de restaurar, gera automaticamente um backup "pre-restauracao" do estado atual.
set -eu

FILE="${1:-}"
CONFIRM="${2:-}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
DATA_DIR="${DATA_DIR:-/data}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -z "$FILE" ]; then
  echo "Informe o arquivo de backup. Disponíveis:" >&2
  ls -1t "$BACKUP_DIR"/patrimonio-*.tar 2>/dev/null >&2 || echo "(nenhum)" >&2
  exit 2
fi
[ -f "$FILE" ] || FILE="${BACKUP_DIR}/${FILE}"
[ -f "$FILE" ] || { echo "Arquivo não encontrado: $FILE" >&2; exit 2; }

if [ "$CONFIRM" != "--sim" ]; then
  echo "ATENÇÃO: a restauração substitui TODOS os dados atuais por $FILE." >&2
  echo "Pare o serviço 'app' e repita o comando acrescentando --sim para confirmar." >&2
  exit 3
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
tar -C "$WORK" -xf "$FILE"
( cd "$WORK" && sha256sum -c SHA256SUMS ) || { echo "Backup corrompido: checksum não confere" >&2; exit 4; }

echo "Gerando backup de segurança do estado atual..."
"$SCRIPT_DIR/backup.sh" pre-restauracao

export PGPASSWORD="${DB_PASSWORD:-}"
PG_ARGS="-h ${DB_HOST:-db} -p ${DB_PORT:-5432} -U ${DB_USER:-patrimonio} -d ${DB_NAME:-patrimonio}"

echo "Restaurando banco de dados..."
# shellcheck disable=SC2086
pg_restore $PG_ARGS --clean --if-exists --no-owner --single-transaction --exit-on-error "$WORK/database.dump"

echo "Restaurando arquivos..."
mkdir -p "${DATA_DIR}/media"
find "${DATA_DIR}/media" -mindepth 1 -delete
tar -C "${DATA_DIR}/media" -xzf "$WORK/media.tar.gz"

echo "Restauração concluída a partir de $FILE"
