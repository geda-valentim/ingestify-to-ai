"""
The closed permission catalog and the managed roles (spec 0014 §4.2, §4.3).

Both live in code, not in a table: changing a role is a reviewed deploy, and there
is no second source of truth editable by SQL. Custom roles arrive with 0017.

Levels in this slice:

- `owner`    — data of the user's own space. Decided by ownership, never by a
               binding (0014 §4.4 step 4). Creation is open to every active user.
- `platform` — cross-user administration, granted by platform roles.
- `iam`      — managing the bindings themselves.

Engine permissions of spec 0009 are only *referenced* here: they stay in
`shared.access.policy` and are never decided by `shared.iam.decide`.

Role families (spec 0018 §4.1): `ROLES` holds the `platform` family only. The six
0009 roles are the `engines` family, in the separate map `ENGINE_ROLES`, whose
permissions are read from `shared.access.policy.ROLES` (one source). They never
enter `ROLES`: the `Decider`, `platform_roles`, `/iam/check` and
`ROLE_ABOVE_GRANTOR` must never see an engine binding (0018 CA13). Engine
bindings are decided by `shared.access.policy.authorize` (0009 semantics), which
reads them from `iam_bindings` through `shared.iam.engine_bindings`.
"""

from dataclasses import dataclass
from typing import Dict, FrozenSet, Optional, Tuple

from shared.access.policy import PERMISSIONS as ENGINE_PERMISSIONS
from shared.access.policy import ROLES as _POLICY_ROLES

OWNER = "owner"
PLATFORM = "platform"
IAM = "iam"


@dataclass(frozen=True)
class Permission:
    name: str
    family: str
    level: str
    # Mutations exercised through bootstrap are audited (CA8). Reads are not.
    mutation: bool
    # Owner-level permissions an active user holds without a resource: creating
    # something in their own space (0014 §4.2 "criação: todo usuário ativo").
    self_service: bool = False
    description: str = ""


def _data(name: str, *, mutation: bool, self_service: bool = False) -> Permission:
    return Permission(name, "data", OWNER, mutation, self_service)


_DATA = [
    _data("jobs.read", mutation=False),
    _data("jobs.create", mutation=True, self_service=True),
    _data("jobs.update", mutation=True),
    _data("jobs.retry", mutation=True),
    _data("jobs.cancel", mutation=True),
    _data("jobs.delete", mutation=True),
    _data("projects.read", mutation=False),
    _data("projects.create", mutation=True, self_service=True),
    _data("projects.update", mutation=True),
    _data("projects.delete", mutation=True),
    _data("folders.read", mutation=False),
    _data("folders.create", mutation=True, self_service=True),
    _data("folders.update", mutation=True),
    _data("folders.delete", mutation=True),
    _data("datalakes.read", mutation=False),
    _data("datalakes.create", mutation=True, self_service=True),
    _data("datalakes.update", mutation=True),
    _data("datalakes.delete", mutation=True),
    _data("datalakes.use", mutation=True),
    _data("datalake_exports.retry", mutation=True),
    _data("api_keys.read", mutation=False),
    _data("api_keys.manage", mutation=True, self_service=True),
    _data("search.query", mutation=False, self_service=True),
    _data("documents.convert", mutation=True, self_service=True),
    _data("audio.transcribe", mutation=True, self_service=True),
    _data("images.analyze", mutation=True, self_service=True),
    _data("live.sessions.create", mutation=True, self_service=True),
]

_PLATFORM = [
    Permission("platform.stats.read", "platform", PLATFORM, False),
    # Metadata of every user's jobs (id, status, filename, user_id): /admin/jobs/stuck.
    Permission("platform.jobs.read", "platform", PLATFORM, False),
    Permission("platform.jobs.recover", "platform", PLATFORM, True),
    # Deletes old jobs of every user; platform_admin only (0014 §9).
    Permission("platform.jobs.cleanup", "platform", PLATFORM, True),
    Permission("platform.monitoring.read", "platform", PLATFORM, False),
    Permission("platform.broker.requeue", "platform", PLATFORM, True),
    Permission("platform.settings.read", "platform", PLATFORM, False),
    Permission("platform.settings.update", "platform", PLATFORM, True),
    Permission("platform.routing.read", "platform", PLATFORM, False),
    Permission("platform.routing.update", "platform", PLATFORM, True),
    Permission("platform.audit.read", "platform", PLATFORM, False),
    # Checked per remote placement by the dispatcher. It is a use, not an
    # administrative change: auditing it would write one row per page.
    Permission("engines.remote.use", "platform", PLATFORM, False),
]

_IAM = [
    Permission("iam.bindings.read", "iam", IAM, False),
    Permission("iam.bindings.manage", "iam", IAM, True),
]

PERMISSIONS: Dict[str, Permission] = {p.name: p for p in _DATA + _PLATFORM + _IAM}

PLATFORM_PERMISSIONS: FrozenSet[str] = frozenset(
    name for name, p in PERMISSIONS.items() if p.level in (PLATFORM, IAM)
)
DATA_PERMISSIONS: FrozenSet[str] = frozenset(
    name for name, p in PERMISSIONS.items() if p.level == OWNER
)

assert not set(PERMISSIONS) & ENGINE_PERMISSIONS, "IAM and 0009 permission names overlap"


def _reads(*prefixes: str) -> FrozenSet[str]:
    return frozenset(
        n for n in PLATFORM_PERMISSIONS
        if n.startswith(prefixes) and n.endswith(".read")
    )


PLATFORM_FAMILY = "platform"
ENGINES_FAMILY = "engines"


@dataclass(frozen=True)
class Role:
    key: str
    permissions: FrozenSet[str]
    description: str
    family: str = PLATFORM_FAMILY


ROLES: Dict[str, Role] = {
    role.key: role
    for role in [
        Role(
            "platform_admin",
            frozenset(n for n in PLATFORM_PERMISSIONS),
            "Every platform.*, iam.* and engines.remote.use",
        ),
        Role(
            "platform_operator",
            frozenset({
                "platform.stats.read",
                "platform.jobs.read",
                "platform.jobs.recover",
                "platform.monitoring.read",
                "platform.broker.requeue",
                "platform.routing.read",
            }),
            "Recovers stuck work and watches the platform; changes no setting",
        ),
        Role(
            "platform_auditor",
            _reads("platform.") | {"iam.bindings.read"},
            "Read-only: every platform.*.read and iam.bindings.read",
        ),
        Role(
            "remote_engine_user",
            frozenset({"engines.remote.use"}),
            "May have work placed on remote (paid) engines",
        ),
    ]
}

# Bootstrap (users.is_admin / ADMIN_USER_IDS) is equivalent to this role and is
# never represented by a binding.
BOOTSTRAP_ROLE = "platform_admin"

for _role in ROLES.values():
    assert _role.permissions <= PLATFORM_PERMISSIONS, _role.key


_ENGINE_ROLE_DESCRIPTIONS = {
    "observer": "Reads engines, execution profiles and operations within its condition",
    "profile_editor": "Creates, revises, publishes and archives execution profiles",
    "runtime_configurator": "Binds published profiles to engine runtimes",
    "engine_operator": "Plans, executes, cancels and recovers engine operations",
    "access_admin": "Grants engine roles within its delegation envelope",
    "connection_manager": "Manages engine connection credentials",
}

# The 0009 roles (family `engines`). Permissions come from `policy.ROLES`, never a
# copy: an engine binding still carries its own materialized `permissions`.
ENGINE_ROLES: Dict[str, Role] = {
    key: Role(key, frozenset(perms), _ENGINE_ROLE_DESCRIPTIONS.get(key, ""), ENGINES_FAMILY)
    for key, perms in _POLICY_ROLES.items()
}

assert not set(ENGINE_ROLES) & set(ROLES), "platform and engines role keys overlap"
for _role in ENGINE_ROLES.values():
    assert _role.permissions <= ENGINE_PERMISSIONS, _role.key


def family(role_key: str) -> Optional[str]:
    """`platform`, `engines`, or None for a key in neither family."""
    if role_key in ROLES:
        return PLATFORM_FAMILY
    if role_key in ENGINE_ROLES:
        return ENGINES_FAMILY
    return None


def permission(name: str) -> Permission:
    """The catalog entry, or KeyError for a name outside the closed catalog."""
    return PERMISSIONS[name]


def role(key: str) -> Role:
    """The managed platform role, or KeyError for an unknown key (engines included)."""
    return ROLES[key]


def is_engine_permission(name: str) -> bool:
    """A 0009 permission: decided by shared.access.policy, never by this package."""
    return name in ENGINE_PERMISSIONS


def roles_granting(name: str) -> Tuple[str, ...]:
    return tuple(sorted(k for k, r in ROLES.items() if name in r.permissions))


def describe() -> dict:
    """The catalog as served by GET /iam/permissions."""
    return {
        "permissions": [
            {
                "name": p.name,
                "family": p.family,
                "level": p.level,
                "mutation": p.mutation,
            }
            for p in PERMISSIONS.values()
        ],
        "roles": [
            {
                "key": r.key,
                "family": r.family,
                "permissions": sorted(r.permissions),
                "description": r.description,
            }
            for r in list(ROLES.values()) + list(ENGINE_ROLES.values())
        ],
    }
