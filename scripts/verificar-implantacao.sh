#!/bin/sh
# Teste de implantação e persistência — roda NO SERVIDOR, na pasta do docker-compose.yml.
#
#   sh scripts/verificar-implantacao.sh            # verificação + backup + recriação dos containers
#   sh scripts/verificar-implantacao.sh --rapido   # só a verificação (não para o sistema)
#
# A recriação usa "docker compose down" SEM -v: os volumes são mantidos. O sistema fica
# fora do ar por cerca de 1 minuto; rode fora do horário de uso.
set -eu

DC="${DC:-docker compose}"
MANAGE="$DC exec -T app python manage.py"

wait_healthy() {
  echo "Aguardando o app ficar saudável..."
  i=0
  while [ "$i" -lt 60 ]; do
    if $DC exec -T app python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/', timeout=5).status == 200 else 1)" 2>/dev/null; then
      echo "App saudável."
      return 0
    fi
    i=$((i + 1)); sleep 5
  done
  echo "O app não ficou saudável em 5 minutos. Veja: $DC logs app" >&2
  exit 1
}

echo "== 1. Verificação da implantação"
wait_healthy
$MANAGE verificar_implantacao || true

[ "${1:-}" = "--rapido" ] && exit 0

echo "== 2. Backup de segurança antes do teste"
$DC exec -T app /app/docker/entrypoint.sh backup verificacao

echo "== 3. Instantâneo dos dados"
SNAP="$($MANAGE verificar_implantacao --json)"
echo "$SNAP"

echo "== 4. Recriando os containers (volumes mantidos)"
$DC down
$DC up -d
wait_healthy

echo "== 5. Conferindo se nada se perdeu"
echo "$SNAP" | $MANAGE verificar_implantacao --comparar -
$MANAGE verificar_implantacao
echo "Teste de persistência concluído com sucesso."
