#!/bin/sh
# Start the app as the unprivileged "app" user.
#
# The container starts as root only to hand the shared temp storage (often a host
# bind mount created by root, e.g. ./tmp) over to "app", then drops privileges
# for good with setpriv (util-linux, part of the base image).
set -e

TEMP_DIR="${TEMP_STORAGE_PATH:-/tmp/ingestify}"

if [ "$(id -u)" = "0" ]; then
    mkdir -p "$TEMP_DIR"
    # Only entries not owned by app yet, so restarts stay fast
    find "$TEMP_DIR" ! -user app -exec chown app:app {} + 2>/dev/null || true
    exec setpriv --reuid=app --regid=app --init-groups -- "$@"
fi

exec "$@"
