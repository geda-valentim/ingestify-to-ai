"""
IAM inventory (spec 0014 CA1, CA2).

CA1: every route of the app declares exactly one authorization (`require`,
`authorized`, `visible`, `engine_access`) or is in the public allowlist. Routes
not converted yet are listed in PENDING_ROUTES, which may only shrink: an entry
that was converted, or that no longer exists, fails until it is removed.

CA2: platform power and ownership are not decided inline in `api/` or
`workers/`. Every `is_effective_admin` / `.is_admin` and every `user_id ==` /
`!=` comparison there is listed below with a reason, and the lists may only
shrink (exact counts: a stale entry fails too).
"""

import inspect
import re
from collections import Counter
from pathlib import Path

from fastapi.routing import APIRoute, APIWebSocketRoute
from starlette.routing import Route

from api.iam_deps import declaration_of
from api.main import app

BACKEND = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# CA1
# ---------------------------------------------------------------------------

# Public by design (CA1). Keys are "METHOD path"; WS routes use "WS".
PUBLIC_ROUTES = {
    "GET /",
    "GET /health",
    "POST /auth/login",
    "POST /auth/register",
    "POST /auth/refresh",
}
# WebSockets authenticated by a single-use ticket instead of a user dependency
# (CA1 "WS /live/{id}/stream com ticket"). The ticket is only issued by a route
# that declares IAM (`POST /transcribe/live/sessions`, require(live.sessions.create)),
# and the handler must still decide, through shared.iam, that the ticket's user
# owns the job (checked below): a route-level dependency cannot, since the
# identity arrives in the first WS message, after the handshake.
TICKET_ROUTES = {
    "WS /transcribe/live/sessions/{job_id}/stream": "POST /transcribe/live/sessions",
}
TICKET_GUARD = "decide("
# Named public by the spec (CA1) but not in the app yet. Kept apart so that every
# PUBLIC_ROUTES entry is checked to exist; move it there when the route lands.
RESERVED_PUBLIC_ROUTES = {
    "GET /auth/registration-settings": "0014 CA1 lists it; no such route exists yet",
}
# Machine identities (engine hosts), never a user session. Listed one by one: each
# handler must authenticate the host with `host_identity(...)` (checked below).
MACHINE_ROUTES = {
    "POST /internal/engine-hosts/{host_id}/heartbeat",
    "GET /internal/engine-hosts/{host_id}/next",
    "GET /internal/engine-hosts/{host_id}/operations/{op_id}/check",
    "POST /internal/engine-hosts/{host_id}/operations/{op_id}/events",
    "POST /internal/engine-hosts/{host_id}/operations/{op_id}/result",
}
MACHINE_GUARD = "host_identity("
# FastAPI's own documentation routes.
DOCS_PATHS = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}

# Routes still on their legacy guard. Every data route was converted in spec 0014
# §8 item 4; the set stays, empty, so a future slice cannot reopen it unnoticed
# (it may only shrink, and may not grow: see PENDING_MAX).
PENDING_ROUTES: set = set()

# Exact sizes, so the allowlists cannot grow unnoticed (a removal that is later
# re-added would otherwise pass). Lower these in each slice that converts.
PENDING_MAX = 0
ADMIN_ALLOWLIST_MAX = 21
OWNER_ALLOWLIST_MAX = 4

# The only routes that may declare authenticated(): they describe the caller to
# themselves and read nobody else's data (0014 §4.9 "sessão").
AUTHENTICATED_ROUTES = {"GET /auth/me", "GET /iam/permissions", "POST /iam/check"}

# The administrative routes of §4.7 and §4.9, with the permission each declares and
# whether it also demands a login session. Pinned so a route cannot drift to a
# weaker permission unnoticed.
PLATFORM_ROUTES = {
    "GET /admin/stats": ("platform.stats.read", False),
    "GET /admin/jobs/stuck": ("platform.jobs.read", False),
    "POST /admin/jobs/recover-stuck": ("platform.jobs.recover", False),
    "POST /admin/jobs/{job_id}/retry-all-failed": ("platform.jobs.recover", False),
    "POST /admin/cleanup": ("platform.jobs.cleanup", False),
    "GET /admin/health/monitoring": ("platform.monitoring.read", False),
    "GET /admin/broker/unacked": ("platform.monitoring.read", False),
    "POST /admin/broker/unacked/{delivery_tag}/requeue": ("platform.broker.requeue", False),
    "GET /admin/routing": ("platform.routing.read", False),
    "GET /admin/engines/status": ("platform.routing.read", False),
    "PUT /admin/routing/{feature}": ("platform.routing.update", True),
    "DELETE /admin/routing/{feature}": ("platform.routing.update", True),
    "GET /admin/iam/bindings": ("iam.bindings.read", False),
    "POST /admin/iam/bindings": ("iam.bindings.manage", True),
    "POST /admin/iam/bindings/{binding_id}/revoke": ("iam.bindings.manage", True),
}

# What a route marked engine_access() must still be guarded by (0009, unchanged).
ENGINE_GUARDS = {"access_session", "require_admin", "require_admin_session"}


def _calls(dependant):
    """Every dependency callable in the route's tree, depth-first, deduplicated."""
    seen = []
    stack = list(dependant.dependencies)
    while stack:
        dep = stack.pop()
        if dep.call not in seen:
            seen.append(dep.call)
        stack.extend(dep.dependencies)
    return seen


def _inventory():
    """{"METHOD path": [Declaration, ...]} plus the guards each route depends on."""
    routes, guards, endpoints = {}, {}, {}
    for route in app.routes:
        if isinstance(route, (APIRoute, APIWebSocketRoute)):
            calls = _calls(route.dependant)
            decls = [d for d in (declaration_of(c) for c in calls) if d is not None]
            names = {getattr(c, "__name__", "") for c in calls}
            methods = sorted(route.methods) if isinstance(route, APIRoute) else ["WS"]
            for method in methods:
                key = f"{method} {route.path}"
                assert key not in routes, f"duplicate route {key}"
                routes[key], guards[key], endpoints[key] = decls, names, route.endpoint
        elif isinstance(route, Route) and route.path in DOCS_PATHS:
            continue
        else:
            raise AssertionError(f"unexpected route type {type(route).__name__} at {getattr(route, 'path', '?')}")
    return routes, guards, endpoints


def _public(key: str) -> bool:
    return key in PUBLIC_ROUTES or key in MACHINE_ROUTES or key in TICKET_ROUTES


def test_every_route_declares_exactly_one_authorization():
    routes, _, _ = _inventory()
    wrong = {}
    for key, decls in routes.items():
        if _public(key) or key in PENDING_ROUTES:
            continue
        if len(decls) != 1:
            wrong[key] = [d.kind for d in decls]
    assert not wrong, f"routes without exactly one IAM declaration: {wrong}"


def test_public_routes_declare_nothing():
    routes, _, _ = _inventory()
    declared = {k: d for k, d in routes.items() if _public(k) and d}
    assert not declared, f"a public route cannot also declare a permission: {declared}"


def test_pending_allowlist_only_shrinks():
    routes, _, _ = _inventory()
    gone = sorted(k for k in PENDING_ROUTES if k not in routes)
    assert not gone, f"remove from PENDING_ROUTES, the route no longer exists: {gone}"
    converted = sorted(k for k in PENDING_ROUTES if routes[k])
    assert not converted, f"remove from PENDING_ROUTES, the route now declares IAM: {converted}"
    public = sorted(k for k in PENDING_ROUTES if _public(k))
    assert not public, f"a route cannot be both public and pending: {public}"


def test_public_and_machine_allowlists_name_real_routes():
    routes, _, _ = _inventory()
    gone = sorted(k for k in PUBLIC_ROUTES | MACHINE_ROUTES | set(TICKET_ROUTES) if k not in routes)
    assert not gone, f"public/machine/ticket allowlist entries with no route: {gone}"
    landed = sorted(k for k in RESERVED_PUBLIC_ROUTES if k in routes)
    assert not landed, f"move from RESERVED_PUBLIC_ROUTES to PUBLIC_ROUTES: {landed}"
    unlisted = sorted(k for k in routes if k.split(" ", 1)[1].startswith("/internal/") and k not in MACHINE_ROUTES)
    assert not unlisted, f"/internal/ routes must be listed in MACHINE_ROUTES: {unlisted}"


def test_machine_routes_authenticate_the_host():
    _, _, endpoints = _inventory()
    missing = sorted(k for k in MACHINE_ROUTES if MACHINE_GUARD not in inspect.getsource(endpoints[k]))
    assert not missing, f"/internal/ routes must call {MACHINE_GUARD}...): {missing}"


def test_ticket_routes_decide_ownership_and_their_issuer_declares_iam():
    routes, _, endpoints = _inventory()
    for key, issuer in TICKET_ROUTES.items():
        assert key.startswith("WS "), f"only WebSockets authenticate by ticket: {key}"
        assert TICKET_GUARD in inspect.getsource(endpoints[key]), f"{key} must call {TICKET_GUARD}...)"
        assert [d.kind for d in routes[issuer]] == ["require"], f"{issuer} issues the ticket of {key}"


def test_allowlists_do_not_grow():
    sizes = (
        len(PENDING_ROUTES),
        sum(n for n, _ in ADMIN_ALLOWLIST.values()),
        sum(n for n, _ in OWNER_ALLOWLIST.values()),
    )
    assert sizes == (PENDING_MAX, ADMIN_ALLOWLIST_MAX, OWNER_ALLOWLIST_MAX), (
        "allowlist sizes changed: never add entries; after removing some, lower the *_MAX ceiling"
    )


def test_engine_access_marks_only_routes_still_under_a_0009_guard():
    routes, guards, _ = _inventory()
    unguarded = sorted(
        k for k, decls in routes.items()
        if any(d.kind == "engine_access" for d in decls) and not guards[k] & ENGINE_GUARDS
    )
    assert not unguarded, f"engine_access() is a marker, not a guard: {unguarded}"


def test_authenticated_is_only_for_self_describing_routes():
    routes, _, _ = _inventory()
    declared = {k for k, decls in routes.items() if any(d.kind == "authenticated" for d in decls)}
    assert declared == AUTHENTICATED_ROUTES


def test_admin_routes_declare_their_platform_permission():
    routes, _, _ = _inventory()
    wrong = {}
    for key, (permission, session) in PLATFORM_ROUTES.items():
        got = [(d.kind, d.permission, d.session) for d in routes[key]]
        if got != [("require", permission, session)]:
            wrong[key] = got
    assert not wrong, f"administrative routes off their §4.7 permission: {wrong}"
    # No other /admin route is left on require(): the rest are 0009 engine routes.
    others = sorted(
        k for k, decls in routes.items()
        if k.split(" ", 1)[1].startswith("/admin/") and k not in PLATFORM_ROUTES
        and [d.kind for d in decls] != ["engine_access"]
    )
    assert not others, f"/admin routes neither in PLATFORM_ROUTES nor engine_access: {others}"


def test_the_0009_routes_are_in_the_inventory():
    routes, _, _ = _inventory()
    for key in (
        "GET /admin/engines",
        "GET /admin/gpus",
        "GET /admin/access/grants",
        "GET /admin/execution-profiles",
        "POST /admin/engines/{engine_id}/operations",
    ):
        assert [d.kind for d in routes[key]] == ["engine_access"], key


# ---------------------------------------------------------------------------
# CA2
# ---------------------------------------------------------------------------

# Scanned: api/ and workers/. Not scanned: shared/iam/ and shared/access/ (they
# *are* the decision points), shared/schemas.py (/auth/me serialization) and
# api/iam_deps.py (the dependencies of shared/iam/ itself).
SCANNED = ("api", "workers")
EXEMPT = {"api/iam_deps.py"}

ADMIN_PATTERN = re.compile(r"\bis_effective_admin\b|\.is_admin\b")
OWNER_PATTERN = re.compile(r"\buser_id\b\s*[!=]=|[!=]=\s*\S*\buser_id\b")

PENDING = "pending: converted in a later 0014 slice"

# (file, stripped line) -> (count, reason). May only shrink.
ADMIN_ALLOWLIST = {
    ("api/access_deps.py", "from shared.admin import is_effective_admin"): (1, "0009 access_session (CA13: unchanged)"),
    ("api/access_deps.py", 'if not is_effective_admin(user) and not policy.navigation(db, user)["permissions"]:'): (1, "0009 access_session (CA13: unchanged)"),
    ("api/access_routes.py", "if (target.is_active, target.is_admin) != ("): (1, "0009 subject state: edits the bootstrap column, decides nothing"),
    ("api/access_routes.py", "target.is_admin = body.is_admin"): (1, "0009 subject state: edits the bootstrap column, decides nothing"),
    ("api/access_routes.py", '{"is_active": target.is_active, "is_admin": target.is_admin},'): (1, "0009 subject state: audit payload"),
    ("api/access_routes.py", "return dict(id=target.id, is_active=target.is_active, is_admin=target.is_admin)"): (1, "0009 subject state: response"),
    ("api/admin_routes.py", "from shared.admin import is_effective_admin"): (1, PENDING + " (§8.7: require_admin now guards only the 0009 engine routes)"),
    ("api/admin_routes.py", "A user is an admin if EITHER the `users.is_admin` column is true (set with"): (1, PENDING + " (§8.7: require_admin docstring)"),
    ("api/admin_routes.py", "if not is_effective_admin(current_user, settings):"): (1, PENDING + " (§8.7: require_admin now guards only the 0009 engine routes)"),
    ("api/engine_admin_routes.py", "from shared.admin import is_effective_admin"): (1, "0009 credential re-auth (CA13: unchanged)"),
    ("api/engine_admin_routes.py", "if is_effective_admin(db.get(User, actor)):"): (1, "0009 credential re-auth (CA13: unchanged)"),
    ("api/image_routes.py", "from shared.admin import is_effective_admin"): (1, PENDING + " (§8.5 engines.remote.use)"),
    ("api/image_routes.py", "is_admin=is_effective_admin(current_user), session_factory=SessionLocal,"): (1, PENDING + " (§8.5 engines.remote.use)"),
    ("api/routes.py", "from shared.admin import is_effective_admin"): (1, PENDING + " (§8.5 engines.remote.use)"),
    ("api/routes.py", 'feature="transcription", job_id=str(job_id), user_id=user.id, is_admin=is_effective_admin(user),'): (1, PENDING + " (§8.5 engines.remote.use)"),
    ("api/routes.py", "is_admin=is_effective_admin(current_user),"): (1, PENDING + " (§8.5 engines.remote.use)"),
    ("api/routes.py", "user_id=current_user.id, is_admin=is_effective_admin(current_user),"): (1, PENDING + " (§8.5 engines.remote.use)"),
    ("workers/tasks.py", "from shared.admin import is_effective_admin"): (2, PENDING + " (§8.5 engines.remote.use)"),
    ("workers/tasks.py", "is_admin = is_effective_admin(job.user) if job is not None and job.user is not None else False"): (2, PENDING + " (§8.5 engines.remote.use)"),
}

OWNER_ALLOWLIST = {
    # Non-authorizing uses (permanent while the code stays as it is).
    ("api/auth_routes.py", "user = db.query(User).filter(User.id == user_id).first()"): (1, "token subject lookup, not an ownership check"),
    ("api/projects_api.py", "Job.user_id == user_id,"): (1, "upload idempotency: duplicate detection within the user's own jobs"),
    # Authorizing comparisons still inline: a key's project binding (0015 changes keys).
    ("api/apikey_routes.py", "if project is None or project.user_id != key.user_id:"): (1, PENDING + " (key binding, 0015)"),
    ("api/projects_api.py", "if project is None or project.user_id != user.id or api_key.user_id != user.id:"): (1, PENDING + " (key binding, 0015)"),
}


def _occurrences(pattern) -> Counter:
    found = Counter()
    for root in SCANNED:
        for path in sorted((BACKEND / root).rglob("*.py")):
            rel = path.relative_to(BACKEND).as_posix()
            if rel in EXEMPT:
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                if pattern.search(line):
                    found[(rel, line.strip())] += 1
    return found


def _check(pattern, allowlist, what):
    found = _occurrences(pattern)
    allowed = Counter({k: n for k, (n, _reason) in allowlist.items()})
    new = {k: n for k, n in found.items() if n > allowed.get(k, 0)}
    stale = {k: n for k, n in allowed.items() if found.get(k, 0) < n}
    assert not new, f"{what} outside shared/iam (decide through api.iam_deps / shared.iam): {new}"
    assert not stale, f"the allowlist only shrinks: lower or remove these entries: {stale}"


def test_ca2_no_inline_admin_checks_outside_iam():
    _check(ADMIN_PATTERN, ADMIN_ALLOWLIST, "is_effective_admin / .is_admin")


def test_ca2_no_inline_ownership_comparisons_outside_iam():
    _check(OWNER_PATTERN, OWNER_ALLOWLIST, "user_id comparison")


def test_ca2_patterns_catch_what_they_must():
    assert ADMIN_PATTERN.search("if is_effective_admin(user):")
    assert ADMIN_PATTERN.search("if current_user.is_admin:")
    assert not ADMIN_PATTERN.search("is_admin=False")
    for line in ("Job.user_id == current_user.id", "if job.user_id != user.id:", "if me == job.user_id:"):
        assert OWNER_PATTERN.search(line), line
    assert not OWNER_PATTERN.search("user_id=current_user.id")
