#!/usr/bin/env bash
# Production deploy: `make deploy` (runs this script under `env -i`, see the Makefile).
#
# Flow
#   1. Preconditions: branch main; no local change in a tracked file that the pull would touch.
#   2. `git pull --ff-only`.
#   3. Change detection against the LAST SUCCESSFUL deploy (.git/deploy-last-success, never
#      tracked), not against the pre-pull HEAD: a failed run is detected again on the retry.
#      Missing marker: falls back to the pre-pull HEAD and warns (FORCE_REBUILD=1 rebuilds all).
#   4. Per category (only services present in `compose config --services`):
#        deps/Dockerfile/lock/copied scripts -> build, then `up -d --no-build --no-deps`
#        docker-compose*.yml                 -> `up -d --no-build --no-deps` (recreate)
#        backend code only                   -> `docker restart` of RUNNING containers
#                                               (managed ones included, see below)
#        frontend/                           -> build; `up` only if it is running
#        worker-live (code baked in image)   -> build only
#   5. Health: `compose port api 8000`, GET /health must be HTTP 200 with "status":"healthy".
#   6. Only then is .git/deploy-last-success written.
#
# Hard rules
#   * Never starts a stopped service and never removes replicas: only services with at least
#     one running container are touched; --scale is passed with the running count (> 0), never
#     to api/beat; if `ps` fails the deploy aborts.
#   * "Managed" = a service with an overlay /var/lib/ingestify-engine-agent/<svc>.json (the
#     observe- prefix and state.json are ignored). The static list worker, worker-audio,
#     worker-vision, worker-live is only a fallback when that directory is not readable.
#     The host agent applies managed services with a pinned image / profile / GPU overlay
#     that is not part of COMPOSE_FILE, so they are NEVER up'd here:
#       - only bind-mounted code changed: RUNNING managed containers get `docker restart`
#         (no recreate: overlay image/env/GPU is kept, the new code is loaded);
#       - image or compose changed: they are at most built, and the script prints that the
#         profile must be re-applied through the engine control (admin API/UI operation
#         apply_profile or restart, executed by the host agent). Pinned (sha256) images need
#         a new profile/digest.
#     Stopped managed services stay untouched. worker-live bakes the code into its image:
#     it is only built, never up'd or restarted.
#   * Not detectable: edits to untracked local overrides (docker-compose.override.yml, .env).
#     After changing them run the `up -d --no-build --no-deps <svc>` yourself.
#   * Compose reads .env itself; the caller environment is wiped (env -i) so make's
#     REDIS_HOST=localhost & co. can never leak into recreated containers.
#
# DRY_RUN=1 prints every mutating action (pull, build, up, restart, marker) without running
# it; read-only commands (ps, config, port, git diff) still run.
# Failure: the partial state and how to retry/roll back are printed (see on_exit).
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

DRY_RUN="${DRY_RUN:-0}"
FORCE_REBUILD="${FORCE_REBUILD:-0}"
export DOCKER_BUILDKIT=1
AGENT_DIR=/var/lib/ingestify-engine-agent

# Services whose code is bind-mounted from backend/ (a restart loads the pulled code).
CODE_SERVICES="api beat worker worker-audio worker-control worker-control-watchdog worker-dispatch worker-remote worker-vision"
# Engine-control-managed services (backend/workers/engine_control/local.py SERVICES).
MANAGED_STATIC="worker worker-audio worker-vision worker-live"   # fallback only
# api/beat have container_name and a single replica: never --scale.
NO_SCALE=" api beat "

# Files really copied into the images (docker/Dockerfile.*): requirements*.txt|lock, the
# Dockerfiles, entrypoint.sh and scripts/{make_admin,engines,seed_execution_profiles}.py.
IMAGE_RE='^(backend/requirements[^/]*\.(txt|lock)|docker/(Dockerfile\.[^/]+|entrypoint\.sh)|scripts/(make_admin|engines|seed_execution_profiles)\.py)$'
CODE_RE='^backend/(api|shared|workers)/'
COMPOSE_RE='^docker-compose[^/]*\.yml$'
FRONTEND_RE='^(frontend/|docker/Dockerfile\.frontend$)'
# worker-live bakes backend/shared and backend/workers into its image (no bind mount).
LIVE_RE='^(backend/(shared|workers)/|backend/requirements[^/]*\.(txt|lock)|docker/(Dockerfile\.(worker|live-whisperx)|entrypoint\.sh))'

STAGE="start"
OLD_HEAD=""
LAST_FILE=""
LAST_OK=""

log() { printf '==> %s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
run() {
  if [ "$DRY_RUN" = 1 ]; then printf '[dry-run] %s\n' "$*"; else "$@"; fi
}
compose() { docker compose "$@"; }
in_list() { case " $2 " in *" $1 "*) return 0;; esac; return 1; }

on_exit() {
  local rc=$?
  [ "$rc" -eq 0 ] && return 0
  local lgd="none recorded"
  [ -z "$LAST_OK" ] || lgd="${LAST_OK:0:7}"
  {
    echo
    echo "DEPLOY FAILED at stage: $STAGE (exit $rc)"
    echo "  HEAD now:           $(git rev-parse --short HEAD 2>/dev/null || echo '?')"
    echo "  HEAD before pull:   ${OLD_HEAD:0:7}"
    echo "  last good deploy:   $lgd"
    echo "  The code may be pulled while some services were not rebuilt/recreated."
    echo "  Retry: fix the cause and run 'make deploy' again; detection starts from the last"
    echo "  good deploy, so nothing is skipped. Full rebuild: 'make deploy FORCE_REBUILD=1'."
    echo "  Roll back: review, then 'git reset --hard <last good deploy>' on main and run"
    echo "  'make deploy FORCE_REBUILD=1'. Inspect with 'docker compose ps' and"
    echo "  'docker compose logs --tail=100 <service>'."
  } >&2
}
trap on_exit EXIT

# ---------------------------------------------------------------- preconditions
STAGE="preconditions"
[ "$(git branch --show-current)" = "main" ] || die "deploy runs from main (current: $(git branch --show-current))"
LAST_FILE="$(git rev-parse --git-path deploy-last-success)"
if [ -s "$LAST_FILE" ]; then
  LAST_OK="$(tr -d '[:space:]' <"$LAST_FILE")"
  git cat-file -e "${LAST_OK}^{commit}" 2>/dev/null || { warn "$LAST_FILE points to an unknown commit; ignoring"; LAST_OK=""; }
fi
OLD_HEAD="$(git rev-parse HEAD)"

STAGE="fetch"
run git fetch --quiet origin main
if [ "$DRY_RUN" = 1 ]; then
  UPSTREAM="$(git rev-parse --verify -q origin/main || echo HEAD)"
else
  UPSTREAM="$(git rev-parse origin/main)"
fi
mapfile -t INCOMING < <(git diff --name-only HEAD "$UPSTREAM")
mapfile -t LOCAL < <(git diff --name-only HEAD)
if [ "${#LOCAL[@]}" -gt 0 ]; then
  CLASH="$(comm -12 <(printf '%s\n' "${INCOMING[@]}" | sort -u) <(printf '%s\n' "${LOCAL[@]}" | sort -u) || true)"
  [ -z "$CLASH" ] || die "local changes in tracked files that the pull would touch; commit/stash them first:
$CLASH"
  warn "tracked files with local changes (not touched by the pull, kept): ${LOCAL[*]}"
fi

# ---------------------------------------------------------------- pull
STAGE="pull"
log "Pulling main"
run git pull --ff-only
if [ -n "$LAST_OK" ]; then
  BASE="$LAST_OK"
else
  BASE="$OLD_HEAD"
  warn "no $LAST_FILE: detecting changes from the pre-pull HEAD only (${OLD_HEAD:0:7}). Earlier failed deploys are not visible; use FORCE_REBUILD=1 if unsure."
fi
if [ "$DRY_RUN" = 1 ]; then NEWHEAD="$UPSTREAM"; else NEWHEAD="$(git rev-parse HEAD)"; fi
CHANGED="$(git diff --name-only "$BASE" "$NEWHEAD" || true)"
match() { grep -qE "$1" <<<"$CHANGED"; }

IMAGES=0; CODE=0; COMPOSE_CHG=0; FRONT=0; LIVE=0
match "$IMAGE_RE" && IMAGES=1
match "$CODE_RE" && CODE=1
match "$COMPOSE_RE" && COMPOSE_CHG=1
match "$FRONTEND_RE" && FRONT=1
match "$LIVE_RE" && LIVE=1
if [ "$FORCE_REBUILD" = 1 ]; then IMAGES=1; CODE=1; FRONT=1; LIVE=1; fi
[ -n "$LAST_OK" ] || [ "$FORCE_REBUILD" = 1 ] || CODE=1   # unknown history: reload code
log "Changes since ${BASE:0:7}: images=$IMAGES code=$CODE compose=$COMPOSE_CHG frontend=$FRONT live=$LIVE"

# ---------------------------------------------------------------- inventory
STAGE="inventory"
mapfile -t CONFIGURED < <(compose config --services)
[ "${#CONFIGURED[@]}" -gt 0 ] || die "compose config returned no services"
CONF=" ${CONFIGURED[*]} "

MANAGED=" "
if [ -d "$AGENT_DIR" ] && [ -r "$AGENT_DIR" ]; then
  for f in "$AGENT_DIR"/*.json; do
    [ -e "$f" ] || continue
    b="$(basename "$f" .json)"; b="${b#observe-}"
    [ "$b" = state ] || MANAGED="$MANAGED$b "
  done
else
  MANAGED=" $MANAGED_STATIC "
  warn "$AGENT_DIR not readable: falling back to the static managed list ($MANAGED_STATIC)"
fi

declare -A RUNNING=()   # service -> running container count (> 0 only)
declare -A IDS=()       # service -> running container ids
for s in $CODE_SERVICES worker-live frontend; do
  in_list "$s" "$CONF" || continue
  ids="$(compose ps --status running -q "$s")" || die "docker compose ps failed for $s; aborting (never guess replica counts)"
  n="$(printf '%s' "$ids" | grep -c . || true)"
  if [ "$n" -gt 0 ]; then RUNNING[$s]="$n"; IDS[$s]="$(printf '%s' "$ids" | tr '\n' ' ')"; fi
done

is_managed() { in_list "$1" "$MANAGED"; }
UNMANAGED_RUNNING=""   # running, not managed: safe to recreate/restart
MANAGED_RUNNING=""     # running, managed: restart only (never up)
MANAGED_TOUCHED=""     # managed: needs a re-apply when image/compose change
for s in $CODE_SERVICES; do
  in_list "$s" "$CONF" || continue
  if is_managed "$s"; then
    MANAGED_TOUCHED="$MANAGED_TOUCHED $s"
    [ -z "${RUNNING[$s]:-}" ] || MANAGED_RUNNING="$MANAGED_RUNNING $s"
  elif [ -n "${RUNNING[$s]:-}" ]; then UNMANAGED_RUNNING="$UNMANAGED_RUNNING $s"; fi
done

active_tasks_warning() {   # best effort, never blocks
  local s id out
  for s in worker worker-audio; do
    id="${IDS[$s]:-}"; id="${id%% *}"; [ -n "$id" ] || continue
    out="$(timeout 15 docker exec "$id" celery -A workers.celery_app inspect active --timeout 3 2>&1 || true)"
    if printf '%s' "$out" | grep -q "'id'\|\"id\""; then
      warn "$s has ACTIVE tasks; recreating/restarting it interrupts them (they are redelivered)."
    fi
  done
}

scale_args() {   # --scale svc=<running> only for running services, count > 0, not api/beat
  local s out=()
  for s in "$@"; do
    in_list "$s" "$NO_SCALE" && continue
    [ "${RUNNING[$s]:-0}" -gt 0 ] || continue
    out+=(--scale "$s=${RUNNING[$s]}")
  done
  printf '%s\n' "${out[@]:-}"
}

# ---------------------------------------------------------------- backend images
STAGE="backend"
if [ "$IMAGES" = 1 ] || [ "$COMPOSE_CHG" = 1 ]; then
  active_tasks_warning
fi
if [ "$IMAGES" = 1 ]; then
  BUILD=""
  for s in $CODE_SERVICES; do in_list "$s" "$CONF" && BUILD="$BUILD $s"; done
  log "Image inputs changed: building$BUILD (managed ones are only built)"
  # shellcheck disable=SC2086
  run compose build $BUILD
fi
if [ "$IMAGES" = 1 ] || [ "$COMPOSE_CHG" = 1 ]; then
  if [ -n "$UNMANAGED_RUNNING" ]; then
    mapfile -t SC < <(scale_args $UNMANAGED_RUNNING)
    [ -n "${SC[0]:-}" ] || SC=()
    log "Recreating running unmanaged services:$UNMANAGED_RUNNING ${SC[*]:-}"
    # shellcheck disable=SC2086
    run compose up -d --no-build --no-deps "${SC[@]}" $UNMANAGED_RUNNING
  fi
elif [ "$CODE" = 1 ] && [ -n "$UNMANAGED_RUNNING$MANAGED_RUNNING" ]; then
  active_tasks_warning
  RIDS=""
  for s in $UNMANAGED_RUNNING $MANAGED_RUNNING; do RIDS="$RIDS ${IDS[$s]:-}"; done
  log "Restarting running services (managed ones keep their overlay, no recreate):$UNMANAGED_RUNNING$MANAGED_RUNNING"
  # shellcheck disable=SC2086
  [ -z "${RIDS// /}" ] || run docker restart $RIDS
fi

# ---------------------------------------------------------------- worker-live
STAGE="worker-live"
LIVE_BUILT=0
if [ "$LIVE" = 1 ] && in_list worker-live "$CONF"; then
  log "worker-live bakes the code: building its image (never up'd here)"
  run compose build worker-live
  LIVE_BUILT=1
fi

# ---------------------------------------------------------------- frontend
STAGE="frontend"
if [ "$FRONT" = 1 ] && in_list frontend "$CONF"; then
  log "Rebuilding the frontend"
  run compose build frontend
  if [ -n "${RUNNING[frontend]:-}" ]; then
    run compose up -d --no-build --no-deps frontend
  else
    log "frontend is not running: built only, not started"
  fi
fi

# ---------------------------------------------------------------- managed notice
NOTICE=""
if [ "$IMAGES" = 1 ] || [ "$COMPOSE_CHG" = 1 ]; then NOTICE="$MANAGED_TOUCHED"; fi
[ "$LIVE_BUILT" = 0 ] || NOTICE="$NOTICE worker-live"
if [ -n "${NOTICE// /}" ]; then
  {
    echo
    echo "ATTENTION - engine-control-managed services were NOT recreated:"
    echo "  ${NOTICE# }"
    echo "  They keep running the old image/compose settings. Re-apply their profile through the engine control (admin API/UI,"
    echo "  operation apply_profile or restart): the host agent recreates them with the pinned"
    echo "  image, GPU and profile overlay. Services stopped on purpose stay stopped."
  } >&2
fi

# ---------------------------------------------------------------- health
STAGE="health"
if [ "$DRY_RUN" = 1 ]; then
  log "[dry-run] skipping health check and marker"
  STAGE="done"
  exit 0
fi
hp="$(compose port api 8000 || true)"
port="${hp##*:}"
case "$port" in ''|*[!0-9]*) die "api does not publish 8000 (compose port: '${hp}')";; esac
url="http://127.0.0.1:${port}/health"
log "Waiting for $url"
body=""
ok=0
for i in $(seq 1 40); do
  body="$(curl -s -m 5 -w ' HTTP %{http_code}' "$url" || true)"
  case "$body" in *'"status":"healthy"'*'HTTP 200') ok=1; break;; esac
  sleep 3
done
[ "$ok" = 1 ] || die "API not healthy after 40 attempts: ${body:-no response (connection refused/timeout)}"
echo "OK $body"

STAGE="marker"
git rev-parse HEAD >"$LAST_FILE"
STAGE="done"
log "Deployed $(git rev-parse --short HEAD) (marker: $LAST_FILE)"
