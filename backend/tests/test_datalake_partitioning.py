"""Immutable user layouts, provider-independent keys and queryable JSONL."""
import json
from datetime import datetime
from types import SimpleNamespace
from urllib.parse import unquote

import pytest
from pydantic import ValidationError

from shared.datalake import service
from shared.datalake.partitioning import (
    PartitionError, PartitionStrategy, analytic_outputs, resolve_layout,
)
from shared.datalake.schemas import Destination
from shared.models import DatalakeConnection, Job, JobDatalakeExport, JobDatalakePartition, JobStatus, LiveSession
from .test_datalakes import JOB, connection, completed_export, world  # noqa: F401


CONTEXT = {"job_id": JOB, "created_at": "2026-10-06T01:30:00Z", "project_id": "p",
           "folder_id": None, "source_type": "file", "filename": "doc.txt"}


def configured(world, strategy, values=None):
    row = connection(world)
    config = {**row["config"], "partitioning": strategy, "default_partition_values": values or {}}
    response = world.client.patch(f'/datalakes/{row["id"]}', json={"config": config})
    assert response.status_code == 200, response.text
    return response.json()


def required_strategy(**extra):
    return {"mode": "custom", "fields": [{"field": "custom", "key": "tenant"}], "missing": "require", **extra}


def snapshot_for(strategy, prefix="out", context=None, values=None):
    strategy = PartitionStrategy.model_validate(strategy)
    context = context or CONTEXT
    return SimpleNamespace(strategy=strategy.model_dump(), context=context, values=values or {},
                           **resolve_layout(strategy, prefix, context, values or {}))


@pytest.mark.parametrize("granularity,expected", [
    ("month", {"year": "2026", "month": "10"}),
    ("day", {"year": "2026", "month": "10", "day": "05"}),
    ("hour", {"year": "2026", "month": "10", "day": "05", "hour": "22"}),
])
def test_date_partitions_apply_timezone_before_truncation(granularity, expected):
    strategy = PartitionStrategy(mode="date", granularity=granularity, timezone="America/Sao_Paulo")
    resolved = resolve_layout(strategy, "out", CONTEXT, {})
    assert resolved["partitions"] == expected
    assert list(resolved["partitions"]) == strategy.keys()


def test_dst_repeated_hour_has_stable_partition_and_distinct_job_objects():
    strategy = PartitionStrategy(mode="date", granularity="hour", timezone="America/New_York")
    first = resolve_layout(strategy, "out", {**CONTEXT, "created_at": "2026-11-01T05:30:00Z"}, {})
    second = resolve_layout(strategy, "out", {**CONTEXT, "created_at": "2026-11-01T06:30:00Z", "job_id": "another-job"}, {})
    assert first["partitions"] == second["partitions"]
    assert first["partitions"]["hour"] == "01"
    assert first["resolved_path"] != second["resolved_path"]


@pytest.mark.parametrize("value", ["a/b=c%20", "a%2Fb", "São Paulo ☕", "..", "x\\y"])
def test_values_round_trip_without_injecting_segments(value):
    strategy = PartitionStrategy.model_validate(required_strategy())
    resolved = resolve_layout(strategy, "out", CONTEXT, {"tenant": value})
    segment = resolved["resolved_path"].split("/")[-2]
    assert segment.startswith("tenant=")
    assert unquote(segment.split("=", 1)[1]) == value
    assert len(resolved["resolved_path"].split("/")) == 4


def test_literal_percent_and_encoded_slash_do_not_collide():
    strategy = PartitionStrategy.model_validate(required_strategy())
    assert resolve_layout(strategy, "", CONTEXT, {"tenant": "a/b"})["resolved_path"] != resolve_layout(strategy, "", CONTEXT, {"tenant": "a%2Fb"})["resolved_path"]


def test_full_key_limit_counts_utf8_bytes_and_percent_encoding():
    strategy = PartitionStrategy.model_validate(required_strategy())
    with pytest.raises(PartitionError, match="1.024"):
        resolve_layout(strategy, "é" * 480, CONTEXT, {"tenant": "hello"})
    with pytest.raises(PartitionError, match="1.024"):
        resolve_layout(strategy, "a" * 700, CONTEXT, {"tenant": "漢" * 128})


@pytest.mark.parametrize("body", [
    {"mode": "custom", "fields": [{"field": "date"}, {"field": "year"}]},
    {"mode": "custom", "fields": [{"field": "custom", "key": "tenant"}] * 2},
    {"mode": "custom", "fields": [{"field": "custom", "key": "job_id"}]},
    {"mode": "date", "timezone": "Definitely/Not_A_Zone"},
])
def test_ambiguous_or_invalid_layouts_are_rejected(body):
    with pytest.raises(ValidationError):
        PartitionStrategy.model_validate(body)


def test_layout_roots_isolate_order_timezone_granularity_and_schema():
    base = {"mode": "custom", "fields": [{"field": "project_id"}, {"field": "date"}]}
    strategies = [base, {**base, "fields": list(reversed(base["fields"]))},
                  {**base, "timezone": "America/Sao_Paulo"}, {**base, "granularity": "month"},
                  {**base, "analytics": "jsonl"}]
    assert len({PartitionStrategy.model_validate(s).layout_id() for s in strategies}) == len(strategies)
    assert PartitionStrategy(mode="project_date").layout_id() == PartitionStrategy.model_validate(base).layout_id()


def test_date_expansion_preserves_custom_field_order():
    strategy = PartitionStrategy.model_validate({"mode": "custom", "granularity": "month",
        "fields": [{"field": "date"}, {"field": "custom", "key": "tenant"}, {"field": "day"}]})
    resolved = resolve_layout(strategy, "out", CONTEXT, {"tenant": "team"})
    assert list(resolved["partitions"]) == ["year", "month", "tenant", "day"]
    assert list(resolved["partitions"]) == strategy.keys()


def test_schema_root_is_not_truncated_by_partition_like_prefix():
    snapshot = snapshot_for({"mode": "date", "analytics": "jsonl"}, prefix="raw/year=legacy")
    outputs = analytic_outputs(snapshot, {"markdown": "Hello"})
    schema = json.loads(outputs[snapshot.schema_path][0])
    assert schema["dataset_root"] == "raw/year=legacy/datasets/" + snapshot.layout_id


@pytest.mark.parametrize("mode", ["none", "date"])
def test_jsonl_retains_context_values_without_adding_directory_dimensions(mode):
    values = {"client_id": "client-42", "conversation_id": "chat-7", "agent_id": "support-agent"}
    snapshot = snapshot_for({"mode": mode, "analytics": "jsonl"}, values=values)
    outputs = analytic_outputs(snapshot, {"text": "Customer conversation"})
    record = json.loads(outputs[snapshot.dataset_path][0])
    assert json.loads(record["partition_values_json"]) == {**values, **snapshot.partitions}
    assert "conversation_id=" not in snapshot.dataset_path
    assert json.loads(outputs[snapshot.schema_path][0])["schema_version"] == 1


def test_jsonl_reports_resolved_fallback_without_losing_other_context():
    snapshot = snapshot_for({"mode": "custom", "fields": [{"field": "custom", "key": "client_id"}],
        "fallback": "unknown", "analytics": "jsonl"},
        values={"client_id": " ", "conversation_id": "chat-7"})
    record = json.loads(analytic_outputs(snapshot, {})[snapshot.dataset_path][0])
    assert json.loads(record["partition_values_json"]) == {"client_id": "unknown", "conversation_id": "chat-7"}


@pytest.mark.parametrize("endpoint", ["/upload", "/convert", "/transcribe"])
def test_api_groups_client_conversations_and_keeps_each_context_in_dataset(world, endpoint):
    strategy = {"mode": "custom", "fields": [{"field": "custom", "key": "tenant_id"},
        {"field": "custom", "key": "client_id"}], "missing": "require", "analytics": "jsonl"}
    c = configured(world, strategy, {"tenant_id": "tenant-1", "agent_id": "default-agent"})
    rows, paths = [], []
    for client_id, conversation_id in [("client-42", "chat-1"), ("client-42", "chat-2"), ("client-99", "chat-3")]:
        values = {"client_id": client_id, "conversation_id": conversation_id, "agent_id": "request-agent"}
        data = {"project_id": "p", "source_type": "file", "datalake_connection_id": c["id"],
            "datalake_bucket": "second-bucket", "datalake_prefix": "conversations",
            "datalake_partition_values": json.dumps(values)}
        filename, mime = (conversation_id + ".mp3", "audio/mpeg") if endpoint == "/transcribe" else (conversation_id + ".txt", "text/plain")
        response = world.client.post(endpoint, data=data, files={"file": (filename, b"hello", mime)})
        assert response.status_code == 200, response.text
        job_id = response.json()["job_id"]
        with world.db() as db:
            job = db.get(Job, job_id)
            job.status = JobStatus.COMPLETED
            db.commit()
            snapshot = db.get(JobDatalakePartition, job_id)
            path = snapshot.dataset_path
            assert snapshot.partitions == {"tenant_id": "tenant-1", "client_id": client_id}
        service.stage_result(job_id, {"transcript": {"txt": "Conversation " + conversation_id}})
        service.export_result(job_id)
        record = json.loads(world.adapter.data["second-bucket", path])
        context = json.loads(record["partition_values_json"])
        assert context == {"tenant_id": "tenant-1", **values}
        assert record["job_id"] == job_id and record["text"] == "Conversation " + conversation_id
        delivery = world.client.get(f"/jobs/{job_id}/datalake").json()["destination"]
        assert delivery["partition_values"] == context
        assert delivery["status"] == "completed"
        rows.append(context)
        paths.append(path)
    # All conversations remain distinct files within one client prefix. Changing
    # clients preserves the layout root while selecting a different partition.
    assert len(set(paths)) == 3
    assert paths[0].rsplit("/", 1)[0] == paths[1].rsplit("/", 1)[0]
    assert paths[2].rsplit("/", 1)[0] != paths[0].rsplit("/", 1)[0]
    assert len({path.split("/client_id=", 1)[0] for path in paths}) == 1
    assert [row["conversation_id"] for row in rows if row["client_id"] == "client-42"] == ["chat-1", "chat-2"]


@pytest.mark.parametrize("endpoint", ["/upload", "/convert", "/transcribe"])
def test_missing_required_field_returns_422_and_rolls_back_submission(world, endpoint):
    c = configured(world, required_strategy())
    data = {"project_id": "p", "source_type": "file", "datalake_connection_id": c["id"], "datalake_bucket": "second-bucket"}
    filename, mime = ("clip.mp3", "audio/mpeg") if endpoint == "/transcribe" else ("doc.txt", "text/plain")
    response = world.client.post(endpoint, data=data, files={"file": (filename, b"hello", mime)})
    assert response.status_code == 422, response.text
    assert "tenant" in response.text
    with world.db() as db:
        assert db.query(Job).count() == db.query(JobDatalakeExport).count() == db.query(JobDatalakePartition).count() == 0
    assert not world.minio.data
    assert not list(world.tmp.rglob("*.txt"))
    assert not list(world.tmp.rglob("*.mp3"))
    assert not world.redis.client.keys("job:*")


@pytest.mark.parametrize("endpoint", ["/upload", "/convert", "/transcribe"])
def test_default_strategy_request_values_and_explicit_legacy_override(world, endpoint):
    c = configured(world, required_strategy(), {"tenant": "default-team"})
    data = {"project_id": "p", "source_type": "file", "datalake_connection_id": c["id"], "datalake_bucket": "second-bucket",
            "datalake_partition_values": json.dumps({"tenant": "request-team"})}
    filename, mime = ("clip.mp3", "audio/mpeg") if endpoint == "/transcribe" else ("doc.txt", "text/plain")
    first = world.client.post(endpoint, data=data, files={"file": (filename, b"hello", mime)})
    assert first.status_code == 200, first.text
    with world.db() as db:
        partition = db.get(JobDatalakePartition, first.json()["job_id"])
        assert partition.partitions == {"tenant": "request-team"}
        assert "tenant=request-team" in partition.resolved_path
    second = world.client.post(endpoint, data={**data, "datalake_partitioning": '{"mode":"none"}'}, files={"file": (filename, b"hello", mime)})
    assert second.status_code == 200, second.text
    assert first.json()["job_id"] != second.json()["job_id"]
    with world.db() as db:
        partition = db.get(JobDatalakePartition, second.json()["job_id"])
        assert partition.partitions == {}
        assert partition.resolved_path == second.json()["job_id"]


def test_preview_reuses_owned_defaults_and_matches_snapshot_without_sdk(world, monkeypatch):
    c = configured(world, {"mode": "project_date", "timezone": "America/Sao_Paulo", "analytics": "jsonl"})
    def forbidden_adapter(_):
        raise AssertionError("Preview must not contact storage")
    monkeypatch.setattr(service, "adapter_for", forbidden_adapter)
    response = world.client.post("/datalakes/partition-preview", json={"connection_id": c["id"], "prefix": "out",
        "created_at": CONTEXT["created_at"], "project_id": "p", "source_type": "file"})
    assert response.status_code == 200, response.text
    preview = response.json()
    with world.db() as db:
        job = Job(id=JOB, user_id="alice", filename="doc.txt", project_id="p", source_type="file",
                  created_at=datetime(2026, 10, 6, 1, 30), status=JobStatus.PENDING)
        db.add(job)
        service.bind_destination(db, job, Destination(connection_id=c["id"], bucket="second-bucket", prefix="out"))
        db.commit()
        partition = db.get(JobDatalakePartition, JOB)
        assert partition.layout_id == preview["layout_id"]
        assert partition.partitions == preview["partitions"]
        assert partition.resolved_path == preview["resolved_path"].replace("00000000-0000-0000-0000-000000000000", JOB)
    world.actor["id"] = "bob"
    assert world.client.post("/datalakes/partition-preview", json={"connection_id": c["id"]}).status_code == 404


def test_required_custom_field_does_not_block_source_browsing_or_bucket_test(world):
    c = configured(world, required_strategy())
    assert world.client.get(f'/datalakes/{c["id"]}/objects', params={"bucket": "first-bucket"}).status_code == 200
    assert world.client.post(f'/datalakes/{c["id"]}/test', json={}).status_code == 200
    missing = world.client.post("/datalakes/partition-preview", json={"connection_id": c["id"]})
    assert missing.status_code == 422 and "tenant" in missing.text


def test_import_preserves_origin_and_missing_field_cleanup(world):
    c = configured(world, required_strategy())
    world.adapter.data["first-bucket", "docs/report.txt"] = b"hello"
    body = {"connection_id": c["id"], "bucket": "first-bucket", "key": "docs/report.txt", "project_id": "p",
        "datalake": {"connection_id": c["id"], "bucket": "second-bucket", "prefix": "out"}}
    response = world.client.post("/datalakes/import", json=body)
    assert response.status_code == 422, response.text
    with world.db() as db:
        assert db.query(Job).count() == 0
    assert not list(world.tmp.rglob("*.download"))
    body["datalake"]["partitioning"] = {"mode": "custom", "fields": [{"field": "source_type"}]}
    response = world.client.post("/datalakes/import", json=body)
    assert response.status_code == 202, response.text
    with world.db() as db:
        partition = db.get(JobDatalakePartition, response.json()["job_id"])
        assert partition.context["source_type"] == "datalake"
        assert partition.partitions == {"source_type": "datalake"}


def test_immutable_keys_and_jsonl_bytes_survive_job_move_default_edit_and_retry(world, monkeypatch):
    c = configured(world, {"mode": "project_date", "timezone": "America/Sao_Paulo", "analytics": "jsonl"},
                   {"tenant_id": "original-tenant", "agent_id": "original-agent"})
    with world.db() as db:
        job = Job(id=JOB, user_id="alice", filename="original.txt", project_id="p", source_type="file",
                  created_at=datetime(2026, 10, 6, 1, 30), status=JobStatus.COMPLETED)
        db.add(job)
        service.bind_destination(db, job, Destination(connection_id=c["id"], bucket="second-bucket", prefix="out",
            partition_values={"client_id": "client-42", "conversation_id": "chat-7"}))
        db.commit()
        partition = db.get(JobDatalakePartition, JOB)
        original_path, dataset_path, schema_path = partition.resolved_path, partition.dataset_path, partition.schema_path
    payload = {"markdown": "Olá", "metadata": {"pages": 2}, "transcript": {"txt": "Transcript text"}}
    service.stage_result(JOB, payload)
    original_put = world.adapter.put
    def fail_on_schema(bucket, key, data, content_type):
        if key == schema_path:
            raise RuntimeError("deliberate failure after dataset write")
        original_put(bucket, key, data, content_type)
    monkeypatch.setattr(world.adapter, "put", fail_on_schema)
    with pytest.raises(RuntimeError, match="Datalake delivery failed"):
        service.export_result(JOB)
    original_bytes = dict(world.adapter.data)
    assert ("second-bucket", dataset_path) in original_bytes
    with world.db() as db:
        job = db.get(Job, JOB)
        job.project_id, job.folder_id, job.filename, job.source_type = "changed-project", "new-folder", "renamed.txt", "url"
        job.created_at = datetime(2030, 1, 1)
        row = db.get(DatalakeConnection, c["id"])
        row.config = {**row.config, "partitioning": {"mode": "none"}, "default_prefix": "changed",
                      "default_partition_values": {"tenant_id": "changed-tenant", "agent_id": "changed-agent"}}
        db.commit()
    monkeypatch.setattr(world.adapter, "put", original_put)
    assert world.client.post(f"/jobs/{JOB}/datalake/retry").status_code == 202
    service.export_result(JOB)
    assert all(world.adapter.data[key] == content for key, content in original_bytes.items())
    record = json.loads(world.adapter.data["second-bucket", dataset_path])
    assert record["filename"] == "original.txt" and record["source_type"] == "file"
    assert record["text"] == "Transcript text"
    assert record["created_at"] == "2026-10-06T01:30:00+00:00"
    assert json.loads(record["partition_values_json"]) == {"tenant_id": "original-tenant", "agent_id": "original-agent",
        "client_id": "client-42", "conversation_id": "chat-7", "project_id": "p", "year": "2026", "month": "10", "day": "05"}
    assert "project_id" not in record
    schema = json.loads(world.adapter.data["second-bucket", schema_path])
    assert [c["name"] for c in schema["partition_columns"]] == ["project_id", "year", "month", "day"]
    assert not set(schema["columns"]) & {c["name"] for c in schema["partition_columns"]}
    assert schema_path.startswith("out/schemas/") and dataset_path.startswith("out/datasets/")
    assert all(key.endswith(".jsonl") for bucket, key in world.adapter.data if key.startswith(schema["dataset_root"] + "/"))
    with world.db() as db:
        assert db.get(JobDatalakePartition, JOB).resolved_path == original_path
        assert db.get(JobDatalakeExport, JOB).status == "completed"


def test_legacy_export_without_partition_snapshot_keeps_exact_old_layout(world):
    _, payload = completed_export(world)
    with world.db() as db:
        db.delete(db.get(JobDatalakePartition, JOB))
        db.commit()
    service.export_result(JOB)
    assert len(world.adapter.data) == 7
    assert all(key.startswith(f"out/{JOB}/") for bucket, key in world.adapter.data)
    assert json.loads(world.adapter.data["second-bucket", f"out/{JOB}/result.json"]) == payload
    delivery = world.client.get(f"/jobs/{JOB}/datalake").json()["destination"]
    assert delivery["partitioning"] is None and delivery["resolved_path"] == f"out/{JOB}"


def test_live_missing_partition_releases_capacity_and_live_origin_is_snapshotted(world, monkeypatch):
    from api import live_routes
    from shared.live.store import LiveStore
    from shared.engine_control import admission
    c = configured(world, required_strategy())
    world.client.app.include_router(live_routes.router)
    store = LiveStore(world.redis.client)
    store.ready({"ready": True, "capacity": 1, "incarnation": "partition-test", "backend": "whisper", "model": "turbo"})
    monkeypatch.setattr(live_routes, "get_store", lambda: store)
    monkeypatch.setattr(live_routes, "get_redis_client", lambda: world.redis)
    monkeypatch.setattr(live_routes, "get_es_client", lambda: SimpleNamespace(job_results_write_ready=lambda: True))
    monkeypatch.setattr(live_routes.get_settings(), "live_transcription_enabled", True)
    monkeypatch.setattr(live_routes.get_settings(), "live_internal_token", "partition-test-" + "x" * 40)
    monkeypatch.setattr(admission, "acquire", lambda *args, **kwargs: [])
    monkeypatch.setattr(admission, "release", lambda tickets: None)
    body = {"project_id": "p", "datalake": {"connection_id": c["id"], "bucket": "second-bucket"}}
    response = world.client.post("/transcribe/live/sessions", json=body)
    assert response.status_code == 422, response.text
    with world.db() as db:
        assert db.query(Job).count() == db.query(LiveSession).count() == 0
    body["datalake"]["partitioning"] = {"mode": "custom", "fields": [{"field": "source_type"}]}
    response = world.client.post("/transcribe/live/sessions", json=body)
    assert response.status_code == 201, response.text
    with world.db() as db:
        partition = db.get(JobDatalakePartition, response.json()["job_id"])
        assert partition.context["source_type"] == "live"
        assert partition.partitions == {"source_type": "live"}


def test_expanded_key_limit_includes_date_components():
    fields = [{"field": "date"}] + [{"field": "custom", "key": f"dimension_{i}"} for i in range(7)]
    assert len(PartitionStrategy(mode="custom", fields=fields, granularity="day").keys()) == 10
    with pytest.raises(ValidationError, match="até 10"):
        PartitionStrategy(mode="custom", fields=fields, granularity="hour")
