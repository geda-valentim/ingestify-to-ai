"""
Spec 0018 CA8: `/admin/access/grants*` are deprecated aliases with the 0009 contract.

The routes now write `iam_bindings` through `shared.iam.bindings`; this module
proves their contract did not move, against the behaviour **before 0018**:

- `ALIAS_SCENARIOS` runs one fixed sequence of requests (grants, delegation,
  every refusal code, revocation and re-revocation, the flag off) and records,
  per request, the status and the raw response body with only the generated ids
  and the timestamps replaced by placeholders. `PRE_0018_TRANSCRIPT` is that
  record captured on the pre-0018 tree (commit bca96be, `access_role_grants`
  storage): the bodies must stay byte-identical.
- `PRE_0018_OPENAPI` is the OpenAPI of the three routes captured on the same
  tree: the only change allowed is `deprecated: true` on each operation.

The one intentional deviation (0018 §4.5, CA8) is listed in `DEVIATIONS`: a
self-grant, accepted by 0009 (201 in the capture), is now 422 SELF_GRANT.

Refusals also gained additive, human guidance (0009 CA1, `shared.error_catalog`):
`message` became Portuguese text instead of the bare code, plus `next_steps`
(and `cause`/`technical` when present). Those keys are compared apart: every other
byte of the body — `code` included — must still match the capture.
"""

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI

from shared.access import contracts as C, policy, service
from shared.config import get_settings
from shared.iam import bindings, migration
from shared.iam.models import IamBinding
from shared.models import AdminAudit
from tests.test_execution_profiles import HEADERS, client, constraints, world  # noqa: F401

ALIAS_PATHS = ("/admin/access/grants", "/admin/access/grants/{id}/revoke")

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_TS = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?")


class _Normalizer:
    """Generated ids become `<idN>` by first appearance; timestamps become `<ts>`."""

    def __init__(self):
        self.ids = {}

    def _id(self, m):
        return self.ids.setdefault(m.group(0), f"<id{len(self.ids)}>")

    def __call__(self, text: str) -> str:
        return _TS.sub("<ts>", _UUID.sub(self._id, text))


def _later(**delta) -> str:
    return (datetime.now(timezone.utc) + timedelta(**delta)).isoformat()


SELF_GRANT = "self grant"


def alias_scenarios(world, http, actor):  # noqa: F811
    """[label, status, normalized body] for each request of the fixed sequence."""
    norm = _Normalizer()
    out = []

    def call(label, who, method, path, body=None, headers=HEADERS):
        actor["id"] = who
        r = http.request(method, path, headers=headers, json=body)
        out.append([label, r.status_code, norm(r.text)])
        return r

    with world() as db:
        p = service.create_policy(db, C.PolicyCreate(name="Alias policy", constraints=constraints()), "bootstrap")
    revision = p["revisions"][0]["id"]
    envelope = {
        "permissions": sorted(policy.ROLES["observer"]),
        "constraints": constraints().model_dump(mode="json"),
        "max_grant_seconds": 1800,
    }

    def body(user="observer", role="observer", **kw):
        return {"user_id": user, "role": role, "policy_revision_id": revision, "expires_at": _later(minutes=30), **kw}

    grants = "/admin/access/grants"
    call("list empty", "bootstrap", "GET", grants)
    observer = call("grant observer", "bootstrap", "POST", grants, body()).json()
    call("grant subset", "bootstrap", "POST", grants, body("operator", "engine_operator", permissions=["engines.read"]))
    call("grant same role again", "bootstrap", "POST", grants, body())
    call("unknown role", "bootstrap", "POST", grants, body(role="wizard"))
    call("platform role", "bootstrap", "POST", grants, body(role="platform_admin"))
    call("outside role", "bootstrap", "POST", grants, body(permissions=["access.grants.manage"]))
    call("empty permissions", "bootstrap", "POST", grants, body(permissions=[]))
    call("missing user", "bootstrap", "POST", grants, body(user="nobody"))
    call("missing revision", "bootstrap", "POST", grants, body(policy_revision_id="no-such-revision"))
    call("past expiry", "bootstrap", "POST", grants, body(expires_at=_later(minutes=-1)))
    call("expiry over a year", "bootstrap", "POST", grants, body(expires_at=_later(days=366)))
    call("naive expiry", "bootstrap", "POST", grants, body(expires_at="2099-01-01T00:00:00"))
    call("unknown field", "bootstrap", "POST", grants, body(subject_type="user"))
    call("delegation on observer", "bootstrap", "POST", grants, body(delegation=envelope))
    call(
        "delegation outside the catalog",
        "bootstrap", "POST", grants,
        body("delegate", "access_admin", delegation={**envelope, "permissions": ["platform.stats.read"]}),
    )
    call("delegate", "bootstrap", "POST", grants, body("delegate", "access_admin", delegation=envelope))
    call("delegated grant", "delegate", "POST", grants, body("editor", expires_at=_later(minutes=10)))
    call("delegated grant too long", "delegate", "POST", grants, body("editor"))
    call("delegated grant above envelope", "delegate", "POST", grants, body("editor", "engine_operator"))
    call("delegate lists", "delegate", "GET", grants)
    call("observer lists", "observer", "GET", grants)
    call("outsider lists", "outsider", "GET", grants)
    call("outsider grants", "outsider", "POST", grants, body("editor"))
    call("api key", "bootstrap", "GET", grants, headers={**HEADERS, "X-API-Key": "k"})
    call("no session", "bootstrap", "POST", grants, body(), headers={})

    revoke = f"{grants}/{observer['id']}/revoke"
    call("revoke stale version", "bootstrap", "POST", revoke, {"version": 7})
    call("revoke", "bootstrap", "POST", revoke, {"version": 0})
    call("revoke again", "bootstrap", "POST", revoke, {"version": 1})
    call("revoke missing", "bootstrap", "POST", f"{grants}/no-such-grant/revoke", {"version": 0})
    call("revoke bad body", "bootstrap", "POST", revoke, {"version": -1})
    call("outsider revokes", "outsider", "POST", revoke, {"version": 2})
    call("list everything", "bootstrap", "GET", grants)

    settings = get_settings()
    settings.engine_access_enabled = False
    try:
        call("off: list", "bootstrap", "GET", grants)
        call("off: grant", "bootstrap", "POST", grants, body())
        call("off: revoke", "bootstrap", "POST", revoke, {"version": 2})
    finally:
        settings.engine_access_enabled = True
    # Last, so no row above depends on it: the one listed deviation (`DEVIATIONS`).
    call(SELF_GRANT, "bootstrap", "POST", grants, body("bootstrap"))
    return out


def _refs(node, found):
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            found.add(ref.rsplit("/", 1)[-1])
        for v in node.values():
            _refs(v, found)
    elif isinstance(node, list):
        for v in node:
            _refs(v, found)


def alias_openapi() -> dict:
    """The OpenAPI operations of the alias routes and every schema they reach."""
    from api.access_routes import router

    app = FastAPI()
    app.include_router(router)
    spec = app.openapi()
    paths = {p: spec["paths"][p] for p in ALIAS_PATHS}
    schemas, names = {}, set()
    _refs(paths, names)
    while names - set(schemas):
        for name in sorted(names - set(schemas)):
            schemas[name] = spec["components"]["schemas"][name]
            _refs(schemas[name], names)
    return {"paths": paths, "schemas": dict(sorted(schemas.items()))}


# -- CA8: the contract, against the pre-0018 capture ----------------------------------

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PRE_0018_TRANSCRIPT = FIXTURES / "pre_0018_access_grants_transcript.json"
PRE_0018_OPENAPI = FIXTURES / "pre_0018_access_grants_openapi.json"

# 0018 §4.5 / CA8: the only behaviour of the aliases that changed, on purpose — the
# label of its row and the answer now. What it answered before is the capture's.
DEVIATIONS = {
    SELF_GRANT: (422, json.dumps({"detail": {"code": "SELF_GRANT", "message": "SELF_GRANT"}}, separators=(",", ":"))),
}


def _pre_0018():
    return json.loads(PRE_0018_TRANSCRIPT.read_text())


_GUIDANCE = ("message", "next_steps", "cause", "technical")


def _without_guidance(body):
    """The body with the additive 0009 CA1 guidance keys of a coded refusal removed."""
    data = json.loads(body)
    detail = data.get("detail") if isinstance(data, dict) else None
    if isinstance(detail, dict) and "code" in detail:
        data["detail"] = {k: v for k, v in detail.items() if k not in _GUIDANCE}
    return json.dumps(data, separators=(",", ":"))


def test_the_aliases_answer_byte_for_byte_as_before_0018(world, client):  # noqa: F811
    http, actor = client
    expected = _pre_0018()
    got = alias_scenarios(world, http, actor)
    assert [row[0] for row in got] == [row[0] for row in expected]
    for (label, status, body), (_, old_status, old_body) in zip(got, expected):
        old_status, old_body = DEVIATIONS.get(label, (old_status, old_body))
        if old_body == body:
            continue
        assert (status, _without_guidance(body)) == (old_status, _without_guidance(old_body)), label
        detail = json.loads(body)["detail"]
        # The guidance is real text, never the bare code again.
        assert detail["message"] and detail["message"] != detail["code"], label
        assert isinstance(detail["next_steps"], list), label


def test_a_self_grant_is_the_one_listed_deviation():
    """Before 0018 the self-grant was accepted (201, the grant); every other row is unchanged."""
    old = {label: (status, json.loads(body)) for label, status, body in _pre_0018()}
    status, granted = old[SELF_GRANT]
    assert status == 201
    assert (granted["user_id"], granted["role"]) == ("bootstrap", "observer")
    assert set(DEVIATIONS) == {SELF_GRANT}
    assert DEVIATIONS[SELF_GRANT][0] != status


def test_the_alias_openapi_is_the_pre_0018_one_marked_deprecated():
    expected = json.loads(PRE_0018_OPENAPI.read_text())
    for operations in expected["paths"].values():
        for operation in operations.values():
            assert "deprecated" not in operation
            operation["deprecated"] = True
    assert alias_openapi() == expected


def test_the_aliases_neither_list_nor_revoke_platform_bindings(world, client):  # noqa: F811
    http, actor = client
    with world() as db:
        b = IamBinding(subject_type="user", subject_id="outsider", role="platform_auditor",
                       scope_type="platform", granted_by="bootstrap",
                       expires_at=datetime.utcnow() + timedelta(days=1), version=0)
        db.add(b)
        db.commit()
        platform_id = b.id
    actor["id"] = "bootstrap"
    assert http.get("/admin/access/grants", headers=HEADERS).json() == []
    r = http.post(f"/admin/access/grants/{platform_id}/revoke", headers=HEADERS, json={"version": 0})
    assert (r.status_code, r.json()["detail"]["code"]) == (404, "GRANT_NOT_FOUND")


def test_alias_writes_are_audited_on_iam_binding(world, client):  # noqa: F811
    """CA12: the 0009 information (subject, role, policy revision, parent) on the IAM target."""
    http, actor = client
    with world() as db:
        p = service.create_policy(db, C.PolicyCreate(name="Audit", constraints=constraints()), "bootstrap")
    revision = p["revisions"][0]["id"]
    actor["id"] = "bootstrap"
    g = http.post("/admin/access/grants", headers=HEADERS, json={
        "user_id": "observer", "role": "observer", "policy_revision_id": revision,
        "expires_at": _later(minutes=30)}).json()
    assert http.post(f"/admin/access/grants/{g['id']}/revoke", headers=HEADERS, json={"version": 0}).status_code == 200
    with world() as db:
        rows = db.query(AdminAudit).filter_by(target_id=g["id"]).order_by(AdminAudit.created_at, AdminAudit.id).all()
        assert [(r.target_type, r.action, r.actor_user_id) for r in rows] == [
            ("iam_binding", bindings.GRANT_AUDIT_ACTION, "bootstrap"),
            ("iam_binding", bindings.REVOKE_AUDIT_ACTION, "bootstrap"),
        ]
        granted, revoked = rows
        assert {k: granted.after[k] for k in ("family", "subject_id", "role", "condition_ref", "parent_id")} == {
            "family": "engines", "subject_id": "observer", "role": "observer",
            "condition_ref": revision, "parent_id": None,
        }
        assert (revoked.before["revoked_at"], revoked.after["version"]) == (None, 1)
        assert revoked.after["revoked_at"] is not None
        assert db.query(AdminAudit).filter_by(target_type="access", action="access.granted").count() == 0
    # The migration reads the revoker of a binding from this very row (§4.2.2).
    assert bindings.REVOKE_AUDIT_ACTION == migration.REVOKE_AUDIT_ACTION
