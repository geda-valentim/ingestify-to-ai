import json


from datetime import datetime


from types import SimpleNamespace


from unittest.mock import MagicMock


import pytest


from fastapi import FastAPI


from fastapi.testclient import TestClient


from sqlalchemy import create_engine, event


from sqlalchemy.orm import sessionmaker


from sqlalchemy.pool import StaticPool


import workers.celery_app


from api import datalake_routes, routes


from shared.auth import get_current_active_user


from shared.database import Base, get_db


from shared.datalake import service


from shared.datalake.adapters import S3Adapter, MinioAdapter, GCSAdapter, AzureAdapter, ADAPTERS


from shared.datalake.schemas import Destination


from shared.datalake.secrets import unseal


from shared.models import DatalakeConnection, Job, JobDatalakeExport, JobStatus, Project, User


from workers import tasks, datalake_tasks


SECRET = "test-storage-secret-never-returned"


JOB = "11111111-2222-4333-8444-555555555555"


class MemoryAdapter:
    def __init__(self):
        self.data = {}
        self.fail = False
        self.created = []

    def buckets(self):
        return ["first-bucket", "second-bucket"] + [bucket for bucket, _ in self.created]

    def bucket_exists(self, name):
        return name in self.buckets()

    def create_bucket(self, bucket, location=None):
        self.created.append((bucket, location))

    def put(self, bucket, key, data, content_type):
        if self.fail:
            raise RuntimeError(SECRET)
        self.data[bucket, key] = data

    def objects(self, bucket, prefix, limit):
        return [{"key": key, "size": len(data)} for (b, key), data in self.data.items() if b == bucket and key.startswith(prefix)][:limit]

    def download(self, bucket, key, path, max_bytes):
        from pathlib import Path
        data = self.data[bucket, key]
        if len(data) > max_bytes:
            raise ValueError("too large")
        Path(path).write_bytes(data)


class InternalMinio:
    bucket_results = "results"
    bucket_audio = "audio"
    bucket_uploads = "uploads"

    def __init__(self):
        self.data = {}

    def upload_file(self, bucket_name, object_name, file_data=None, file_path=None, content_type=None):
        from pathlib import Path
        self.data[bucket_name, object_name] = file_data if file_data is not None else Path(file_path).read_bytes()
        return object_name

    def download_file(self, bucket_name, object_name):
        return self.data[bucket_name, object_name]


@pytest.fixture
def world(monkeypatch, fake_redis, tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def enable_fk(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        db.add_all([User(id="alice", username="alice", email="a@example.test", hashed_password="x"),
                    User(id="bob", username="bob", email="b@example.test", hashed_password="x")])
        db.commit()
        db.add(Project(id="p", user_id="alice", name="Aulas", name_key="aulas"))
        db.commit()
    actor = {"id": "alice"}
    adapter = MemoryAdapter()
    minio = InternalMinio()
    monkeypatch.setattr(service, "adapter_for", lambda connection: adapter)
    monkeypatch.setattr(datalake_routes, "adapter_for", lambda connection: adapter)
    monkeypatch.setattr(service, "SessionLocal", Session)
    monkeypatch.setattr(service, "get_minio_client", lambda: minio)
    monkeypatch.setattr(datalake_tasks, "SessionLocal", Session)
    monkeypatch.setattr(routes, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(routes, "get_minio_client", lambda: minio)
    monkeypatch.setattr(routes.settings, "temp_storage_path", str(tmp_path))
    monkeypatch.setattr(tasks.process_conversion, "delay", lambda *args, **kwargs: None)
    monkeypatch.setattr(tasks.process_conversion, "apply_async", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "_publish_export", lambda job_id: None)
    app = FastAPI()
    app.include_router(datalake_routes.router)
    app.include_router(datalake_routes.job_router)
    app.include_router(routes.router)
    def dbdep():
        with Session() as db:
            yield db
    def auth():
        with Session() as db:
            return db.get(User, actor["id"])
    app.dependency_overrides[get_db] = dbdep
    app.dependency_overrides[get_current_active_user] = auth
    return SimpleNamespace(client=TestClient(app), db=Session, actor=actor, adapter=adapter,
                           minio=minio, redis=fake_redis, tmp=tmp_path)


def connection(world, provider="minio", buckets=None):
    credentials = {"access_key": "test-key", "secret_key": SECRET}
    if provider == "gcs":
        credentials = {"service_account_json": json.dumps({"client_email": "test@example.test", "private_key": SECRET,
                                                           "token_uri": "https://oauth2.googleapis.com/token"})}
    if provider == "azure":
        credentials = {"connection_string": SECRET}
    response = world.client.post("/datalakes", json={"name": provider, "provider": provider,
        "credentials": credentials, "config": {"endpoint": "https://storage.example.test" if provider in ("minio", "s3") else None,
            "buckets": buckets or [], "default_bucket": "first-bucket", "default_prefix": "results"}})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("provider", ["s3", "minio", "gcs", "azure"])
def test_all_provider_connections_encrypt_credentials_and_never_return_them(world, provider):
    c = connection(world, provider)
    assert SECRET not in json.dumps(c)
    assert "credentials" not in c
    with world.db() as db:
        row = db.get(DatalakeConnection, c["id"])
        assert SECRET.encode() not in row.credentials_encrypted
        assert SECRET in json.dumps(unseal(row))
    response = world.client.get("/datalakes")
    assert response.status_code == 200
    assert SECRET not in response.text
    assert world.client.post(f'/datalakes/{c["id"]}/test', json={}).status_code == 200
    assert world.client.get(f'/datalakes/{c["id"]}/buckets').json()["buckets"] == ["first-bucket", "second-bucket"]


def test_edit_preserves_and_rotates_secret(world):
    c = connection(world)
    assert world.client.patch(f'/datalakes/{c["id"]}', json={"name": "Renamed"}).status_code == 200
    with world.db() as db:
        assert unseal(db.get(DatalakeConnection, c["id"]))["secret_key"] == SECRET
    assert world.client.patch(f'/datalakes/{c["id"]}', json={"credentials": {"access_key": "new", "secret_key": "rotated-secret"}}).status_code == 200
    with world.db() as db:
        assert unseal(db.get(DatalakeConnection, c["id"]))["secret_key"] == "rotated-secret"


def completed_export(world):
    c = connection(world)
    with world.db() as db:
        job = Job(id=JOB, user_id="alice", filename="doc.txt", job_type="MAIN", source_type="file", status=JobStatus.COMPLETED)
        db.add(job)
        service.bind_destination(db, job, Destination(connection_id=c["id"], bucket="second-bucket", prefix="out"))
        db.commit()
    payload = {"markdown": "# Hello", "metadata": {"format": "txt", "size_bytes": 5},
               "transcript": {"vtt": "WEBVTT\n", "srt": "", "txt": "Hello", "json": '{"segments":[]}'}}
    service.stage_result(JOB, payload)
    world.redis.client.flushdb()
    return c, payload


def test_export_survives_cache_loss_and_writes_only_chosen_bucket_idempotently(world):
    _, payload = completed_export(world)
    service.export_result(JOB)
    assert len(world.adapter.data) == 7
    assert all(bucket == "second-bucket" and key.startswith(f"out/{JOB}/") for bucket, key in world.adapter.data)
    assert json.loads(world.adapter.data["second-bucket", f"out/{JOB}/result.json"]) == payload
    assert world.adapter.data["second-bucket", f"out/{JOB}/transcript.srt"] == b""
    service.export_result(JOB)
    with world.db() as db:
        dest = db.get(JobDatalakeExport, JOB)
        assert dest.status == "completed" and dest.attempts == 1
    assert world.client.get(f"/jobs/{JOB}/datalake").json()["destination"]["status"] == "completed"


def test_failed_delivery_preserves_completed_job_and_can_retry_without_inference(world):
    completed_export(world)
    world.adapter.fail = True
    with pytest.raises(RuntimeError, match="Datalake delivery failed"):
        service.export_result(JOB)
    with world.db() as db:
        assert db.get(Job, JOB).status == JobStatus.COMPLETED
        dest = db.get(JobDatalakeExport, JOB)
        assert dest.status == "failed" and SECRET not in dest.error
    world.adapter.fail = False
    assert world.client.post(f"/jobs/{JOB}/datalake/retry").status_code == 202
    service.export_result(JOB)
    assert world.client.get(f"/jobs/{JOB}/datalake").json()["destination"]["status"] == "completed"


def test_encrypted_credentials_are_bound_to_owner_and_connection(world):
    c = connection(world)
    with world.db() as db:
        row = db.get(DatalakeConnection, c["id"])
        copied = SimpleNamespace(user_id="bob", id=row.id, credentials_encrypted=row.credentials_encrypted)
        with pytest.raises(ValueError, match="binding"):
            unseal(copied)
        copied.user_id, copied.id = row.user_id, "different-id"
        with pytest.raises(ValueError, match="binding"):
            unseal(copied)


def test_bucket_default_must_be_in_the_selected_allowed_buckets(world):
    c = connection(world)
    response = world.client.patch('/datalakes/' + c['id'], json={"config": {**c['config'], "buckets": ["second-bucket"]}})
    assert response.status_code == 422
    assert world.client.get('/datalakes').json()['connections'][0]['config'] == c['config']


def test_partial_full_image_exports_the_selected_durable_report(world):
    _, _ = completed_export(world)
    report_path = f'images/{JOB}/reports/1-report.json'
    payload = {'markdown': '# Full Analysis\nPartial',
        'metadata': {'format': 'image/png', 'size_bytes': 10, 'analysis_status':'partial'},
        'image': {'operation':'full_analysis', 'analysis_status':'partial', 'results':[
            {'task':'<CAPTION>', 'status':'succeeded', 'text':'Preserved caption'},
            {'task':'<OCR>', 'status':'failed', 'reason_code':'inference_failed'}]}}
    world.minio.data[world.minio.bucket_results, report_path] = json.dumps(payload).encode()
    with world.db() as db:
        job = db.get(Job, JOB)
        job.source_type, job.status, job.minio_result_path = 'image', JobStatus.PARTIAL, report_path
        db.commit()
    service.export_result(JOB)
    exported = json.loads(world.adapter.data['second-bucket', f'out/{JOB}/result.json'])
    assert exported == payload
    assert exported['image']['analysis_status'] == 'partial'
    with world.db() as db:
        assert db.get(Job, JOB).status == JobStatus.PARTIAL
        assert db.get(JobDatalakeExport, JOB).status == 'completed'



def test_partial_image_is_listed_and_filterable_after_cache_loss(world):
    completed_export(world)
    with world.db() as db:
        job = db.get(Job, JOB)
        job.source_type, job.status = 'image', JobStatus.PARTIAL
        db.commit()
    response = world.client.get('/jobs?status=partial&kind=image')
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['counts']['partial'] == 1
    assert payload['total'] == 1
    assert payload['jobs'][0]['job_id'] == JOB
    assert payload['jobs'][0]['status'] == 'partial'
