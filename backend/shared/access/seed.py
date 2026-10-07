"""
Default execution profiles of an installation (spec 0020).

Seeds, as the root user, a published profile for every approved catalog model
("Padrão — <model>") and for every engine x feature already configured
("<engine> — <feature>"), then binds each engine profile to its engine when that
engine/feature has no runtime profile yet. Everything goes through the library
service (`create_profile`, `publish`, `bind`, `set_attributes`): validation,
model fingerprint, epoch and audit stay the same as through the API. Seeding and
binding never create a plan, operation, outbox row or reservation.

Idempotency key: the `seed_key` in the `execution_profile.created` audit row, which
`create_profile` writes in the same transaction as the profile. Each step re-reads
it under the authorization epoch lock, so concurrent seeders (several API workers
booting at once) serialize instead of creating duplicates. An archived seeded
profile is left alone: archiving is the admin's way of saying "not this one".

Usage (inside the api container):
    python -m shared.access.seed [--dry-run] [--json]
    python scripts/seed_execution_profiles.py [--dry-run] [--json]
"""

import copy
import logging
from datetime import timedelta
from dataclasses import asdict, dataclass, field
from typing import Optional

from pydantic import ValidationError

from shared.config import get_settings
from shared.models import ROOT_SLOT, AdminAudit, Engine, User
from shared.admin import is_effective_admin
from shared.engine_control import catalog, registry
from shared.engine_control import service as control
from shared.engine_control.contracts import RuntimeSettings
from shared.engine_control.models import ControlHost
from shared.access import contracts as C, policy, service
from shared.access.models import EngineAttributes, ExecutionProfile, ExecutionRevision

logger = logging.getLogger(__name__)

ORIGIN = "seed"
MODAL_DEFAULT_GPU = "L4"  # the GPU the engine console and benchmarks default to
HOST_READY_SECONDS = 30  # local driver: a host agent seen longer ago is not ready


def reason_text(code):
    """Portuguese text for a skip/failure code, from the single error catalog."""
    from shared.error_catalog import describe

    message, _ = describe(code)
    return message or f"Falha: {code}"


@dataclass
class SeedReport:
    """What a seeding run did (or, with dry_run, would do); `skipped` carries the reason"""

    dry_run: bool = False
    created: list = field(default_factory=list)
    published: list = field(default_factory=list)
    bound: list = field(default_factory=list)
    skipped: list = field(default_factory=list)

    def skip(self, key, reason, stage="create", **extra):
        self.skipped.append(
            dict(key=key, stage=stage, reason=reason, message=reason_text(reason), **extra)
        )

    def as_dict(self):
        return asdict(self)

    def summary(self):
        verb = "would be " if self.dry_run else ""
        lines = [
            f"execution profiles: {len(self.created)} {verb}created, "
            f"{len(self.published)} {verb}published, {len(self.bound)} {verb}bound, "
            f"{len(self.skipped)} skipped"
        ]
        for title, rows in (
            ("created", self.created),
            ("published", self.published),
            ("bound", self.bound),
        ):
            for r in rows:
                lines.append(f"  {title:<9} {r['key']}  {r.get('name', '')}".rstrip())
        for r in self.skipped:
            lines.append(
                f"  skipped   {r['key']} [{r['stage']}] {r['reason']}: {r['message']}"
            )
        return "\n".join(lines)


def installation_environment():
    """ENVIRONMENT as an access environment; unknown values count as production"""
    value = (get_settings().environment or "").strip().lower()
    if value in ("development", "staging", "production"):
        return value
    return "development" if value.startswith("dev") else "production"


def root_user(db) -> Optional[User]:
    return db.query(User).filter(User.root_slot == ROOT_SLOT).first()


def _code(exc):
    if isinstance(exc, control.ControlError):
        return exc.code
    if isinstance(exc, ValidationError):
        return "INVALID_SETTINGS"
    text = str(exc).strip() or type(exc).__name__
    return text.splitlines()[0][:200]


def _audit(key):
    return {"origin": ORIGIN, "seed_key": key}


def _seeded(db, key) -> Optional[ExecutionProfile]:
    """The profile seeded under `key`, if any (it survives renames and archiving)"""
    rows = db.query(AdminAudit).filter(
        AdminAudit.action == "execution_profile.created",
        AdminAudit.target_type == "access",
    )
    for row in rows:
        if isinstance(row.after, dict) and row.after.get("seed_key") == key:
            p = db.get(ExecutionProfile, row.target_id)
            if p is not None:
                return p
    return None


def _host(db) -> Optional[ControlHost]:
    """The registered host agent last seen; local profiles name a concrete host"""
    return (
        db.query(ControlHost)
        .order_by(ControlHost.seen_at.desc(), ControlHost.id)
        .first()
    )


def _runtime(binding, model_id, provider_settings):
    workers = binding["workers"]
    # Same defaults as the engine console form (frontend engine-control.tsx).
    return dict(
        adapter_version=1,
        schema_version=1,
        binding=binding,
        model_profile_id=model_id,
        desired_replicas=workers,
        max_replicas=workers,
        min_ready_replicas=0,
        idle_timeout_seconds=60,
        memory_mb=None,
        warmup_mode="on_start",
        warm_until=None,
        provider_settings=provider_settings,
    )


def _provider_settings(db, adapter, report, key):
    """provider_settings for `adapter`, or None (and a skip) when they cannot be known"""
    fields = [f["name"] for f in registry.descriptor(adapter)["provider_fields"]]
    if not fields:
        return {}
    if adapter == "local":
        host = _host(db)
        if host is None:
            report.skip(key, "NO_REGISTERED_HOST")
            return None
        return {"host_id": host.id}
    report.skip(key, "PROVIDER_SETTINGS_REQUIRED")
    return None


def _approved_model(adapter, feature):
    return next(
        (
            m
            for m in catalog.profiles()
            if m["approved"] and m["feature"] == feature and adapter in m["adapters"]
        ),
        None,
    )


def catalog_plans(db, report):
    """One plan per approved catalog model x adapter (CA1)"""
    plans = []
    env = installation_environment()
    for m in catalog.profiles():
        for adapter in m["adapters"]:
            key = f"catalog:{m['id']}:{adapter}"
            if not m["approved"]:
                report.skip(key, "MODEL_NOT_APPROVED")
                continue
            try:
                d = registry.descriptor(adapter)
            except ValueError:
                report.skip(key, "ADAPTER_NOT_REGISTERED")
                continue
            if m["feature"] not in d["features"]:
                report.skip(key, "FEATURE_NOT_SUPPORTED")
                continue
            provider = _provider_settings(db, adapter, report, key)
            if provider is None:
                continue
            binding = {"workers": 1, "executions_per_worker": 1}
            if adapter == "modal":
                binding["gpu_type"] = MODAL_DEFAULT_GPU
            title = m["title"] if len(m["adapters"]) == 1 else f"{m['title']} ({adapter})"
            plans.append(
                dict(
                    key=key,
                    name=f"Padrão — {title}"[:100],
                    description=(
                        "Perfil padrão do catálogo, criado na instalação "
                        f"(seed {key}). Revise GPU e réplicas antes de vincular."
                    ),
                    adapter=adapter,
                    feature=m["feature"],
                    environment=env,
                    settings=_runtime(binding, m["id"], provider),
                    engine_id=None,
                )
            )
    return plans


def engine_plans(db, report):
    """One plan per engine x configured feature, reproducing its configuration (CA2)"""
    plans = []
    from shared.engine_control.models import RuntimeProfile

    for engine in db.query(Engine).order_by(Engine.slug):
        try:
            d = registry.descriptor(engine.adapter_type)
        except ValueError:
            continue
        config = engine.config or {}
        configured = set((config.get("features") or {}).keys())
        configured |= {
            f
            for (f,) in db.query(RuntimeProfile.feature)
            .filter_by(engine_id=engine.id)
            .distinct()
        }
        attr = db.get(EngineAttributes, engine.id)
        env = attr.environment if attr else installation_environment()
        for feature in sorted(configured):
            key = f"engine:{engine.id}:{feature}"
            if feature not in d["features"]:
                report.skip(key, "FEATURE_NOT_SUPPORTED")
                continue
            if engine.adapter_type == "modal" and config.get("whisperx_manifest"):
                report.skip(key, "WHISPERX_CONTROL_PROFILE_NOT_QUALIFIED")
                continue
            legacy = control.latest_profile(db, engine.id, feature)
            if legacy and legacy.source_profile_revision_id:
                report.skip(key, "BOUND_TO_LIBRARY_PROFILE")
                continue
            if legacy:
                # Whitelist, as the legacy import route does: the stored JSON carries
                # resolved extras (model/service/gpu_uuid/manifest_hash) that are not
                # contract input; an absolute warm deadline is never seeded.
                settings = {
                    k: copy.deepcopy(v)
                    for k, v in legacy.profile.items()
                    if k in RuntimeSettings.model_fields
                }
                settings["warm_until"] = None
            else:
                model = _approved_model(engine.adapter_type, feature)
                if model is None:
                    report.skip(key, "MODEL_NOT_APPROVED")
                    continue
                provider = _provider_settings(db, engine.adapter_type, report, key)
                if provider is None:
                    continue
                binding = {
                    k: v
                    for k, v in (config["features"][feature] or {}).items()
                    if v is not None
                }
                settings = _runtime(binding, model["id"], provider)
            plans.append(
                dict(
                    key=key,
                    name=f"{engine.display_name or engine.slug} — {feature}"[:100],
                    description=(
                        f"Configuração de {engine.slug}/{feature} na instalação (seed {key})."
                    ),
                    adapter=engine.adapter_type,
                    feature=feature,
                    environment=env,
                    settings=settings,
                    engine_id=engine.id,
                )
            )
    return plans


def _lock(db, dry_run):
    """End the previous transaction; a real run then serializes on the epoch row"""
    db.rollback()
    if not dry_run:
        policy.epoch(db, True)


def _body(plan):
    return C.ProfileCreate(
        name=plan["name"],
        description=plan["description"],
        adapter_type=plan["adapter"],
        feature=plan["feature"],
        environment=plan["environment"],
        settings=RuntimeSettings.model_validate(plan["settings"]),
        warm_for_seconds=None,
    )


def ensure_profile(db, plan, actor, report, dry_run):
    """The published seeded profile of `plan` (None when skipped or in a dry run)"""
    key = plan["key"]
    row = dict(key=key, name=plan["name"])
    try:
        _lock(db, dry_run)
        p = _seeded(db, key)
        if p is None:
            body = _body(plan)
            if dry_run:
                service.normalize(body.adapter_type, body.feature, body)
                report.created.append(row)
                report.published.append(row)
                return None
            view = service.create_profile(db, body, actor, _audit(key))
            report.created.append(dict(row, profile_id=view["id"]))
            p = db.get(ExecutionProfile, view["id"])
        if p.status == "archived":
            report.skip(key, "PROFILE_ARCHIVED", profile_id=p.id)
            return None
        if not p.latest_published_revision_id:
            if dry_run:
                report.published.append(dict(row, profile_id=p.id))
                return p
            _lock(db, dry_run)
            p = db.get(ExecutionProfile, p.id)
            if not p.latest_published_revision_id:
                r = (
                    db.query(ExecutionRevision)
                    .filter_by(profile_id=p.id)
                    .order_by(ExecutionRevision.revision.desc())
                    .first()
                )
                service.publish(
                    db,
                    p.id,
                    C.Publish(version=p.version, revision_id=r.id),
                    actor,
                    _audit(key),
                )
                report.published.append(dict(row, profile_id=p.id, revision_id=r.id))
        return db.get(ExecutionProfile, p.id)
    except Exception as exc:  # one bad plan never aborts the seeding
        db.rollback()
        report.skip(key, _code(exc), profile_id=None)
        return None


def ensure_bound(db, plan, profile, actor, report, dry_run):
    """Bind the engine profile when the engine/feature has no runtime profile (CA3)"""
    key, feature = plan["key"], plan["feature"]
    row = dict(key=key, name=plan["name"], engine_id=plan["engine_id"], feature=feature)
    try:
        _lock(db, dry_run)
        engine = db.get(Engine, plan["engine_id"])
        if control.latest_profile(db, engine.id, feature):
            report.skip(key, "RUNTIME_PROFILE_EXISTS", stage="bind")
            return
        attr = db.get(EngineAttributes, engine.id)
        if attr is not None and attr.environment != plan["environment"]:
            report.skip(key, "ENGINE_ENVIRONMENT_REQUIRED", stage="bind")
            return
        # The adapter's own checks first (host agent, GPU, connection test), so a bind
        # that cannot succeed does not classify the engine on its way to failing.
        raw = copy.deepcopy(plan["settings"])
        driver = registry.create(engine.adapter_type, raw["adapter_version"])
        driver.validate(engine, feature, raw, db)
        if dry_run:
            report.bound.append(row)
            return
        if attr is None:
            service.set_attributes(
                db,
                engine,
                C.AttributesUpdate(version=0, environment=plan["environment"]),
                actor,
                _audit(key),
            )
            _lock(db, dry_run)
            engine = db.get(Engine, plan["engine_id"])
            if control.latest_profile(db, engine.id, feature):
                report.skip(key, "RUNTIME_PROFILE_EXISTS", stage="bind")
                return
        service.bind(
            db,
            engine,
            C.Bind(
                version=engine.version,
                feature=feature,
                revision_id=profile.latest_published_revision_id,
            ),
            actor,
            _audit(key),
        )
        report.bound.append(dict(row, profile_id=profile.id))
    except Exception as exc:  # best effort: record the code and carry on
        db.rollback()
        report.skip(key, _code(exc), stage="bind")


def seed_execution_profiles(db, *, actor_id, dry_run=False) -> SeedReport:
    """Create, publish and (best effort) bind the default profiles as `actor_id` (root)"""
    report = SeedReport(dry_run=dry_run)
    if not policy.enabled():
        # The library is closed while engine access is off (its routes answer 503);
        # the next boot with IAM_MODE=enforce seeds it.
        report.skip("*", "ACCESS_NOT_ENABLED", stage="seed")
        return report
    actor = db.query(User).filter_by(id=str(actor_id)).first()
    if not actor or not actor.is_active or not is_effective_admin(actor):
        report.skip("*", "BOOTSTRAP_ACTOR_REQUIRED", stage="seed")
        return report
    try:
        policy.epoch(db)
    except control.ControlError as exc:
        report.skip("*", exc.code, stage="seed")
        return report
    for plan in catalog_plans(db, report) + engine_plans(db, report):
        profile = ensure_profile(db, plan, actor.id, report, dry_run)
        if plan["engine_id"] and (profile is not None or dry_run):
            ensure_bound(db, plan, profile, actor.id, report, dry_run)
    db.rollback()
    return report


def seed_quietly(db, actor_id, trigger) -> Optional[SeedReport]:
    """Seed and log; never raises (root creation and boot must not fail because of it)"""
    try:
        report = seed_execution_profiles(db, actor_id=actor_id)
        logger.info("Execution profile seeding (%s): %s", trigger, report.summary())
        return report
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning("Execution profile seeding (%s) failed: %s", trigger, exc)
        return None


def seed_if_root(session_factory=None, trigger="boot") -> Optional[SeedReport]:
    """Seed as the root when one exists; without one, do nothing. Never raises."""
    try:
        if session_factory is None:
            from shared.database import SessionLocal as session_factory
        with session_factory() as db:
            root = root_user(db)
            if root is None:
                logger.info("Execution profile seeding (%s) skipped: no root user yet", trigger)
                return None
            return seed_quietly(db, root.id, trigger)
    except Exception as exc:
        logger.warning("Execution profile seeding (%s) failed: %s", trigger, exc)
        return None


def seed_on_boot(session_factory=None) -> Optional[SeedReport]:
    """API boot (CA5b)"""
    return seed_if_root(session_factory, "boot")


def host_became_ready(previous_seen_at, previous_manifest, inventory, now) -> bool:
    """
    A heartbeat that should re-run the seeding: a new host, one back after being
    stale (the bind window of the local driver), or a changed manifest. Steady
    heartbeats every few seconds do not.
    """
    if previous_seen_at is None:
        return True
    if previous_seen_at < now - timedelta(seconds=HOST_READY_SECONDS):
        return True
    return previous_manifest != (inventory or {}).get("manifest_hash")


def main(argv=None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Create the installation's default execution profiles (spec 0020)."
    )
    parser.add_argument("--dry-run", action="store_true", help="only show what would be done")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)
    from shared.database import SessionLocal

    with SessionLocal() as db:
        root = root_user(db)
        if root is None:
            print("No root user: create it first (first registration or make_admin.py --root).")
            return 1
        report = seed_execution_profiles(db, actor_id=root.id, dry_run=args.dry_run)
    print(json.dumps(report.as_dict(), indent=2, default=str) if args.json else report.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
