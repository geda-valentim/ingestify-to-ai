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
    find "$TEMP_DIR" ! -user app -exec chown app:app {} + || true

    # Fail loudly if app still cannot write there (e.g. rootless Docker, NFS root squash)
    if ! setpriv --reuid=app --regid=app --init-groups -- test -w "$TEMP_DIR"; then
        echo "entrypoint: $TEMP_DIR is not writable by user app (uid $(id -u app)); fix its ownership/permissions" >&2
        exit 1
    fi

    # setpriv keeps the environment: point HOME at app's home (model caches, e.g. Whisper)
    export HOME=/home/app USER=app LOGNAME=app
    exec setpriv --reuid=app --regid=app --init-groups -- "$@"
fi

exec "$@"
