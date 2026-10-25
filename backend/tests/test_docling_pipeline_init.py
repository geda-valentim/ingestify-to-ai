"""DOCLING_INIT_PIPELINE: load the pipeline weights at build time, never fail the build."""
import logging
from types import SimpleNamespace

import pytest

import workers.celery_app  # noqa: F401  (import order used by the worker)
import workers.converter as converter_module
from api import admin_routes
from shared import docling_coldstart as cs
from shared.config import get_settings
from workers.converter import DoclingConverter, get_converter


class FakeDocling:
    raises = None

    def __init__(self):
        self.calls = []

    def initialize_pipeline(self, fmt):
        self.calls.append(fmt)
        if self.raises:
            raise self.raises

    def convert(self, path):
        return SimpleNamespace(
            status=SimpleNamespace(value="success"), input=SimpleNamespace(page_count=1), errors=[],
            document=SimpleNamespace(export_to_markdown=lambda: "x"))


@pytest.fixture(autouse=True)
def fake_docling(monkeypatch):
    holder = SimpleNamespace(inner=FakeDocling, built=[])

    def init(self, **options):
        self.converter, self.import_error, self._pdf_format = holder.inner(), None, "pdf"
        holder.built.append(self.converter)

    monkeypatch.setattr(DoclingConverter, "__init__", init)
    monkeypatch.setattr(cs, "docling_version", lambda: "2.87.0")
    converter_module._cached_converter.cache_clear()
    get_settings.cache_clear()
    yield holder
    converter_module._cached_converter.cache_clear()
    get_settings.cache_clear()


def _on(monkeypatch):
    monkeypatch.setenv("DOCLING_INIT_PIPELINE", "true")
    get_settings.cache_clear()


def _hash(client):
    return client.hgetall(cs.key_for(cs.hour_bucket(), cs.hostname()))


def test_off_by_default(fake_docling, _docling_telemetry_fake_redis, caplog):
    with caplog.at_level(logging.INFO):
        conv = get_converter("fast")
    data = _hash(_docling_telemetry_fake_redis)
    assert conv.converter.calls == []
    assert "pipeline_init=off" in caplog.text and "wrapper_seconds=" in caplog.text
    assert "seconds:process_start" in data and "wrapper_seconds:process_start" in data
    assert not [k for k in data if k.startswith("pipeline_init")]


def test_on_loads_once_and_splits_the_seconds(fake_docling, _docling_telemetry_fake_redis, monkeypatch):
    _on(monkeypatch)
    ticks = iter([0.0, 1.0, 1.0, 5.0, 5.0, 5.0, 9.0, 9.0])  # build 1 s, init 4 s, total 5 s
    monkeypatch.setattr(converter_module, "time", SimpleNamespace(monotonic=lambda: next(ticks, 9.0)))
    conv = get_converter("fast")
    get_converter("fast")  # cache hit
    data = _hash(_docling_telemetry_fake_redis)
    assert conv.converter.calls == ["pdf"]
    assert data["pipeline_init:ok"] == "1"
    assert float(data["wrapper_seconds:process_start"]) == pytest.approx(1.0)
    assert float(data["pipeline_init_seconds:process_start"]) == pytest.approx(4.0)
    assert float(data["seconds:process_start"]) == pytest.approx(5.0)


def test_init_failure_keeps_the_converter(fake_docling, _docling_telemetry_fake_redis, monkeypatch, caplog, tmp_path):
    _on(monkeypatch)

    class Boom(FakeDocling):
        raises = RuntimeError("CUDA out of memory")

    fake_docling.inner = Boom
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF")
    with caplog.at_level(logging.INFO):
        conv = get_converter("fast")
    assert get_converter("fast") is conv  # cached
    conv.convert_to_markdown(pdf)
    assert _hash(_docling_telemetry_fake_redis)["pipeline_init:failed"] == "1"
    assert "docling.pipeline_init failed" in caplog.text
    assert converter_module._build_tracker.peek(("x",)) == "new_options"  # the build was committed


def test_soft_time_limit_propagates_and_caches_nothing(fake_docling, monkeypatch):
    from celery.exceptions import SoftTimeLimitExceeded
    _on(monkeypatch)

    class Slow(FakeDocling):
        raises = SoftTimeLimitExceeded()

    fake_docling.inner = Slow
    with pytest.raises(SoftTimeLimitExceeded):
        get_converter("fast")
    assert not converter_module._converters


@pytest.mark.parametrize("broken", [None, object()])
def test_unavailable_without_initializer(fake_docling, _docling_telemetry_fake_redis, monkeypatch, broken):
    _on(monkeypatch)
    fake_docling.inner = lambda: broken
    get_converter("fast")
    assert _hash(_docling_telemetry_fake_redis)["pipeline_init:unavailable"] == "1"


def test_read_hours_and_endpoint_fields(_docling_telemetry_fake_redis):
    cs.record_cold_start("process_start", 5.0, 3, wrapper_seconds=1.0, pipeline_init_seconds=4.0, pipeline_init="ok")
    row = cs.read_hours(1)[0]
    assert (row["wrapper_seconds_total"], row["pipeline_init_seconds_total"], row["pipeline_init_ok"]) == (1.0, 4.0, 1)
    assert row["pipeline_init_failed"] == row["pipeline_init_unavailable"] == 0
    assert admin_routes.DoclingColdStartRow(**{**row}).pipeline_init_ok == 1


def test_docling_initialize_pipeline_signature():
    pytest.importorskip("docling")
    import inspect
    from docling.document_converter import DocumentConverter
    assert list(inspect.signature(DocumentConverter.initialize_pipeline).parameters) == ["self", "format"]
