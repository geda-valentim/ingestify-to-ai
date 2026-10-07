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
    "GET /auth/registration-settings",
    # Authenticated by a single-use ticket bound to the session, not by a user.
    "WS /transcribe/live/sessions/{job_id}/stream",
}
# Machine identities (engine hosts), never a user session.
PUBLIC_PREFIXES = ("/internal/",)
# FastAPI's own documentation routes.
DOCS_PATHS = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}

# Routes still on their legacy guard. Converted in spec 0014 §8 items 3 and 4;
# this set may only shrink.
PENDING_ROUTES = {
    # Session-only routes (§4.9): a declaration for "any authenticated user" comes with /iam/*.
    "GET /auth/me",
    # §8.3: administrative routes (§4.7)
    "GET /admin/stats",
    "GET /admin/jobs/stuck",
    "POST /admin/jobs/recover-stuck",
    "POST /admin/jobs/{job_id}/retry-all-failed",
    "POST /admin/cleanup",
    "GET /admin/health/monitoring",
    "GET /admin/broker/unacked",
    "POST /admin/broker/unacked/{delivery_tag}/requeue",
    "GET /admin/routing",
    "PUT /admin/routing/{feature}",
    "DELETE /admin/routing/{feature}",
    "GET /admin/engines/status",
    # §8.4: data routes by id and listings
    "POST /api-keys/",
    "GET /api-keys/",
    "PATCH /api-keys/{key_id}",
    "DELETE /api-keys/{key_id}",
    "POST /images/describe",
    "POST /images/describe/upload",
    "POST /images/ocr",
    "POST /images/ocr/upload",
    "GET /images/capabilities",
    "GET /tags",
    "PUT /jobs/{job_id}/tags",
    "GET /projects",
    "GET /projects/resolve",
    "GET /projects/{project_id}/folders/resolve",
    "POST /transcribe/live/sessions",
    "GET /transcribe/live/sessions/{job_id}",
    "DELETE /transcribe/live/sessions/{job_id}",
    "POST /upload",
    "POST /transcribe",
    "POST /convert",
    "GET /jobs",
    "GET /search",
    "GET /jobs/{job_id}",
    "DELETE /jobs/{job_id}",
    "GET /jobs/{job_id}/result",
    "GET /jobs/{job_id}/transcript/partial",
    "GET /jobs/{job_id}/pages",
    "GET /jobs/{job_id}/pages/{page_number}/status",
    "GET /jobs/{job_id}/pages/{page_number}/result",
    "POST /jobs/{job_id}/pages/{page_number}/retry",
    "GET /jobs/{job_id}/pages/{page_number}/pdf",
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
    routes, guards = {}, {}
    for route in app.routes:
        if isinstance(route, (APIRoute, APIWebSocketRoute)):
            calls = _calls(route.dependant)
            decls = [d for d in (declaration_of(c) for c in calls) if d is not None]
            names = {getattr(c, "__name__", "") for c in calls}
            methods = sorted(route.methods) if isinstance(route, APIRoute) else ["WS"]
            for method in methods:
                key = f"{method} {route.path}"
                assert key not in routes, f"duplicate route {key}"
                routes[key], guards[key] = decls, names
        elif isinstance(route, Route) and route.path in DOCS_PATHS:
            continue
        else:
            raise AssertionError(f"unexpected route type {type(route).__name__} at {getattr(route, 'path', '?')}")
    return routes, guards


def _public(key: str) -> bool:
    path = key.split(" ", 1)[1]
    return key in PUBLIC_ROUTES or path.startswith(PUBLIC_PREFIXES)


def test_every_route_declares_exactly_one_authorization():
    routes, _ = _inventory()
    wrong = {}
    for key, decls in routes.items():
        if _public(key) or key in PENDING_ROUTES:
            continue
        if len(decls) != 1:
            wrong[key] = [d.kind for d in decls]
    assert not wrong, f"routes without exactly one IAM declaration: {wrong}"


def test_public_routes_declare_nothing():
    routes, _ = _inventory()
    declared = {k: d for k, d in routes.items() if _public(k) and d}
    assert not declared, f"a public route cannot also declare a permission: {declared}"


def test_pending_allowlist_only_shrinks():
    routes, _ = _inventory()
    gone = sorted(k for k in PENDING_ROUTES if k not in routes)
    assert not gone, f"remove from PENDING_ROUTES, the route no longer exists: {gone}"
    converted = sorted(k for k in PENDING_ROUTES if routes[k])
    assert not converted, f"remove from PENDING_ROUTES, the route now declares IAM: {converted}"
    public = sorted(k for k in PENDING_ROUTES if _public(k))
    assert not public, f"a route cannot be both public and pending: {public}"


def test_engine_access_marks_only_routes_still_under_a_0009_guard():
    routes, guards = _inventory()
    unguarded = sorted(
        k for k, decls in routes.items()
        if any(d.kind == "engine_access" for d in decls) and not guards[k] & ENGINE_GUARDS
    )
    assert not unguarded, f"engine_access() is a marker, not a guard: {unguarded}"


def test_the_0009_routes_are_in_the_inventory():
    routes, _ = _inventory()
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
    ("api/admin_routes.py", "from shared.admin import is_effective_admin"): (1, PENDING + " (§8.3 require_admin)"),
    ("api/admin_routes.py", "A user is an admin if EITHER the `users.is_admin` column is true (set with"): (1, PENDING + " (§8.3 require_admin docstring)"),
    ("api/admin_routes.py", "if not is_effective_admin(current_user, settings):"): (1, PENDING + " (§8.3 require_admin)"),
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
    # Authorizing filters still inline: converted to visible()/authorized() in §8.4.
    ("api/apikey_routes.py", "if project is None or project.user_id != key.user_id:"): (1, PENDING + " (key binding, 0015)"),
    ("api/apikey_routes.py", "keys = db.query(APIKey).filter(APIKey.user_id == current_user.id).all()"): (1, PENDING + " (visible(APIKey))"),
    ("api/apikey_routes.py", "projects = {p.id: p for p in db.query(Project).filter(Project.user_id == current_user.id)}"): (1, PENDING + " (visible(Project))"),
    ("api/apikey_routes.py", "APIKey.user_id == current_user.id"): (2, PENDING + " (authorized(APIKey))"),
    ("api/live_routes.py", "if not job or not owner or not owner.is_active or job.user_id != binding['user_id'] or not live or live.generation != generation or live.state != 'created':"): (1, PENDING + " (WS ticket binding)"),
    ("api/projects_api.py", "if project is None or project.user_id != user.id or api_key.user_id != user.id:"): (1, PENDING + " (key binding, 0015)"),
    ("api/projects_api.py", "projects = db.query(Project).filter(Project.user_id == current_user.id).all()"): (1, PENDING + " (visible(Project))"),
    ("api/projects_api.py", '.filter(Job.user_id == current_user.id, Job.job_type == "MAIN", Job.project_id.isnot(None))'): (1, PENDING + " (visible(Job))"),
    ("api/projects_api.py", ".filter(APIKey.user_id == current_user.id, APIKey.project_id.isnot(None))"): (1, PENDING + " (visible(APIKey))"),
    ("api/projects_api.py", "for folder in db.query(Folder).filter(Folder.user_id == current_user.id).all():"): (1, PENDING + " (visible(Folder))"),
    ("api/routes.py", "query = db.query(Job).filter(Job.user_id == current_user.id)"): (1, PENDING + " (visible(Job), GET /jobs)"),
    ("api/routes.py", ".filter(Job.id.in_(live_ids), Job.user_id == current_user.id,"): (1, PENDING + " (visible(Job))"),
    ("api/tag_routes.py", ".filter(Job.user_id == current_user.id)"): (1, PENDING + " (visible(Job), GET /tags)"),
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
