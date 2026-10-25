"""Per-convert() Docling telemetry: first vs warm, pages, failure, probe, Redis outage."""
import asyncio
import logging
from types import SimpleNamespace

import pytest

import workers.celery_app  # noqa: F401  (import order used by the worker)
import workers.converter as converter_module
from api import admin_routes
from shared import docling_coldstart as cs
from shared.config import get_settings
from workers.converter import DoclingConverter, get_converter


def _result(status="success", pages=1, errors=()):
    return SimpleNamespace(
        status=SimpleNamespace(value=status),
        input=SimpleNamespace(page_count=pages),
        errors=list(errors),
        document=SimpleNamespace(export_to_markdown=lambda: "x"),
    )


class FakeDocling:
    outcome = None  # a result, or an exception to raise

    def convert(self, path):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome or _result()


@pytest.fixture(autouse=True)
def fake_docling(monkeypatch):
    def init(self, **options):
        self.converter, self.import_error = FakeDocling(), None

    monkeypatch.setattr(DoclingConverter, "__init__", init)
    monkeypatch.setattr(cs, "docling_version", lambda: "2.87.0")
    converter_module._cached_converter.cache_clear()
    get_settings.cache_clear()
    yield
    converter_module._cached_converter.cache_clear()
    get_settings.cache_clear()


@pytest.fixture
def pdf(tmp_path):
    path = tmp_path / "p.pdf"
    path.write_bytes(b"%PDF")
    return path


def _hash(client):
    return client.hgetall(cs.key_for(cs.hour_bucket(), cs.hostname()))


def test_first_and_warm_per_key(pdf, _docling_telemetry_fake_redis, monkeypatch):
    monkeypatch.setenv("DOCLING_CONVERTER_CACHE_SIZE", "1")
    get_settings.cache_clear()
    fast = get_converter("fast")
    fast.convert_to_markdown(pdf)
    fast.convert_to_markdown(pdf)
    data = _hash(_docling_telemetry_fake_redis)
    assert (data["conv:first"], data["conv:warm"], data["conv:first_process"]) == ("1", "1", "1")
    assert float(data["conv_seconds:first"]) > 0

    get_converter("quality").convert_to_markdown(pdf)
    data = _hash(_docling_telemetry_fake_redis)
    assert (data["conv:first"], data["conv:first_process"]) == ("2", "1")

    get_converter("fast").convert_to_markdown(pdf)  # evicted, rebuilt: first again
    assert _hash(_docling_telemetry_fake_redis)["conv:first"] == "3"


def test_failure_counts_page_failed_and_keeps_error(pdf, _docling_telemetry_fake_redis, caplog):
    conv = get_converter("fast")
    conv.converter.outcome = RuntimeError("boom")
    with caplog.at_level(logging.INFO), pytest.raises(Exception, match="Failed to convert document: boom"):
        conv.convert_to_markdown(pdf)
    data = _hash(_docling_telemetry_fake_redis)
    assert (data["conv:failed"], data["pages_failed"], data["pages_ok"]) == ("1", "1", "0")
    assert "result=failed" in caplog.text and "pages=unknown" in caplog.text
    conv.converter.outcome = None
    conv.convert_to_markdown(pdf)  # the weights loaded in the failed call: warm now
    assert _hash(_docling_telemetry_fake_redis)["conv:warm"] == "1"


def test_partial_counts_unopened_pages(pdf, _docling_telemetry_fake_redis, caplog):
    conv = get_converter("fast")
    bad = SimpleNamespace(component_type=SimpleNamespace(value="document_backend"))
    other = SimpleNamespace(component_type=SimpleNamespace(value="pipeline"))
    conv.converter.outcome = _result("partial_success", 3, [bad, other])
    with caplog.at_level(logging.INFO):
        conv.convert_to_markdown(pdf)
    data = _hash(_docling_telemetry_fake_redis)
    assert (data["pages_ok"], data["pages_failed"]) == ("2", "1")
    assert "result=partial" in caplog.text


def test_labels_version_and_admin_row(pdf, _docling_telemetry_fake_redis, caplog):
    with caplog.at_level(logging.INFO):
        get_converter("fast").convert_to_markdown(pdf)
    assert "docling=2.87.0" in caplog.text
    assert "key=ocr0-tab1-img0-pic0" in caplog.text and "accelerator=" in caplog.text
    assert "build_reason=process_start" in caplog.text
    assert _hash(_docling_telemetry_fake_redis)["docling_version"] == "2.87.0"
    row = asyncio.run(admin_routes.docling_cold_starts(admin_user=None)).rows[0]
    assert (row.pages_ok, row.conversions_first, row.docling_version) == (1, 1, "2.87.0")


def test_docling_version_unknown_without_docling(monkeypatch):
    import importlib.metadata as md

    monkeypatch.undo()  # the autouse stub out
    monkeypatch.setattr(md, "version", lambda name: (_ for _ in ()).throw(md.PackageNotFoundError(name)))
    cs.docling_version.cache_clear()
    assert cs.docling_version() == "unknown"
    cs.docling_version.cache_clear()


def test_probe_logs_without_counting(pdf, _docling_telemetry_fake_redis, caplog):
    conv = get_converter("fast")
    _docling_telemetry_fake_redis.flushall()
    with caplog.at_level(logging.INFO):
        conv.convert_to_markdown(pdf, {}, probe=True)
    assert not [k for k in _hash(_docling_telemetry_fake_redis) if k.startswith(("conv", "pages"))]
    assert "probe=true" in caplog.text


def test_new_pid_counts_as_first_again(pdf, _docling_telemetry_fake_redis, monkeypatch):
    conv = get_converter("fast")
    conv.convert_to_markdown(pdf)
    monkeypatch.setattr(cs.os, "getpid", lambda: 424242)  # a forked pool child
    conv.convert_to_markdown(pdf)
    data = _hash(_docling_telemetry_fake_redis)
    assert (data["conv:first"], data["conv:first_process"]) == ("2", "2")


def test_redis_outage_never_breaks_conversion_and_trips_breaker(pdf, monkeypatch):
    import redis

    calls = []

    def down():
        calls.append(1)
        raise redis.exceptions.TimeoutError("slow")

    monkeypatch.setattr(cs, "_redis", down)
    conv = get_converter("fast")  # one write attempt: trips the breaker
    assert conv.convert_to_markdown(pdf)["markdown"] == "x"
    assert conv.convert_to_markdown(pdf)["markdown"] == "x"
    assert len(calls) == 1  # the breaker skipped Redis for the rest of the window


def test_telemetry_bug_never_breaks_conversion(pdf, monkeypatch):
    conv = get_converter("fast")
    monkeypatch.setattr(cs, "docling_version", lambda: 1 / 0)
    assert conv.convert_to_markdown(pdf)["markdown"] == "x"


def test_hot_path_is_one_pipeline_no_reads(pdf, _docling_telemetry_fake_redis, monkeypatch):
    conv = get_converter("fast")
    client = _docling_telemetry_fake_redis
    seen = []
    real_pipeline = client.pipeline
    monkeypatch.setattr(client, "pipeline", lambda *a, **k: seen.append("pipeline") or real_pipeline(*a, **k))
    for name in ("hget", "hgetall"):
        monkeypatch.setattr(client, name, lambda *a, **k: seen.append("read"))
    conv.convert_to_markdown(pdf)
    assert seen == ["pipeline"]


def test_readiness_probe_conversion_is_not_counted(_docling_telemetry_fake_redis, monkeypatch, tmp_path, caplog):
    from workers.engine_control import readiness

    monkeypatch.setenv("INGESTIFY_RUNTIME_REVISION", "r1")
    monkeypatch.setenv("INGESTIFY_RUNTIME_FEATURE", "document_conversion")
    monkeypatch.setenv("INGESTIFY_MODEL_PROFILE", "p")
    monkeypatch.setattr(readiness, "ROOT", tmp_path)
    monkeypatch.setattr(readiness, "_ready", None)
    monkeypatch.setattr("shared.device.resolve_docling_device", lambda: "cpu")
    _docling_telemetry_fake_redis.flushall()
    with caplog.at_level(logging.INFO):
        assert readiness.ensure()["ready"]
    assert not [k for k in _hash(_docling_telemetry_fake_redis) if k.startswith(("conv:", "pages"))]
    assert "probe=true" in caplog.text
