#!/bin/bash
# Ensure JWT_SECRET_KEY is available for the API.
# Keeps an existing value (environment or .env) so sessions stay valid across
# restarts; otherwise generates a new secret and saves it to .env in the repo root.
# docker compose and run_api.sh (pydantic) both read .env from the repo root.

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"

if [ -n "$JWT_SECRET_KEY" ]; then
    exit 0
fi

if [ -f "$ENV_FILE" ] && grep -q '^JWT_SECRET_KEY=..*' "$ENV_FILE"; then
    exit 0
fi

if [ -f "$ENV_FILE" ]; then
    grep -v '^JWT_SECRET_KEY=' "$ENV_FILE" > "$ENV_FILE.tmp" || true
    mv "$ENV_FILE.tmp" "$ENV_FILE"
    # Make sure the new line does not get glued to a last line without newline
    [ -s "$ENV_FILE" ] && [ -n "$(tail -c1 "$ENV_FILE")" ] && echo >> "$ENV_FILE"
fi

echo "JWT_SECRET_KEY=$(openssl rand -hex 32)" >> "$ENV_FILE"
echo "🔑 Generated a new JWT_SECRET_KEY in $ENV_FILE"
