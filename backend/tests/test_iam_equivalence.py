"""
CA3 in CI (spec 0014 §3, §4.11 step 3): the offline equivalence of
`shared.iam.equivalence` (CLI `scripts/iam_equivalence.py`) run against a SQLite
fixture that holds the shapes unit fixtures tend to miss: orphan jobs, a NULL
`user_id` walked up `parent_job_id`, a parent cycle, PAGE children known only
through `pages`, SPLIT/MERGE children known only through the Redis parent link,
a job MySQL does not know at all (Redis owner fallback), an inactive user, a
bootstrap admin and an API key bound to someone else's project.

The run must be clean, and must **not** be clean when the IAM side regresses
(otherwise a broken comparison would pass silently).
"""

from datetime import datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.database import Base
from shared.iam import equivalence, ownership
from shared.models import (APIKey, DatalakeConnection, Folder, ImageAnalysisRun, Job, JobStatus, Page, Project,
                           User)

ALICE, BOB, DAVE, EVE = "user-alice", "user-bob", "user-dave", "user-eve"  # dave inactive, eve admin

# Redis, as the workers leave it: SPLIT/MERGE children carry their parent link; one
# job reached Redis only (its MySQL write failed during upload).
REDIS_STATUS = {
    "alice-split": {"parent_job_id": "alice-main"},
    "bob-merge": {"parent_job_id": "bob-main"},
    "dangling-split": {"parent_job_id": "no-such-job"},
}
REDIS_OWNER = {"redis-only": ALICE}


def redis_status(job_id):
    return REDIS_STATUS.get(job_id)


def owner_matches(job_id, user_id):
    owner = REDIS_OWNER.get(job_id)
    return bool(owner) and owner == user_id


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    session.add_all([
        User(id=ALICE, email="a@example.com", username="alice", hashed_password="x", is_active=True),
        User(id=BOB, email="b@example.com", username="bob", hashed_password="x", is_active=True),
        User(id=DAVE, email="d@example.com", username="dave", hashed_password="x", is_active=False),
        User(id=EVE, email="e@example.com", username="eve", hashed_password="x", is_active=True, is_admin=True),
    ])
    session.flush()

    def job(job_id, user_id, parent=None, kind="MAIN"):
        return Job(id=job_id, user_id=user_id, parent_job_id=parent, name=job_id, filename=f"{job_id}.pdf",
                   status=JobStatus.COMPLETED, job_type=kind, created_at=datetime(2026, 1, 1))

    session.add_all([
        job("alice-main", ALICE),
        job("bob-main", BOB),
        job("dave-main", DAVE),
        job("eve-main", EVE),
        job("orphan", None),  # user deleted: nobody's
        job("alice-child-row", None, parent="alice-main", kind="PAGE"),  # walks up to alice
        job("cycle-a", None),
        job("cycle-b", None, parent="cycle-a"),
    ])
    session.flush()
    session.get(Job, "cycle-a").parent_job_id = "cycle-b"  # a parent cycle: nobody's
    session.add_all([
        Page(job_id="alice-main", page_number=1, page_job_id="alice-page-1"),
        Page(job_id="bob-main", page_number=1, page_job_id="bob-page-1"),
        Page(job_id="orphan", page_number=1, page_job_id="orphan-page-1"),
    ])
    for owner in (ALICE, BOB, DAVE):
        session.add(Project(id=f"{owner}-p", user_id=owner, name="P", name_key="p"))
    session.flush()
    for owner in (ALICE, BOB):
        session.add(Folder(id=f"{owner}-f", user_id=owner, project_id=f"{owner}-p", name="F", name_key="f"))
    session.add_all([
        APIKey(id="00000000-0000-0000-0000-00000000000a", user_id=ALICE, key_hash="ha", name="a"),
        # Alice's key bound to Bob's project: the key is still Alice's.
        APIKey(id="00000000-0000-0000-0000-00000000000b", user_id=ALICE, key_hash="hb", name="b",
               project_id=f"{BOB}-p"),
        APIKey(id="00000000-0000-0000-0000-00000000000c", user_id=BOB, key_hash="hc", name="c"),
    ])
    # Merged with #48: datalake connections (owned rows) and image runs (keyed by job).
    session.add_all([
        DatalakeConnection(id=f"{owner}-dl", user_id=owner, name="DL", provider="s3", config={},
                           credentials_encrypted=b"x")
        for owner in (ALICE, BOB, DAVE)
    ])
    session.add_all([job("alice-image", ALICE), job("bob-image", BOB), job("orphan-image", None),
                     # NULL owner, parent owned by alice: a job the shared rule gives alice,
                     # but main's inline cancel rule (`Job.user_id == me`) did not.
                     job("alice-parented-image", None, parent="alice-main")])
    session.flush()
    session.add_all([
        ImageAnalysisRun(job_id=j, options={}, source_path=f"images/{j}/source", deadline_at=datetime(2026, 1, 2))
        for j in ("alice-image", "bob-image", "orphan-image", "alice-parented-image")
    ])
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _run(db):
    return equivalence.run(
        db,
        redis_status=redis_status,
        owner_matches=owner_matches,
        extra_job_ids=["alice-split", "bob-merge", "dangling-split", "redis-only", "unknown"],
    )


def test_fixture_is_clean_and_covers_every_kind(db):
    report = _run(db)
    assert report.clean, "\n".join(map(str, report.divergences))
    # 4 users × (12 job rows + 3 page children + 5 extras + 3 projects + 2 folders + 3 keys
    #            + 3 datalake connections + 4 image runs)
    assert report.pairs == 4 * (12 + 3 + 5 + 3 + 2 + 3 + 3 + 4)
    # read/update/delete everywhere, + datalakes.use; a run is one jobs.cancel.
    per_user = (12 + 3 + 5 + 3 + 2 + 3) * len(equivalence.ACTIONS) \
        + 3 * len(equivalence.DATALAKE_PERMISSIONS) + 4 * 1
    assert report.decisions == 4 * per_user


def test_legacy_copy_decides_the_tricky_shapes(db):
    """The frozen legacy rule itself, so 'clean' is not two wrong answers agreeing."""
    alice, bob, dave = (db.get(User, u) for u in (ALICE, BOB, DAVE))

    def legacy(job_id, user):
        return equivalence.legacy_job_allowed(db, job_id, user, redis_status, owner_matches)

    assert legacy("alice-child-row", alice)
    assert legacy("alice-page-1", alice) and not legacy("alice-page-1", bob)
    assert legacy("alice-split", alice) and legacy("bob-merge", bob) and not legacy("bob-merge", alice)
    assert legacy("redis-only", alice) and not legacy("redis-only", bob)
    for nobody in ("orphan", "orphan-page-1", "cycle-a", "dangling-split", "unknown"):
        assert not legacy(nobody, alice)
    # An inactive user is refused by get_current_active_user before any owner check.
    assert legacy("dave-main", dave) and not equivalence.legacy_active(dave)
    assert equivalence.legacy_api_key_allowed(db, "00000000-0000-0000-0000-00000000000b", alice)
    assert not equivalence.legacy_project_allowed(db, f"{BOB}-p", alice)
    assert equivalence.legacy_datalake_allowed(db, f"{ALICE}-dl", alice)
    assert not equivalence.legacy_datalake_allowed(db, f"{ALICE}-dl", bob)
    assert equivalence.legacy_image_cancel_allowed(db, "alice-image", alice)
    assert not equivalence.legacy_image_cancel_allowed(db, "alice-image", bob)
    assert not equivalence.legacy_image_cancel_allowed(db, "orphan-image", alice)
    # The shared job rule gives alice the parented row; the cancel rule did not.
    assert legacy("alice-parented-image", alice)
    assert not equivalence.legacy_image_cancel_allowed(db, "alice-parented-image", alice)


def test_a_regression_in_ownership_is_reported(db, monkeypatch):
    """A broken IAM side (Redis parent link ignored) must produce divergences."""
    real = ownership.job_access

    def no_parent_link(s, job_id, user_id, *, redis_status, owner_matches):
        return real(s, job_id, user_id, redis_status=lambda _id: None, owner_matches=owner_matches)

    monkeypatch.setattr(ownership, "job_access", no_parent_link)
    report = _run(db)
    diverging = {(d.user_id, d.resource_id) for d in report.divergences}
    assert diverging == {(ALICE, "alice-split"), (BOB, "bob-merge")}
    assert all(d.legacy and not d.iam for d in report.divergences)


def test_a_regression_on_the_merged_resources_is_reported(db, monkeypatch):
    """Datalake connections and image cancel are really compared, not skipped."""
    real = ownership.owns
    monkeypatch.setattr(ownership, "owns", lambda resource, user_id: (
        True if isinstance(resource, DatalakeConnection) else real(resource, user_id)))
    report = _run(db)
    assert report.divergences and {d.kind for d in report.divergences} == {"datalake"}
    assert all(not d.legacy and d.iam for d in report.divergences)
    monkeypatch.setattr(ownership, "owns", real)

    real_access = ownership.job_access

    def deny_images(s, job_id, user_id, *, redis_status, owner_matches):
        if job_id.endswith("-image"):
            return ownership.JobAccess(False, None)
        return real_access(s, job_id, user_id, redis_status=redis_status, owner_matches=owner_matches)

    monkeypatch.setattr(ownership, "job_access", deny_images)
    report = _run(db)
    diverging = {(d.kind, d.user_id, d.resource_id) for d in report.divergences}
    assert ("image_cancel", ALICE, "alice-image") in diverging and ("image_cancel", BOB, "bob-image") in diverging


def test_bootstrap_reads_no_one_elses_data(db):
    """Equivalence holds for an admin too: bootstrap is not a data owner (§4.4)."""
    report = equivalence.run(db, user_ids=[EVE])
    assert report.clean
    eve = db.get(User, EVE)
    assert not equivalence.legacy_job_allowed(db, "alice-main", eve, redis_status, owner_matches)


def test_cli_exit_codes(tmp_path, monkeypatch, capsys):
    url = f"sqlite:///{tmp_path / 'dump.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(bind=engine)
    s = sessionmaker(bind=engine)()
    s.add(User(id=ALICE, email="a@example.com", username="alice", hashed_password="x", is_active=True))
    s.add(Job(id="j1", user_id=ALICE, name="j", filename="j.pdf", status=JobStatus.COMPLETED, job_type="MAIN"))
    s.commit()
    s.close()
    engine.dispose()

    assert equivalence.main(["--db-url", url]) == 0
    assert "0 divergences" in capsys.readouterr().out

    def always_deny(s, job_id, user_id, **_kw):
        return ownership.JobAccess(False, None)

    monkeypatch.setattr(ownership, "job_access", always_deny)
    assert equivalence.main(["--db-url", url]) == 1
    out = capsys.readouterr().out
    assert "DIVERGENCE user=user-alice job=j1 permission=jobs.read legacy=True iam=False" in out

    assert equivalence.main(["--db-url", "notadialect://x"]) == 2
