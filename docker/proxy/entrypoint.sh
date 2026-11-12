#!/bin/sh
# Aceita SITE_ADDRESS com ou sem espaço depois da vírgula (o Caddy exige ", ").
set -eu
SITE_ADDRESS="$(printf '%s' "${SITE_ADDRESS:-localhost}" | sed -e 's/[[:space:]]*,[[:space:]]*/, /g' -e 's/^[[:space:]]*//' -e 's/[[:space:],]*$//')"
export SITE_ADDRESS
exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
