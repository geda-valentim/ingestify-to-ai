#!/bin/sh
# Start the app as the unprivileged "app" user.
#
# The container starts as root only to hand the shared temp storage (often a host
# bind mount created by root, e.g. ./tmp) over to "app", then drops privileges
# for good with setpriv (util-linux, part of the base image).
set -e

TEMP_DIR="${TEMP_STORAGE_PATH:-/tmp/ingestify}"

if [ "$(id -u)" = "0" ]; then
    # HF_HOME: the named model-cache volume (vision workers). A volume created by
    # an older, root-running image is still owned by root.
    for DIR in "$TEMP_DIR" ${HF_HOME:+"$HF_HOME"}; do
        mkdir -p "$DIR"
        # Only entries not owned by app yet, so restarts stay fast
        find "$DIR" ! -user app -exec chown app:app {} + || true

        # Fail loudly if app still cannot write there (e.g. rootless Docker, NFS root squash)
        if ! setpriv --reuid=app --regid=app --init-groups -- test -w "$DIR"; then
            echo "entrypoint: $DIR is not writable by user app (uid $(id -u app)); fix its ownership/permissions" >&2
            exit 1
        fi
    done

    # worker-remote: the engine private key arrives as a read-only bind mount, usually
    # owned by the host user with mode 600. Hand app a copy on the tmpfs at
    # /run/ingestify-keys (compose), readable by app only, and point the setting at it.
    KEY_FILE="${ENGINE_SECRETS_PRIVATE_KEYS_FILE:-}"
    if [ -n "$KEY_FILE" ] && [ -f "$KEY_FILE" ] && ! setpriv --reuid=app --regid=app --init-groups -- test -r "$KEY_FILE"; then
        mkdir -p /run/ingestify-keys
        chown app:app /run/ingestify-keys
        chmod 700 /run/ingestify-keys
        install -m 400 -o app -g app "$KEY_FILE" /run/ingestify-keys/engine_secrets_private
        export ENGINE_SECRETS_PRIVATE_KEYS_FILE=/run/ingestify-keys/engine_secrets_private
    fi

    # setpriv keeps the environment: point HOME at app's home (model caches, e.g. Whisper)
    export HOME=/home/app USER=app LOGNAME=app
    exec setpriv --reuid=app --regid=app --init-groups -- "$@"
fi

exec "$@"
