"""
A self-contained world for routing tests (spec 0003, slice 3b): SQLite with the
real models, fakeredis, a Celery stand-in that records what is published, the
local engine with 2 transcription slots, and a fake remote executor for the
rules that only remote engines exercise (budget, admins, fill_first).

Every module that opens sessions is pointed at this database; nothing here can
reach a real MySQL, Redis or broker.
"""

import os
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Optional
from uuid import uuid4

import fakeredis
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import workers.celery_app  # noqa: F401  (import order used by the worker; avoids a circular import)
import shared.database
import shared.queries
import shared.redis_client
from shared.auth import hash_password
from shared.database import Base
from shared.engines import dispatch, routing
from shared.models import DispatcherLease, Engine, EngineUsage, FeatureRoute, Job, JobDispatch, JobStatus, User
from shared.redis_client import RedisClient
from workers import tasks
from workers.engines import dispatcher, executors

ALICE = "user-alice"  # not an admin
ROOT = "user-root"  # admin
LOCAL_BINDING = {"gpu_ref": "gpu0", "workers": 2}
GPU0 = {"ref": "gpu0", "name": "RTX 5060 Ti", "vram_gb": 16, "vram_reserve_gb": 1.0}
REMOTE_BINDING = {"gpu_type": "L4", "workers": 1, "executions_per_worker": 1}


class FakeCelery:
    def __init__(self):
        self.sent = []

    def send_task(self, name, args=None, kwargs=None, queue=None, **options):
        self.sent.append(SimpleNamespace(name=name, args=list(args or []), kwargs=dict(kwargs or {}), queue=queue))

    def named(self, name):
        return [s for s in self.sent if s.name == name]

    def local_runs(self):
        return [s for s in self.named(dispatch.PROCESS_CONVERSION) if "usage_id" in s.kwargs]


class FakeRemote:
    """A remote executor that charges `usd_per_second` of media and records what it is sent"""
    remote = True

    def __init__(self, usd_per_second="0.001"):
        self.rate = Decimal(usd_per_second)
        self.published = []

    def estimate(self, engine, binding, item):
        return (self.rate * Decimal(str(item.media_seconds or 0))).quantize(Decimal("0.000001"))

    def publish(self, celery, engine, item, usage_id):
        self.published.append((engine.slug, item.id, usage_id))


class World:
    def __init__(self, monkeypatch, tmp_path):
        # ENGINES_TEST_DATABASE_URL runs the same scenarios on a real (scratch!) MySQL,
        # whose locking SQLite does not reproduce; every table is dropped first
        url = os.environ.get("ENGINES_TEST_DATABASE_URL")
        if url:
            self.engine = create_engine(url)
            Base.metadata.drop_all(bind=self.engine)
        else:
            self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        for module in (shared.database, shared.queries, tasks):
            monkeypatch.setattr(module, "SessionLocal", self.Session)
        monkeypatch.setattr(routing, "_default_session_factory", self.Session)
        self.redis = RedisClient(client=fakeredis.FakeRedis(decode_responses=True))
        monkeypatch.setattr(shared.redis_client, "_redis_client", self.redis)
        monkeypatch.setattr(tasks, "get_redis_client", lambda: self.redis)
        self.celery = FakeCelery()
        monkeypatch.setattr(tasks, "celery_app", self.celery)
        monkeypatch.setattr(tasks.settings, "temp_storage_path", str(tmp_path))
        self.tmp = tmp_path
        dispatch.reset_caches()
        dispatcher._leadership.clear()
        self.remote = FakeRemote()
        executors.register("fake", self.remote)
        self.now = datetime.utcnow().replace(microsecond=0)

        with self.Session() as db:
            db.add(User(id=ALICE, email="alice@example.com", username="alice", hashed_password="x"))
            db.add(User(id=ROOT, email="root@example.com", username="root", hashed_password=hash_password("pw"),
                        is_admin=True))
            db.add(Engine(id="eng-local", slug="local", display_name="Local workers", adapter_type="local",
                          config={"gpus": [GPU0], "features": {"transcription": dict(LOCAL_BINDING)}},
                          deployments={}, status="active", health="unknown", is_system=True, credentials_masked={}))
            db.add(DispatcherLease(id=1, epoch=0))
            db.commit()

    def close(self):
        executors.register("fake", None)
        dispatch.reset_caches()
        dispatcher._leadership.clear()

    # --- configuration -------------------------------------------------------------

    def add_remote(self, slug, limit_usd="30", **extra):
        with self.Session() as db:
            db.add(Engine(id=f"eng-{slug}", slug=slug, display_name=slug, adapter_type="fake",
                          config={"features": {"transcription": dict(REMOTE_BINDING)}, **extra.pop("config", {})},
                          deployments={"transcription": {"binding": dict(REMOTE_BINDING)}}, status="active",
                          health="healthy", credentials_masked={}, limit_usd=Decimal(limit_usd),
                          min_remaining_usd=Decimal("0.5"), **extra))
            db.commit()
        return f"eng-{slug}"

    def set_route(self, *steps, **values):
        """Steps as lists of engine ids, or dicts; written directly (validation is tested on its own)"""
        raw = []
        for position, step in enumerate(steps, start=1):
            step = {"engine_ids": step} if isinstance(step, list) else dict(step)
            step.setdefault("group_strategy", "priority")
            step["position"] = position
            raw.append(step)
        with self.Session() as db:
            route = db.get(FeatureRoute, "transcription") or FeatureRoute(feature="transcription", version=0)
            route.steps = raw
            route.state = values.pop("state", "active")
            for k, v in values.items():
                setattr(route, k, v)
            route.version = (route.version or 0) + 1
            db.merge(route)
            db.commit()
        dispatch.reset_caches()

    def dispatcher_alive(self, at: Optional[datetime] = None):
        with self.Session() as db:
            db.get(DispatcherLease, 1).dispatcher_seen_at = at or self.now
            db.commit()
        dispatch.reset_caches()

    # --- items ---------------------------------------------------------------------

    def add_job(self, user=ALICE, status=JobStatus.PENDING, name="aula.mp3"):
        job_id = str(uuid4())
        audio_dir = self.tmp / "audio" / job_id
        audio_dir.mkdir(parents=True)
        (audio_dir / name).write_bytes(b"ID3" + b"\0" * 64)
        with self.Session() as db:
            db.add(Job(id=job_id, user_id=user, filename=name, name=name, job_type="MAIN", status=status,
                       source_type="audio"))
            db.commit()
        return job_id

    def add_item(self, user=ALICE, remote_allowed=False, media=None, wait=0, state="waiting", **extra):
        job_id = self.add_job(user=user)
        payload = dispatch.transcription_payload(job_id, self.tmp / "audio" / job_id / "aula.mp3",
                                                 {"is_audio": True}, "ingestify-audio")
        with self.Session() as db:
            d = JobDispatch(feature="transcription", subject_type="job", subject_id=job_id, job_id=job_id,
                            user_id=user, remote_allowed=remote_allowed, state=state, payload=payload,
                            media_seconds=Decimal(str(media)) if media is not None else None,
                            enqueued_at=self.now - timedelta(seconds=wait), updated_at=self.now,
                            **{"exclude_engines": [], **extra})
            db.add(d)
            db.commit()
            return d.id

    def tick(self, at: Optional[datetime] = None, **kwargs):
        kwargs.setdefault("alive", lambda feature: 2)
        return dispatcher.run_tick(celery=self.celery, session_factory=self.Session, now=at or self.now,
                                   redis_client=self.redis, **kwargs)

    # --- reading -------------------------------------------------------------------

    def item(self, dispatch_id):
        with self.Session() as db:
            d = db.get(JobDispatch, dispatch_id)
            db.expunge(d)
            return d

    def usage(self, usage_id):
        with self.Session() as db:
            u = db.get(EngineUsage, usage_id)
            db.expunge(u)
            return u

    def job(self, job_id):
        with self.Session() as db:
            j = db.get(Job, job_id)
            db.expunge(j)
            return j

    def count(self, model, **filters):
        with self.Session() as db:
            return db.query(model).filter_by(**filters).count()

    def in_flight(self, engine_id="eng-local"):
        with self.Session() as db:
            return db.query(EngineUsage).filter(EngineUsage.engine_id == engine_id,
                                                EngineUsage.status.in_(("reserved", "spawning", "running"))).count()
