#!/usr/bin/env bash
set -euo pipefail

PORT="${NGROK_PORT:-8000}"
DOMAIN="${NGROK_DOMAIN:-}"
CONFIG="${NGROK_CONFIG:-}"

ARGS=("http" "${PORT}")

if [[ -n "${DOMAIN}" ]]; then
  ARGS+=("--domain" "${DOMAIN}")
fi

if [[ -n "${CONFIG}" ]]; then
  ARGS+=("--config" "${CONFIG}")
fi

exec /opt/homebrew/bin/ngrok "${ARGS[@]}"
