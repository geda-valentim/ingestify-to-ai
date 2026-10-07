"""Configured providers, ownership, per-request bucket and durable delivery."""
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
    monkeypatch.setattr(routes, "_enqueue_maybe_routed", lambda *args, **kwargs: None)
    monkeypatch.setattr(tasks.process_conversion, "delay", lambda *args, **kwargs: None)
    monkeypatch.setattr(tasks.process_conversion, "apply_async", lambda *args, **kwargs: None)
    monkeypatch.setattr(datalake_tasks.export_result, "delay", lambda job_id: None)
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


def test_other_user_cannot_read_rotate_delete_or_use_connection(world):
    c = connection(world)
    world.actor["id"] = "bob"
    assert world.client.get("/datalakes").json() == {"connections": []}
    for method, path, body in [("PATCH", "", {"name": "stolen"}), ("DELETE", "", None),
                                ("POST", "/test", {}), ("GET", "/buckets", None),
                                ("GET", "/objects?bucket=first-bucket", None)]:
        assert world.client.request(method, f'/datalakes/{c["id"]}{path}', json=body).status_code == 404
    response = world.client.post("/upload", data={"project": "Bob", "datalake_connection_id": c["id"], "datalake_bucket": "first-bucket"}, files={"file": ("doc.txt", b"hello")})
    assert response.status_code == 404
    with world.db() as db:
        assert db.query(Job).count() == 0


def test_edit_preserves_and_rotates_secret(world):
    c = connection(world)
    assert world.client.patch(f'/datalakes/{c["id"]}', json={"name": "Renamed"}).status_code == 200
    with world.db() as db:
        assert unseal(db.get(DatalakeConnection, c["id"]))["secret_key"] == SECRET
    assert world.client.patch(f'/datalakes/{c["id"]}', json={"credentials": {"access_key": "new", "secret_key": "rotated-secret"}}).status_code == 200
    with world.db() as db:
        assert unseal(db.get(DatalakeConnection, c["id"]))["secret_key"] == "rotated-secret"


@pytest.mark.parametrize("field,value", [("datalake_bucket", "forbidden"), ("datalake_prefix", "../escape")])
def test_invalid_destination_is_rejected_before_any_job_or_upload(world, field, value):
    c = connection(world, buckets=["first-bucket"])
    data = {"project_id": "p", "datalake_connection_id": c["id"], "datalake_bucket": "first-bucket", field: value}
    response = world.client.post("/upload", data=data, files={"file": ("doc.txt", b"hello")})
    assert response.status_code == 422
    with world.db() as db:
        assert db.query(Job).count() == 0
    assert not world.minio.data


def test_disabled_connection_cannot_receive_new_request(world):
    c = connection(world)
    assert world.client.patch(f'/datalakes/{c["id"]}', json={"enabled": False}).status_code == 200
    response = world.client.post("/upload", data={"project_id": "p", "datalake_connection_id": c["id"], "datalake_bucket": "first-bucket"}, files={"file": ("doc.txt", b"hello")})
    assert response.status_code == 422


@pytest.mark.parametrize("endpoint", ["/upload", "/convert", "/transcribe"])
def test_request_chooses_bucket_independent_of_default_and_stores_destination(world, endpoint):
    c = connection(world)
    data = {"project_id": "p", "source_type": "file", "datalake_connection_id": c["id"],
            "datalake_bucket": "second-bucket", "datalake_prefix": "team/october"}
    filename = "clip.mp3" if endpoint == "/transcribe" else "doc.txt"
    response = world.client.post(endpoint, data=data, files={"file": (filename, b"hello", "audio/mpeg" if endpoint == "/transcribe" else "text/plain")})
    assert response.status_code == 200, response.text
    with world.db() as db:
        dest = db.get(JobDatalakeExport, response.json()["job_id"])
        assert dest.bucket == "second-bucket"
        assert dest.prefix == "team/october"
        assert dest.status == "pending"
    assert world.client.delete(f'/datalakes/{c["id"]}').status_code == 409


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


def test_document_exports_include_private_images_with_portable_references(world):
    _, payload = completed_export(world)
    url = f'/jobs/{JOB}/assets/image_000000_abc123.png'
    object_name = f'results/{JOB}/assets/image_000000_abc123.png'
    payload['markdown'] = f'![Figure]({url})'
    payload['exports'] = {'html': f'<img src="{url}">', 'txt': 'Native text', 'json': '{"name":"native"}'}
    payload['assets'] = [{'name': 'image_000000_abc123.png', 'url': url, 'object_name': object_name, 'content_type': 'image/png'}]
    world.minio.data['results', object_name] = b'PNG'
    service.stage_result(JOB, payload)
    world.redis.client.flushdb()
    service.export_result(JOB)
    base = f'out/{JOB}/'
    assert world.adapter.data['second-bucket', base + 'document.html'] == b'<img src="assets/image_000000_abc123.png">'
    assert world.adapter.data['second-bucket', base + 'document.txt'] == b'Native text'
    assert world.adapter.data['second-bucket', base + 'result.md'] == b'![Figure](assets/image_000000_abc123.png)'
    portable = json.loads(world.adapter.data['second-bucket', base + 'result.json'])
    assert portable['assets'][0]['url'] == 'assets/image_000000_abc123.png'
    assert portable['exports']['html'] == '<img src="assets/image_000000_abc123.png">'
    assert url not in portable['markdown']
    assert payload['assets'][0]['url'] == url  # the source snapshot remains unchanged
    assert world.adapter.data['second-bucket', base + 'assets/image_000000_abc123.png'] == b'PNG'


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


def test_import_reads_selected_bucket_and_submits_output_destination(world):
    c = connection(world)
    world.adapter.data["first-bucket", "docs/report.txt"] = b"hello from lake"
    response = world.client.post("/datalakes/import", json={"connection_id": c["id"], "bucket": "first-bucket", "key": "docs/report.txt",
        "project_id": "p", "datalake": {"connection_id": c["id"], "bucket": "second-bucket", "prefix": "converted"}})
    assert response.status_code == 202, response.text
    with world.db() as db:
        job = db.get(Job, response.json()["job_id"])
        assert job.filename == "report.txt"
        assert db.get(JobDatalakeExport, job.id).bucket == "second-bucket"
    assert not list((world.tmp / "datalake-imports").glob("*.download"))


@pytest.mark.parametrize('operation', ['transcribe', 'detect_language', 'inspect'])
def test_audio_import_preserves_model_controls_format_and_retention(world, monkeypatch, operation):
    from shared.job_configuration import job_configuration
    monkeypatch.setattr(routes.settings, 'audio_transcriber_provider', 'faster-whisper')
    monkeypatch.setattr(routes.settings, 'whisper_model', 'turbo')
    monkeypatch.setattr(routes.settings, 'enable_audio_transcription', True)
    queued = []
    monkeypatch.setattr(tasks.process_conversion, 'apply_async', lambda **kwargs: queued.append(kwargs))
    monkeypatch.setattr('shared.engines.dispatch.submit', lambda **kwargs: kwargs['today']())
    c = connection(world)
    world.adapter.data['first-bucket', 'audio/meeting.wav'] = b'RIFF-fixture'
    requested = {'operation': operation, 'decoding': {'beam_size': 2, 'hotwords': 'Ingestify', 'vad_parameters': {'threshold': .7}},
        'include_timestamps': False, 'include_word_timestamps': operation == 'transcribe', 'output_format': 'json', 'purge_source': True}
    response = world.client.post('/datalakes/import', json={'connection_id': c['id'], 'bucket': 'first-bucket',
        'key': 'audio/meeting.wav', 'project_id': 'p', 'audio_options': requested,
        'datalake': {'connection_id': c['id'], 'bucket': 'second-bucket', 'prefix': 'captions'}})
    assert response.status_code == 202, response.text
    with world.db() as db:
        job = db.get(Job, response.json()['job_id'])
        saved = job_configuration(job)
        assert saved['options']['operation'] == operation and saved['options']['include_timestamps'] is False
        assert saved['options']['include_word_timestamps'] == (operation == 'transcribe')
        assert saved['options']['vad_parameters']['threshold'] == .7 and saved['options']['hotwords'] == 'Ingestify'
        assert saved['options']['output_format'] == 'json' and saved['options']['purge_source'] is True
        assert db.get(JobDatalakeExport, job.id).bucket == 'second-bucket'
    assert queued[0]['queue'] == routes.settings.transcription_queue
    assert queued[0]['kwargs']['options']['beam_size'] == 2
    assert not list((world.tmp / 'datalake-imports').glob('*.download'))


@pytest.mark.parametrize('key,fields', [
    ('audio.wav', {'audio_options': {'decoding': {'task': 'translate'}}}),
    ('audio.wav', {'audio_options': {'operation': 'detect_language', 'decoding': {'language': 'pt'}}}),
    ('audio.wav', {'conversion_options': {'pipeline': {'do_ocr': True}}}),
    ('document.pdf', {'audio_options': {}}),
    ('audio.wav', {'audio_options': {'output_format': 'html'}}),
])
def test_invalid_import_processing_options_fail_before_download(world, monkeypatch, key, fields):
    monkeypatch.setattr(routes.settings, 'whisper_model', 'turbo')
    monkeypatch.setattr(routes.settings, 'audio_transcriber_provider', 'faster-whisper')
    calls = []
    monkeypatch.setattr(world.adapter, 'download', lambda *args: calls.append(args))
    response = world.client.post('/datalakes/import', json={'connection_id': 'unknown', 'bucket': 'first-bucket',
        'key': key, 'project_id': 'p', **fields})
    assert response.status_code == 422, response.text
    assert not calls and not world.minio.data
    with world.db() as db:
        assert db.query(Job).count() == 0


def test_delivery_ownership_and_incomplete_job_fence(world):
    completed_export(world)
    world.actor["id"] = "bob"
    assert world.client.get(f"/jobs/{JOB}/datalake").status_code == 404
    assert world.client.post(f"/jobs/{JOB}/datalake/retry").status_code == 404
    world.actor["id"] = "alice"
    with world.db() as db:
        db.get(Job, JOB).status = JobStatus.PROCESSING
        db.commit()
    service.export_result(JOB)
    assert not world.adapter.data
    assert world.client.post(f"/jobs/{JOB}/datalake/retry").status_code == 409


def test_google_and_azure_sdk_contracts_use_explicit_clients():
    gclient = MagicMock()
    gcs = GCSAdapter({}, {}, client=gclient)
    gcs.put("chosen", "result.txt", b"text", "text/plain")
    gclient.bucket.assert_called_with("chosen")
    gclient.bucket().blob().upload_from_string.assert_called_once_with(b"text", content_type="text/plain", timeout=60)
    aclient = MagicMock()
    azure = AzureAdapter({}, {}, client=aclient)
    azure.put("chosen", "result.txt", b"text", "text/plain")
    aclient.get_blob_client.assert_called_with("chosen", "result.txt")
    assert aclient.get_blob_client().upload_blob.call_args.kwargs["overwrite"] is True
    assert aclient.get_blob_client().upload_blob.call_args.kwargs["content_settings"].content_type == "text/plain"


@pytest.mark.parametrize("adapter_class", [S3Adapter, MinioAdapter])
def test_s3_protocol_upload_uses_the_requested_bucket(adapter_class):
    client = MagicMock()
    adapter = adapter_class({}, {}, client=client)
    adapter.put("chosen-bucket", "result.txt", b"text", "text/plain")
    call = client.put_object.call_args
    assert call.args[:2] == ("chosen-bucket", "result.txt")
    assert call.args[2].read() == b"text"
    assert call.args[3] == 4
    assert ADAPTERS["gcs"] is GCSAdapter and ADAPTERS["azure"] is AzureAdapter


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


def test_reconciliation_recovers_missing_broker_message_and_caps_attempts(world, monkeypatch):
    from datetime import timedelta
    completed_export(world)
    with world.db() as db:
        row = db.get(JobDatalakeExport, JOB)
        row.updated_at = datetime.utcnow() - timedelta(minutes=6)
        db.commit()
    queued = []
    monkeypatch.setattr(datalake_tasks.export_result, "delay", queued.append)
    assert datalake_tasks.reconcile() == {"queued": 1}
    assert queued == [JOB]
    with world.db() as db:
        row = db.get(JobDatalakeExport, JOB)
        row.attempts, row.status = 5, "failed"
        row.updated_at = datetime.utcnow() - timedelta(minutes=6)
        db.commit()
    assert datalake_tasks.reconcile() == {"queued": 0}


def test_sdk_client_construction_never_uses_ambient_credentials(monkeypatch):
    from google.cloud import storage
    from azure.storage.blob import BlobServiceClient
    google_factory, azure_factory = MagicMock(), MagicMock()
    monkeypatch.setattr(storage.Client, "from_service_account_info", google_factory)
    monkeypatch.setattr(BlobServiceClient, "from_connection_string", azure_factory)
    GCSAdapter({"project_id": "selected-project"}, {"service_account_json": '{"client_email":"explicit"}'})
    google_factory.assert_called_once_with({"client_email": "explicit"}, project="selected-project")
    AzureAdapter({}, {"connection_string": SECRET})
    assert azure_factory.call_args.args == (SECRET,)


def test_bucket_import_size_failure_cleans_staging_and_creates_no_job(world, monkeypatch):
    c = connection(world)
    def too_big(bucket, key, path, max_bytes):
        from pathlib import Path
        Path(path).write_bytes(b"partial")
        raise ValueError("too large")
    monkeypatch.setattr(world.adapter, "download", too_big)
    response = world.client.post("/datalakes/import", json={"connection_id": c["id"], "bucket": "first-bucket", "key": "large.pdf", "project_id": "p"})
    assert response.status_code == 413
    assert not list((world.tmp / "datalake-imports").glob("*.download"))
    with world.db() as db:
        assert db.query(Job).count() == 0


def test_exhausted_delivery_ignores_duplicate_messages_until_manual_retry(world):
    completed_export(world)
    with world.db() as db:
        dest = db.get(JobDatalakeExport, JOB)
        dest.status, dest.attempts = "failed", 5
        db.commit()
    service.export_result(JOB)
    assert not world.adapter.data
    assert world.client.post(f"/jobs/{JOB}/datalake/retry").status_code == 202
    service.export_result(JOB)
    assert world.adapter.data


def test_explicit_destination_is_not_silently_lost_if_sql_write_fails(world, monkeypatch):
    c = connection(world)
    def fail(*args):
        raise RuntimeError("database unavailable")
    monkeypatch.setattr(routes, "bind_request_destination", fail)
    response = world.client.post("/upload", data={"project_id": "p", "datalake_connection_id": c["id"], "datalake_bucket": "second-bucket"}, files={"file": ("doc.txt", b"hello")})
    assert response.status_code == 503, response.text
    with world.db() as db:
        assert db.query(Job).count() == 0
    assert not world.minio.data


@pytest.mark.parametrize("provider", ["s3", "minio", "gcs", "azure"])
def test_draft_discovery_uses_owned_credentials_without_saving_changes(world, monkeypatch, provider):
    c = connection(world, provider, buckets=["first-bucket"])
    with world.db() as db:
        row = db.get(DatalakeConnection, c["id"])
        encrypted = row.credentials_encrypted
    drafts = []
    def adapter(draft):
        drafts.append(draft)
        assert unseal(draft)
        return world.adapter
    monkeypatch.setattr(datalake_routes, "adapter_for", adapter)
    response = world.client.post("/datalakes/discover", json={"connection_id": c["id"], "provider": provider, "config": c["config"]})
    assert response.status_code == 200, response.text
    assert response.json()["buckets"] == ["first-bucket", "second-bucket"]
    assert SECRET not in response.text
    assert drafts[0].id != c["id"]
    with world.db() as db:
        assert db.query(DatalakeConnection).count() == 1
        assert db.get(DatalakeConnection, c["id"]).credentials_encrypted == encrypted
        assert db.get(DatalakeConnection, c["id"]).config == c["config"]


def test_new_draft_and_manual_bucket_verification_do_not_persist(world, monkeypatch):
    body = {"provider": "minio", "config": {"endpoint": "https://storage.example.test"},
            "credentials": {"access_key": "test-key", "secret_key": SECRET}}
    assert world.client.post("/datalakes/discover", json=body).status_code == 200
    def forbidden_list():
        raise RuntimeError(SECRET)
    monkeypatch.setattr(world.adapter, "buckets", forbidden_list)
    monkeypatch.setattr(world.adapter, "bucket_exists", lambda bucket: bucket == "first-bucket")
    response = world.client.post("/datalakes/discover", json=body)
    assert response.status_code == 502 and SECRET not in response.text
    response = world.client.post("/datalakes/discover", json={**body, "bucket": "first-bucket"})
    assert response.status_code == 200 and response.json()["buckets"] == ["first-bucket"]
    assert world.client.post("/datalakes/discover", json={**body, "bucket": "missing-bucket"}).status_code == 422
    with world.db() as db:
        assert db.query(DatalakeConnection).count() == 0


def test_draft_discovery_cannot_use_another_users_credentials(world):
    c = connection(world)
    world.actor["id"] = "bob"
    response = world.client.post("/datalakes/discover", json={"provider": "minio", "connection_id": c["id"], "config": c["config"]})
    assert response.status_code == 404 and SECRET not in response.text


def test_bucket_default_must_be_in_the_selected_allowed_buckets(world):
    c = connection(world)
    response = world.client.patch('/datalakes/' + c['id'], json={"config": {**c['config'], "buckets": ["second-bucket"]}})
    assert response.status_code == 422
    assert world.client.get('/datalakes').json()['connections'][0]['config'] == c['config']


@pytest.mark.parametrize('provider,location', [('s3', 'us-east-1'), ('minio', 'us-east-1'), ('gcs', 'southamerica-east1'), ('azure', None)])
def test_create_bucket_with_owned_saved_credentials_keeps_connection_unchanged(world, monkeypatch, provider, location):
    c = connection(world, provider, buckets=['first-bucket'])
    with world.db() as db:
        encrypted = db.get(DatalakeConnection, c['id']).credentials_encrypted
    def adapter(draft):
        assert SECRET in json.dumps(unseal(draft))
        return world.adapter
    monkeypatch.setattr(datalake_routes, 'adapter_for', adapter)
    body = {'connection_id': c['id'], 'provider': provider, 'config': c['config'], 'bucket': 'new-transcripts'}
    if provider == 'gcs':
        body['location'] = location
    response = world.client.post('/datalakes/buckets', json=body)
    assert response.status_code == 201, response.text
    assert response.json() == {'bucket': 'new-transcripts', 'created': True, 'location': location}
    assert world.adapter.created == [('new-transcripts', location)]
    assert SECRET not in response.text
    assert world.client.get('/datalakes').json()['connections'][0] == c
    with world.db() as db:
        assert db.query(DatalakeConnection).count() == 1
        assert db.get(DatalakeConnection, c['id']).credentials_encrypted == encrypted
    # Repeated creation must not alter an existing bucket, including S3 us-east-1.
    assert world.client.post('/datalakes/buckets', json=body).status_code == 409
    assert len(world.adapter.created) == 1


def test_create_bucket_from_new_unsaved_draft_requires_explicit_credentials(world, monkeypatch):
    body = {'provider': 'minio', 'config': {'endpoint': 'https://storage.example.test', 'region': 'sa-east-1'}, 'bucket': 'new-bucket'}
    assert world.client.post('/datalakes/buckets', json=body).status_code == 422
    body['credentials'] = {'access_key': 'test-key', 'secret_key': SECRET}
    def adapter(draft):
        assert unseal(draft) == body['credentials']
        return world.adapter
    monkeypatch.setattr(datalake_routes, 'adapter_for', adapter)
    response = world.client.post('/datalakes/buckets', json=body)
    assert response.status_code == 201 and SECRET not in response.text
    assert world.adapter.created == [('new-bucket', 'sa-east-1')]
    with world.db() as db:
        assert db.query(DatalakeConnection).count() == 0


@pytest.mark.parametrize('provider,bucket', [('s3', 'Uppercase'), ('minio', '192.168.0.1'), ('s3', 'a' * 64), ('s3', 'xn--reserved'), ('s3', 'reserved--x-s3'), ('gcs', 'google-data'), ('gcs', 'a' * 64 + '.data'), ('azure', 'invalid--container'), ('azure', 'invalid.container')])
def test_invalid_new_bucket_is_rejected_before_sdk_call(world, monkeypatch, provider, bucket):
    c = connection(world, provider)
    adapter = MagicMock()
    monkeypatch.setattr(datalake_routes, 'adapter_for', adapter)
    response = world.client.post('/datalakes/buckets', json={'connection_id': c['id'], 'provider': provider, 'config': c['config'], 'bucket': bucket})
    assert response.status_code == 422
    adapter.assert_not_called()


def test_create_bucket_rejects_other_user_and_provider_switch_before_sdk_call(world, monkeypatch):
    c = connection(world)
    adapter = MagicMock()
    monkeypatch.setattr(datalake_routes, 'adapter_for', adapter)
    body = {'connection_id': c['id'], 'provider': 's3', 'config': c['config'], 'bucket': 'new-bucket'}
    assert world.client.post('/datalakes/buckets', json=body).status_code == 422
    world.actor['id'] = 'bob'
    body['provider'] = 'minio'
    assert world.client.post('/datalakes/buckets', json=body).status_code == 404
    adapter.assert_not_called()


@pytest.mark.parametrize('provider,location', [('s3', 'eu-west-1'), ('azure', 'US')])
def test_create_bucket_rejects_location_mismatch(world, provider, location):
    c = connection(world, provider)
    response = world.client.post('/datalakes/buckets', json={'connection_id': c['id'], 'provider': provider, 'config': c['config'], 'bucket': 'new-bucket', 'location': location})
    assert response.status_code == 422 and not world.adapter.created


@pytest.mark.parametrize('code,status,expected', [('AccessDenied', None, 403), (403, None, 403), (None, 403, 403), ('BucketAlreadyExists', None, 409), (None, 409, 409), (None, None, 502)])
def test_create_bucket_provider_errors_are_safe_and_actionable(world, monkeypatch, code, status, expected):
    c = connection(world)
    error = RuntimeError(SECRET)
    error.code, error.status_code = code, status
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(world.adapter, 'create_bucket', fail)
    response = world.client.post('/datalakes/buckets', json={'connection_id': c['id'], 'provider': 'minio', 'config': c['config'], 'bucket': 'new-bucket'})
    assert response.status_code == expected and SECRET not in response.text
    assert world.client.get('/datalakes').json()['connections'][0] == c


@pytest.mark.parametrize('provider', ['s3', 'minio', 'gcs', 'azure'])
def test_create_bucket_sdk_contracts_use_selected_location_and_private_container(provider):
    client = MagicMock()
    credentials = {'access_key': 'key', 'secret_key': SECRET}
    adapter = ADAPTERS[provider]({'endpoint': 'https://storage.example.test', 'region': 'sa-east-1'}, credentials, client=client)
    adapter.create_bucket('new-transcripts', location='southamerica-east1' if provider == 'gcs' else None)
    if provider in ('s3', 'minio'):
        client.make_bucket.assert_called_once_with('new-transcripts', location='sa-east-1')
    elif provider == 'gcs':
        client.create_bucket.assert_called_once_with('new-transcripts', location='southamerica-east1', timeout=30, retry=None)
    else:
        client.create_container.assert_called_once_with('new-transcripts', public_access=None, timeout=30)


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
