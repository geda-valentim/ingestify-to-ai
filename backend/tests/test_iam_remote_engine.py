"""
`engines.remote.use` in submit and in the dispatcher (spec 0014 §4.6, §8 item 5):
CA9 (the permission is decided per remote placement, so a revocation reaches
pages already queued), CA10 (`user_period_limit_usd` on `admins` routes too,
bootstrap included) and CA11 (one decision per user per tick, never per item or
chunk, measured as SQL statements so it cannot flake).

IAM_MODE is set explicitly in every test that depends on it.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event

import shared.iam.models  # noqa: F401  (registers iam_bindings before World creates the schema)
from shared.config import get_settings
from shared.engines import dispatch
from shared.iam import remote
from shared.iam.models import IamBinding
from shared.models import Engine, EngineUsage, Job, JobDispatch, User
from tests._engines_world import ALICE, ROOT, World
from tests.test_engine_pages_and_vision import PARENT, pages, route, split  # noqa: F401  (pages is a fixture)

LOCAL = "eng-local"
BOB = "user-bob"  # holds remote_engine_user through a binding
REMOTE_BINDING = {"gpu_type": "L4", "workers": 1, "executions_per_worker": 1}


@pytest.fixture
def world(monkeypatch, tmp_path):
    w = World(monkeypatch, tmp_path)
    with w.Session() as db:
        local = db.get(Engine, LOCAL)
        local.config = {**local.config, "features": {**local.config["features"],
                                                     "document_conversion": {"workers": 2}}}
        db.add(User(id=BOB, email="bob@example.com", username="bob", hashed_password="x"))
        db.commit()
    monkeypatch.setattr(get_settings(), "admin_user_ids", "")
    yield w
    w.close()


def mode(monkeypatch, value):
    monkeypatch.setattr(get_settings(), "iam_mode", value)


def bind(world, user=BOB, role="remote_engine_user"):
    with world.Session() as db:
        b = IamBinding(subject_type="user", subject_id=user, role=role, scope_type="platform",
                       granted_by=ROOT, expires_at=world.now + timedelta(days=30),
                       created_at=world.now - timedelta(days=1))
        db.add(b)
        db.commit()
        return b.id


def revoke(world, binding_id):
    with world.Session() as db:
        db.get(IamBinding, binding_id).revoked_at = world.now
        db.commit()


def add_remote(world, slug="fake_1", features=("transcription",)):
    with world.Session() as db:
        db.add(Engine(id=f"eng-{slug}", slug=slug, display_name=slug, adapter_type="fake",
                      config={"features": {f: dict(REMOTE_BINDING) for f in features}},
                      deployments={f: {"binding": dict(REMOTE_BINDING)} for f in features},
                      status="active", health="healthy", credentials_masked={}, limit_usd=Decimal("30"),
                      min_remaining_usd=Decimal("0.5")))
        db.commit()
    return f"eng-{slug}"


def occupy(world, engine_id, feature, n):
    with world.Session() as db:
        ids = []
        for i in range(n):
            u = EngineUsage(kind="job", engine_id=engine_id, feature=feature, subject_type="job",
                            subject_id=f"busy-{engine_id}-{i}", attempt=1, period_start=world.now.date(),
                            status="running", heartbeat_at=world.now)
            db.add(u)
            db.flush()
            ids.append(u.id)
        db.commit()
        return ids


def release(world, usage_ids):
    with world.Session() as db:
        db.query(EngineUsage).filter(EngineUsage.id.in_(usage_ids)).update(
            {"status": "settled", "actual_usd": 0}, synchronize_session=False)
        db.commit()


# --- the helper ---------------------------------------------------------------------


def test_can_use_remote_follows_the_mode(world, monkeypatch):
    with world.Session() as db:
        root, alice, bob = db.get(User, ROOT), db.get(User, ALICE), db.get(User, BOB)
        bind(world)
        mode(monkeypatch, "off")  # legacy: is_effective_admin; bindings inert
        assert [remote.can_use_remote(u, db=db) for u in (root, alice, bob)] == [True, False, False]
        mode(monkeypatch, "enforce")
        assert [remote.can_use_remote(u, db=db) for u in (root, alice, bob)] == [True, False, True]
        # Without a session the helper opens one only when it has to read bindings
        assert remote.can_use_remote(bob, session_factory=world.Session) is True
        assert remote.can_use_remote(None, db=db) is False
        assert remote.can_use_remote_by_id(db, None) is False
        assert remote.can_use_remote_by_id(db, "nobody") is False


def test_off_without_a_session_reads_nothing(world, monkeypatch):
    mode(monkeypatch, "off")

    def no_session():
        raise AssertionError("off decides from the user row in hand")

    with world.Session() as db:
        root = db.get(User, ROOT)
        db.expunge(root)
    assert remote.can_use_remote(root, session_factory=no_session) is True


# --- submit records remote_allowed through IAM ---------------------------------------


def _submitted_remote_allowed(world, user_id, remote_use):
    job_id = world.add_job(user=user_id)
    world.dispatcher_alive()
    outcome = dispatch.submit(feature="transcription", job_id=job_id, user_id=user_id, remote_use=remote_use,
                              payload={}, today=None, celery=world.celery, session_factory=world.Session,
                              now=world.now)
    assert outcome == "queued"
    with world.Session() as db:
        return db.query(JobDispatch).filter_by(job_id=job_id).one().remote_allowed


def test_submit_records_engines_remote_use_and_skips_the_decision_when_it_does_not_matter(world, monkeypatch):
    mode(monkeypatch, "enforce")
    fake = add_remote(world)
    bind(world)
    world.set_route([LOCAL], [fake])  # remote_allowed_for defaults to 'admins'
    with world.Session() as db:
        bob, alice = db.get(User, BOB), db.get(User, ALICE)
        db.expunge_all()
    assert _submitted_remote_allowed(world, BOB, lambda: remote.can_use_remote(bob, session_factory=world.Session))
    assert not _submitted_remote_allowed(world, ALICE,
                                         lambda: remote.can_use_remote(alice, session_factory=world.Session))

    # remote_allowed_for='all': nobody needs the permission, so it is never decided
    world.set_route([LOCAL], [fake], remote_allowed_for="all", user_period_limit_usd=Decimal("5"))

    def never():
        raise AssertionError("decided although the route lets everyone through")

    assert _submitted_remote_allowed(world, ALICE, never)


# --- CA9: decided per remote placement ----------------------------------------------


def test_ca9_without_the_permission_no_remote_placement_even_with_a_stale_flag(world, monkeypatch):
    mode(monkeypatch, "enforce")
    fake = add_remote(world)
    world.set_route([fake], [LOCAL])
    # remote_allowed=True as if frozen when the user still had the permission
    item = world.add_item(user=ALICE, remote_allowed=True, media=10)

    placed = world.tick().placed

    assert [(p[0], p[1]) for p in placed] == [(item, "local")]
    assert world.remote.published == []


def test_ca9_with_the_permission_the_item_goes_remote(world, monkeypatch):
    mode(monkeypatch, "enforce")
    fake = add_remote(world)
    world.set_route([fake], [LOCAL])
    bind(world)
    item = world.add_item(user=BOB, remote_allowed=True, media=10)

    assert [(p[0], p[1]) for p in world.tick().placed] == [(item, "fake_1")]
    assert world.usage(world.item(item).usage_id).user_id == BOB


def test_ca9_off_mode_demoting_an_admin_reaches_queued_items(world, monkeypatch):
    """IAM_MODE=off is the legacy rule, now evaluated at placement instead of frozen at submit"""
    mode(monkeypatch, "off")
    fake = add_remote(world)
    world.set_route([fake], [LOCAL])
    item = world.add_item(user=ROOT, remote_allowed=True, media=10)
    with world.Session() as db:
        db.get(User, ROOT).is_admin = False
        db.commit()

    assert [p[1] for p in world.tick().placed] == ["local"]
    assert world.item(item).engine_id == LOCAL


def test_ca9_revocation_between_placements_of_a_multipage_pdf(world, pages, monkeypatch):
    mode(monkeypatch, "enforce")
    fake = add_remote(world, features=("document_conversion",))
    route(world, "document_conversion", [fake], [LOCAL])
    with world.Session() as db:
        db.get(Job, PARENT).user_id = BOB  # the PDF's owner holds engines.remote.use
        db.commit()
    binding = bind(world)
    busy = occupy(world, LOCAL, "document_conversion", 2)  # the local lane is full

    split(world)  # three pages, submitted while BOB holds engines.remote.use
    with world.Session() as db:
        rows = db.query(JobDispatch).order_by(JobDispatch.id).all()
        assert [r.remote_allowed for r in rows] == [True, True, True]
        # Remote executors take only measured items; pages are never probed, so the
        # test measures them itself
        for r in rows:
            r.media_seconds = Decimal("1")
        db.commit()
        page_items = [r.id for r in rows]

    # Tick 1: one remote slot, the local lane full -> page 1 goes remote
    assert [(p[0], p[1]) for p in world.tick().placed] == [(page_items[0], "fake_1")]

    # Revoked mid-PDF; the remote slot frees, so does the local lane
    revoke(world, binding)
    release(world, busy + [world.item(page_items[0]).usage_id])

    placed = world.tick(world.now + timedelta(seconds=5)).placed
    assert sorted((p[0], p[1]) for p in placed) == [(page_items[1], "local"), (page_items[2], "local")]
    assert [p[1] for p in world.remote.published] == [page_items[0]]


def test_ca9_revoked_without_a_local_path_follows_on_no_engine(world, monkeypatch):
    mode(monkeypatch, "enforce")
    fake = add_remote(world)
    binding = bind(world)
    world.set_route([fake], on_no_engine="fail", fail_after_seconds=60)
    first = world.add_item(user=BOB, remote_allowed=True, media=10, wait=20)
    second = world.add_item(user=BOB, remote_allowed=True, media=10, wait=10)
    assert [p[0] for p in world.tick().placed] == [first]
    revoke(world, binding)
    release(world, [world.item(first).usage_id])

    assert world.tick(world.now + timedelta(seconds=5)).placed == []
    assert world.item(second).state == "waiting"
    assert world.item(second).unplaceable_since is not None  # "no remote executor": not a capacity wait

    world.tick(world.now + timedelta(seconds=120))
    assert world.item(second).state == "failed"
    assert world.remote.published == [("fake_1", first, world.item(first).usage_id)]


def test_ca9_an_all_route_never_asks(world, monkeypatch):
    mode(monkeypatch, "enforce")
    fake = add_remote(world)
    world.set_route([fake], [LOCAL], remote_allowed_for="all", user_period_limit_usd=Decimal("5"))
    monkeypatch.setattr(remote, "can_use_remote_by_id",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("asked on an 'all' route")))
    world.add_item(user=ALICE, remote_allowed=True, media=10)
    assert [p[1] for p in world.tick().placed] == ["fake_1"]


def test_ca9_a_decision_that_cannot_be_taken_denies_remote(world, monkeypatch):
    mode(monkeypatch, "enforce")
    fake = add_remote(world)
    world.set_route([fake], [LOCAL])
    bind(world)

    def broken(*a, **k):
        raise RuntimeError("database went away")

    monkeypatch.setattr(remote, "can_use_remote_by_id", broken)
    world.add_item(user=BOB, remote_allowed=True, media=10)
    assert [p[1] for p in world.tick().placed] == ["local"]


# --- CA10: the per-user ceiling on 'admins' routes, bootstrap included ---------------


@pytest.mark.parametrize("iam_mode", ["off", "enforce"])
def test_ca10_user_period_limit_applies_to_admins_routes_and_bootstrap(world, monkeypatch, iam_mode):
    mode(monkeypatch, iam_mode)
    fake = add_remote(world)
    world.set_route([fake], [LOCAL], user_period_limit_usd=Decimal("0.05"))  # 'admins'
    big = world.add_item(user=ROOT, remote_allowed=True, media=100, wait=10)  # US$ 0.10 > 0.05
    small = world.add_item(user=ROOT, remote_allowed=True, media=40, wait=5)  # US$ 0.04

    placed = dict((p[0], p[1]) for p in world.tick().placed)

    assert placed[big] == "local"  # refused remote by user_cap, the local step takes it
    assert placed[small] == "fake_1"


def test_ca10_the_ceiling_counts_what_the_user_already_committed(world, monkeypatch):
    mode(monkeypatch, "enforce")
    fake = add_remote(world)
    bind(world)
    world.set_route([fake], user_period_limit_usd=Decimal("0.05"))
    first = world.add_item(user=BOB, remote_allowed=True, media=40, wait=10)  # 0.04
    assert [p[0] for p in world.tick().placed] == [first]
    release(world, [world.item(first).usage_id])
    with world.Session() as db:
        db.get(EngineUsage, world.item(first).usage_id).actual_usd = Decimal("0.04")
        db.commit()
    second = world.add_item(user=BOB, remote_allowed=True, media=20)  # 0.04 + 0.02 > 0.05
    assert world.tick(world.now + timedelta(seconds=5)).placed == []
    assert world.item(second).state == "waiting"


# --- CA11: per placement and per user, never per item -------------------------------


class _Statements:
    def __init__(self, engine):
        self.engine, self.n = engine, 0

    def __enter__(self):
        event.listen(self.engine, "before_cursor_execute", self._count)
        return self

    def __exit__(self, *exc):
        event.remove(self.engine, "before_cursor_execute", self._count)

    def _count(self, *args, **kwargs):
        self.n += 1


def _backlog(world, users, n):
    """`n` waiting remote-allowed items, round-robin over `users` (no job files: never published locally)"""
    with world.Session() as db:
        db.bulk_save_objects([
            JobDispatch(feature="transcription", subject_type="job", subject_id=f"bulk-{i}", job_id=f"bulk-{i}",
                        user_id=users[i % len(users)], remote_allowed=True, state="waiting", payload={},
                        media_seconds=Decimal("1"), enqueued_at=world.now - timedelta(seconds=n - i),
                        updated_at=world.now, exclude_engines=[])
            for i in range(n)
        ])
        db.commit()


def _tick_statements(world, at):
    with _Statements(world.engine) as counter:
        result = world.tick(at)
    return counter.n, result


@pytest.mark.parametrize("users", [[BOB], [BOB, ROOT]])
def test_ca11_one_decision_per_user_per_tick_with_1000_items_in_backlog(world, monkeypatch, users):
    mode(monkeypatch, "enforce")
    fake = add_remote(world)
    bind(world)
    _backlog(world, users, 1000)
    calls = []
    real = remote.can_use_remote_by_id
    monkeypatch.setattr(remote, "can_use_remote_by_id", lambda db, uid, **k: calls.append(uid) or real(db, uid, **k))

    # Same backlog, same engines; only the route's restriction differs. The remote
    # engine has one slot, so every other candidate reaches it and finds it full.
    # A first tick warms up the per-engine state rows, so the two measured ticks
    # do the same work apart from the IAM decisions.
    world.set_route([fake], remote_allowed_for="all", user_period_limit_usd=Decimal("100"))
    assert len(world.tick().placed) == 1
    release(world, [u.id for u in _usages(world)])
    open_n, open_result = _tick_statements(world, world.now + timedelta(seconds=5))
    assert len(open_result.placed) == 1 and calls == []
    release(world, [u.id for u in _usages(world)])

    world.set_route([fake], remote_allowed_for="admins", user_period_limit_usd=Decimal("100"))
    restricted_n, restricted_result = _tick_statements(world, world.now + timedelta(seconds=10))
    assert len(restricted_result.placed) == 1

    assert sorted(calls) == sorted(users)  # once per user, not per candidate (20+) nor per item (1000)
    # Per user: the user's primary key, plus the bindings query for a non-bootstrap user
    per_user = {BOB: 2, ROOT: 1}
    assert 0 < restricted_n - open_n <= sum(per_user[u] for u in users)


def _usages(world):
    with world.Session() as db:
        rows = db.query(EngineUsage).filter(EngineUsage.engine_id == "eng-fake_1").all()
        db.expunge_all()
        return rows


# --- the API's submit paths decide through IAM ---------------------------------------


@pytest.mark.parametrize("iam_mode,expected", [("off", False), ("enforce", True)])
def test_api_upload_records_the_binding_only_when_iam_decides(world, monkeypatch, iam_mode, expected):
    from api import routes

    mode(monkeypatch, iam_mode)
    fake = add_remote(world)
    bind(world)
    world.set_route([LOCAL], [fake])
    world.dispatcher_alive()
    monkeypatch.setattr(routes, "SessionLocal", world.Session)
    monkeypatch.setattr(routes, "_engine_celery", lambda: world.celery)
    job_id = world.add_job(user=BOB)
    with world.Session() as db:
        bob = db.get(User, BOB)
        db.expunge(bob)

    routes._enqueue_maybe_routed("aula.mp3", job_id, world.tmp / "audio" / job_id / "aula.mp3", bob, 67,
                                 lambda: pytest.fail("a routed upload is not sent down today's path"))

    with world.Session() as db:
        assert db.query(JobDispatch).filter_by(job_id=job_id).one().remote_allowed is expected
