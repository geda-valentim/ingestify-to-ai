#!/usr/bin/env bash
# Production deploy: `make deploy` (runs this script under `env -i`, see the Makefile).
# Flow, flags, first deploy and rollback: docs/runbooks/deploy.md.
# Rules: detection starts at the last good deploy (.git/deploy-last-success; no marker aborts
# before any change); never start a stopped service, remove replicas or `up` an engine-managed
# one (overlay in $AGENT_DIR); health must match the deployed API_VERSION before the marker is
# written; rollback is DEPLOY_REF=<sha> (no pull); DRY_RUN=1 prints every mutating action.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
DRY_RUN="${DRY_RUN:-0}"; FORCE_REBUILD="${FORCE_REBUILD:-0}"; BUILD_LIVE="${BUILD_LIVE:-0}"
NO_PULL="${NO_PULL:-0}"; DEPLOY_REF="${DEPLOY_REF:-}"; DEPLOY_BASE="${DEPLOY_BASE:-}"
export DOCKER_BUILDKIT=1
AGENT_DIR="${DEPLOY_AGENT_DIR:-/var/lib/ingestify-engine-agent}"

# Services whose code is bind-mounted from backend/ (a restart loads the pulled code).
CODE_SERVICES="api beat worker worker-audio worker-control worker-control-watchdog worker-dispatch worker-remote worker-vision"
# api/beat have container_name and a single replica: never --scale.
NO_SCALE=" api beat "

# Files really copied into the images (docker/Dockerfile.*).
IMAGE_RE='^(backend/requirements[^/]*\.(txt|lock)|docker/(Dockerfile\.(api|audio|live-whisperx|remote|worker)|entrypoint\.sh)|scripts/(make_admin|engines|seed_execution_profiles)\.py)$'
CODE_RE='^backend/(api|shared|workers)/'
COMPOSE_RE='^docker-compose[^/]*\.yml$'
FRONTEND_RE='^(frontend/|docker/Dockerfile\.frontend$)'
# worker-live bakes backend/shared and backend/workers into its image (no bind mount).
LIVE_RE='^(backend/(shared|workers)/|backend/requirements[^/]*\.(txt|lock)|docker/(Dockerfile\.(worker|live-whisperx)|entrypoint\.sh))'

STAGE="start"; OLD_HEAD=""; LAST_FILE=""; LAST_OK=""; EXPECTED=""

log() { printf '==> %s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
run() { if [ "$DRY_RUN" = 1 ]; then printf '[dry-run] %s\n' "$*"; else "$@"; fi; }
compose() { docker compose "$@"; }
in_list() { case " $2 " in *" $1 "*) return 0;; esac; return 1; }

on_exit() {
  local rc=$?
  [ "$rc" -eq 0 ] && return 0
  local lgd what=""
  lgd="${LAST_OK:0:7}"; [ -n "$lgd" ] || lgd="none recorded"
  case "$STAGE" in
    start|preconditions|fetch) what="nothing changed (no git or container action ran).";;
    pull) what="the merge/reset is atomic: HEAD is unchanged or fully moved; see 'git status'.";;
    inventory) what="code is at the new HEAD but no container was touched.";;
    backend|worker-live|frontend) what="PARTIAL state: some services were built/recreated, others not.";;
    health) what="all actions ran, but the API is unhealthy or on another version (logs: api).";;
    marker) what="deploy is healthy but the marker is missing: git rev-parse HEAD > \"$LAST_FILE\"";;
  esac
  {
    echo
    echo "DEPLOY FAILED at stage: $STAGE (exit $rc)"
    echo "  HEAD now: $(git rev-parse --short HEAD 2>/dev/null || echo '?')   HEAD before: ${OLD_HEAD:0:7}   last good deploy: $lgd"
    echo "  $what Retry: 'make deploy'. Roll back (no pull): 'make deploy DEPLOY_REF=<last good deploy>'."
  } >&2
}
trap on_exit EXIT
# ---------------------------------------------------------------- preconditions
STAGE="preconditions"
[ "$(git branch --show-current)" = "main" ] || die "deploy runs from main (current: $(git branch --show-current))"
LAST_FILE="$(git rev-parse --git-path deploy-last-success)"
if [ -s "$LAST_FILE" ]; then
  LAST_OK="$(tr -d '[:space:]' <"$LAST_FILE")"
  git cat-file -e "${LAST_OK}^{commit}" 2>/dev/null || { warn "$LAST_FILE points to an unknown commit"; LAST_OK=""; }
fi
OLD_HEAD="$(git rev-parse HEAD)"
PENDING_FILE="$(git rev-parse --git-path deploy-pending)"   # one commit per line: every HEAD an unfinished deploy touched
PENDING=()
if [ -s "$PENDING_FILE" ]; then
  while read -r c; do
    [ -z "$c" ] || if git cat-file -e "${c}^{commit}" 2>/dev/null; then PENDING+=("$c"); else warn "pending: unknown commit $c; ignoring"; fi
  done <"$PENDING_FILE"
fi

# P1: the detection base is fixed BEFORE any git change; without one the deploy aborts.
UNKNOWN_BASE=0
if [ -n "$DEPLOY_BASE" ]; then
  git cat-file -e "${DEPLOY_BASE}^{commit}" 2>/dev/null || die "DEPLOY_BASE=$DEPLOY_BASE is not a known commit"
  BASE="$DEPLOY_BASE"
elif [ -n "$LAST_OK" ]; then
  BASE="$LAST_OK"
elif [ "$FORCE_REBUILD" = 1 ]; then
  BASE="$OLD_HEAD"; UNKNOWN_BASE=1
  warn "no usable deploy marker: FORCE_REBUILD=1 rebuilds everything from the pre-pull HEAD (${OLD_HEAD:0:7})"
else
  die "no deploy marker ($LAST_FILE missing or pointing to an unknown commit); nothing was changed. Seed it (runbook: first deploy) or pass DEPLOY_BASE=<sha> / FORCE_REBUILD=1"
fi

STAGE="fetch"
if [ -n "$DEPLOY_REF" ]; then   # rollback: no pull, target must already be on origin/main
  NO_PULL=1
  git cat-file -e "${DEPLOY_REF}^{commit}" 2>/dev/null || die "DEPLOY_REF=$DEPLOY_REF is not a known commit"
  git merge-base --is-ancestor "$DEPLOY_REF" origin/main || die "DEPLOY_REF=$DEPLOY_REF is not an ancestor of origin/main"
  UPSTREAM="$(git rev-parse "${DEPLOY_REF}^{commit}")"
elif [ "$NO_PULL" = 1 ]; then
  UPSTREAM="$OLD_HEAD"
else
  run git fetch --quiet origin main
  if [ "$DRY_RUN" = 1 ]; then
    UPSTREAM="$(git rev-parse --verify -q origin/main || echo HEAD)"
  else
    UPSTREAM="$(git rev-parse origin/main)"
  fi
fi
NEWHEAD="$UPSTREAM"
mapfile -t INCOMING < <(git diff --no-renames --name-only HEAD "$NEWHEAD")
mapfile -t LOCAL < <(git diff --no-renames --name-only HEAD)
if [ "${#LOCAL[@]}" -gt 0 ]; then
  CLASH="$(comm -12 <(printf '%s\n' "${INCOMING[@]}" | sort -u) <(printf '%s\n' "${LOCAL[@]}" | sort -u) || true)"
  [ -z "$CLASH" ] || die "local changes in tracked files that the pull would touch; commit/stash them first:
$CLASH"
  warn "tracked files with local changes (not touched by the pull, kept): ${LOCAL[*]}"
fi
EXPECTED="$(git show "$NEWHEAD:backend/api/openapi_docs.py" | sed -n 's/^API_VERSION = "\([^"]*\)".*/\1/p' || true)"
[ -n "$EXPECTED" ] || die "cannot read API_VERSION from backend/api/openapi_docs.py at ${NEWHEAD:0:7}"

# Marker, current HEAD and the pending (unfinished deploy) HEAD, each ->target: a failed deploy
# or rollback is covered again on retry, even when marker->target is empty.
CHANGED="$( { git diff --no-renames --name-only "$BASE" "$NEWHEAD"; git diff --no-renames --name-only "$OLD_HEAD" "$NEWHEAD"
  for c in "${PENDING[@]}"; do git diff --no-renames --name-only "$c" "$NEWHEAD"; done; } | sort -u)"
match() { grep -qE "$1" <<<"$CHANGED"; }

IMAGES=0; CODE=0; COMPOSE_CHG=0; FRONT=0; LIVE=0
match "$IMAGE_RE" && IMAGES=1; match "$CODE_RE" && CODE=1; match "$COMPOSE_RE" && COMPOSE_CHG=1
match "$FRONTEND_RE" && FRONT=1; match "$LIVE_RE" && LIVE=1
if [ "$FORCE_REBUILD" = 1 ]; then IMAGES=1; CODE=1; FRONT=1; LIVE=1; fi
[ "$UNKNOWN_BASE" = 0 ] || COMPOSE_CHG=1
log "Target ${NEWHEAD:0:7} (API $EXPECTED); changes since ${BASE:0:7}: images=$IMAGES code=$CODE compose=$COMPOSE_CHG frontend=$FRONT live=$LIVE"
# ---------------------------------------------------------------- pull
STAGE="pull"
[ -n "$DEPLOY_REF" ] || [ "$NO_PULL" = 1 ] || git merge-base --is-ancestor HEAD "$NEWHEAD" || die "local main is ahead of ${NEWHEAD:0:7}; nothing changed"
for c in "$OLD_HEAD" "$NEWHEAD"; do   # append (no duplicates) before the first state change
  [ "$DRY_RUN" = 1 ] || grep -qx "$c" "$PENDING_FILE" 2>/dev/null || printf '%s\n' "$c" >>"$PENDING_FILE"
done
if [ -n "$DEPLOY_REF" ]; then
  log "Rolling back to ${DEPLOY_REF:0:7} (reset --keep refuses to drop local changes)"; run git reset --keep "$NEWHEAD"
elif [ "$NO_PULL" = 1 ]; then log "NO_PULL=1: deploying the current HEAD"
else
  log "Fast-forwarding main to ${NEWHEAD:0:7}"; run git merge --ff-only "$NEWHEAD"
fi
# ---------------------------------------------------------------- inventory
STAGE="inventory"
compose config --quiet || die "compose config is invalid; nothing was touched"
mapfile -t CONFIGURED < <(compose config --services)
[ "${#CONFIGURED[@]}" -gt 0 ] || die "compose config returned no services"
CONF=" ${CONFIGURED[*]} "
CF="$(sed -n 's/^COMPOSE_FILE=//p' .env 2>/dev/null | tail -1 | tr -d "\"'" || true)"
log "COMPOSE_FILE from .env: ${CF:-<unset: compose defaults>}"
if [ -f docker-compose.override.yml ] && [ -n "$CF" ]; then
  sep="${COMPOSE_PATH_SEPARATOR:-:}"
  [[ "$sep$CF$sep" == *"${sep}docker-compose.override.yml$sep"* ]] ||
    warn "docker-compose.override.yml exists but is NOT in COMPOSE_FILE: compose ignores it"
fi

HOST_CFG="${DEPLOY_ENGINE_HOST_CONFIG:-/etc/ingestify/engine-host.json}"
MANAGED=" "
if [ -d "$AGENT_DIR" ] && [ -r "$AGENT_DIR" ]; then
  for f in "$AGENT_DIR"/*.json; do
    [ -e "$f" ] || continue
    b="$(basename "$f" .json)"; b="${b#observe-}"
    [ "$b" = state ] || MANAGED="$MANAGED$b "
  done
elif [ -e "$AGENT_DIR" ] || [ -e "$HOST_CFG" ]; then   # engine control is installed but its state is unusable
  die "engine control installed ($HOST_CFG) but $AGENT_DIR is missing/unreadable: cannot tell which services are managed; nothing was touched"
else
  log "engine control not installed: no managed services"
fi

declare -A RUNNING=() IDS=()   # service -> running count (> 0 only) / running container ids
for s in $CODE_SERVICES worker-live frontend; do
  in_list "$s" "$CONF" || continue
  ids="$(compose ps --status running -q "$s")" || die "docker compose ps failed for $s; aborting (never guess replica counts)"
  n="$(printf '%s' "$ids" | grep -c . || true)"
  if [ "$n" -gt 0 ]; then RUNNING[$s]="$n"; IDS[$s]="$(printf '%s' "$ids" | tr '\n' ' ')"; fi
done

is_managed() { in_list "$1" "$MANAGED"; }
UNMANAGED_RUNNING=""; MANAGED_RUNNING=""; MANAGED_TOUCHED=""   # recreate-safe / restart-only / needs re-apply
for s in $CODE_SERVICES; do
  in_list "$s" "$CONF" || continue
  if is_managed "$s"; then
    MANAGED_TOUCHED="$MANAGED_TOUCHED $s"
    [ -z "${RUNNING[$s]:-}" ] || MANAGED_RUNNING="$MANAGED_RUNNING $s"
  elif [ -n "${RUNNING[$s]:-}" ]; then UNMANAGED_RUNNING="$UNMANAGED_RUNNING $s"; fi
done

active_tasks_warning() {   # best effort, never blocks
  local s id out pfx
  for s in worker worker-audio; do
    id="${IDS[$s]:-}"; id="${id%% *}"; [ -n "$id" ] || continue
    case "$s" in worker) pfx=ingestify-worker;; *) pfx=ingestify-audio;; esac
    # -d: only this container's node (a broadcast reports other workers' tasks too)
    out="$(timeout 15 docker exec "$id" sh -c "celery -A workers.celery_app inspect active -d \"$pfx@\$(hostname)\" --timeout 3" 2>&1 || true)"
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

restart_running() {   # restart (not recreate) running containers: overlay kept
  local ids="" s
  for s in "$@"; do ids="$ids ${IDS[$s]:-}"; done
  log "Restarting running services:$*"
  # shellcheck disable=SC2086
  [ -z "${ids// /}" ] || run docker restart $ids
}
# ---------------------------------------------------------------- backend images
STAGE="backend"
if [ "$IMAGES" = 1 ] || [ "$COMPOSE_CHG" = 1 ]; then active_tasks_warning; fi
if [ "$IMAGES" = 1 ] || [ "$COMPOSE_CHG" = 1 ]; then   # compose may change build inputs (args, Dockerfile)
  BUILD=""
  for s in $CODE_SERVICES; do in_list "$s" "$CONF" && BUILD="$BUILD $s"; done
  log "Image inputs changed: building$BUILD (managed ones are only built)"
  # shellcheck disable=SC2086
  run compose build $BUILD
fi
if [ "$IMAGES" = 1 ] || [ "$COMPOSE_CHG" = 1 ]; then
  if [ -n "$UNMANAGED_RUNNING" ]; then
    mapfile -t SC < <(scale_args $UNMANAGED_RUNNING); [ -n "${SC[0]:-}" ] || SC=()
    log "Recreating running unmanaged services:$UNMANAGED_RUNNING ${SC[*]:-}"
    # shellcheck disable=SC2086
    # --force-recreate: with equal config/image a plain `up` keeps the container and the new code unloaded
    run compose up -d --no-build --no-deps --force-recreate "${SC[@]}" $UNMANAGED_RUNNING
  fi
  if [ "$IMAGES" = 0 ] && [ -n "$MANAGED_RUNNING" ]; then
    restart_running $MANAGED_RUNNING   # compose-only: no new image, a restart loads the code
  fi
elif [ "$CODE" = 1 ] && [ -n "$UNMANAGED_RUNNING$MANAGED_RUNNING" ]; then
  active_tasks_warning
  restart_running $UNMANAGED_RUNNING $MANAGED_RUNNING
fi
# ---------------------------------------------------------------- worker-live
STAGE="worker-live"
LIVE_BUILT=0
if in_list worker-live "$CONF"; then
  if [ "$BUILD_LIVE" = 1 ]; then   # explicit request, independent of detection
    log "worker-live bakes the code: building its image (never up'd here)"; run compose build worker-live; LIVE_BUILT=1
  elif [ "$LIVE" = 1 ]; then
    warn "worker-live inputs changed: its image is stale. Run with BUILD_LIVE=1, then apply_profile."
  fi
fi
# ---------------------------------------------------------------- frontend
STAGE="frontend"
if in_list frontend "$CONF" && { [ "$FRONT" = 1 ] || { [ "$COMPOSE_CHG" = 1 ] && [ -n "${RUNNING[frontend]:-}" ]; }; }; then
  log "Rebuilding the frontend (cached if nothing changed)"; run compose build frontend
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
if [ "$COMPOSE_CHG" = 1 ] && ! in_list worker-live "$NOTICE" && in_list worker-live "$CONF" && is_managed worker-live; then
  NOTICE="$NOTICE worker-live"   # built only, yet a compose change still needs the re-register
fi
if [ -n "${NOTICE// /}" ]; then
  {
    echo
    echo "ATTENTION - engine-control-managed services were NOT recreated:${NOTICE}"
    if [ "$COMPOSE_CHG" = 1 ]; then
      echo "  Compose changed: the host agent is now in REGISTERED_MANIFEST_CHANGED. Re-register the host"
      echo "  (docs/runbooks/engine-control-bootstrap.md, 'Re-registrar o host'), THEN run apply_profile."
    fi
    if [ "$IMAGES" = 1 ] || [ "$LIVE_BUILT" = 1 ]; then
      echo "  New image: re-register the host with the new image digest (same runbook), THEN apply_profile."
    fi
    echo "  Services stopped on purpose stay stopped."
  } >&2
fi
# ---------------------------------------------------------------- health
STAGE="health"
if [ "$DRY_RUN" = 1 ]; then
  log "[dry-run] skipping health check and marker"; STAGE="done"; exit 0
fi
hp="$(compose port api 8000 || true)"; port="${hp##*:}"
case "$port" in ''|*[!0-9]*) die "api does not publish 8000 (compose port: '${hp}')";; esac
url="http://127.0.0.1:${port}/health"
log "Waiting for $url"
body=""; ok=0
for i in $(seq 1 40); do
  body="$(curl -s -m 5 -w ' HTTP %{http_code}' "$url" || true)"
  if [[ $body == *'"status":"healthy"'* && $body == *"\"version\":\"$EXPECTED\""* && $body == *'HTTP 200' ]]; then ok=1; break; fi
  sleep 3
done
if [ "$ok" != 1 ]; then
  if [[ $body == *'"status":"healthy"'* && $body == *'HTTP 200' ]]; then
    die "API is healthy but runs another version than the deployed commit (expected $EXPECTED): $body"
  fi
  die "API unhealthy after 40 attempts: ${body:-no response (connection refused/timeout)}"
fi
echo "OK $body"

STAGE="marker"
git rev-parse HEAD >"$LAST_FILE"
rm -f "$PENDING_FILE"
STAGE="done"; log "Deployed $(git rev-parse --short HEAD) (marker: $LAST_FILE)"
