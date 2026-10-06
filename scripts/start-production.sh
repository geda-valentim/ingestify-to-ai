#!/usr/bin/env bash
# Deliberately bypass start.sh's shared development infrastructure discovery.
set -euo pipefail
cd "$(dirname "$0")/.."
compose=(docker compose --env-file "${PRODUCTION_ENV_FILE:-.env.production}" -f docker-compose.yml)
# Extra overlays must precede the security overlay.
for overlay in "$@"; do compose+=(-f "$overlay"); done
compose+=(-f docker-compose.prod.yml --profile infra)
"${compose[@]}" config --format json | python3 -c '
import ipaddress, json, sys
config = json.load(sys.stdin)
command = config["services"]["api"]["command"]
try:
    allowlist = command[command.index("--forwarded-allow-ips") + 1]
    for value in allowlist.split(","):
        if value.strip():
            ipaddress.ip_address(value.strip())
except (ValueError, IndexError):
    sys.exit("Production TRUSTED_PROXY_IPS must contain exact IP addresses only; wildcard/CIDR trust is forbidden")
'

"${compose[@]}" up -d --build
