"""
Figure descriptions / OCR of a document conversion (`describe_images`,
`ocr_images`; shared/figure_descriptions.py, workers/figure_tasks.py).

- markdown rewriting: order, escaping, empty texts, image_mode none vs referenced;
- extraction: markers (none) / asset anchors (referenced), tiny figures skipped;
- the describe stage: dedup by sha256 (one vision call per unique image), the
  split-PDF path (pages + merge + describe), one image failing, the limits, the
  stall watchdog, purge_source only after the texts are inlined;
- the operation key (dedup) and the API form fields.

Vision is the stub provider (VISION_PROVIDER=stub, tests/conftest.py); docling
documents are built with docling_core, as in test_conversion_assets.py.
`test_real_florence_figure_description` (opt-in, RUN_REAL_FLORENCE=1) runs the
real Florence-2 path in the worker image.
"""
import os
from types import SimpleNamespace

import pytest

from shared import conversion_assets as ca
from shared import figure_descriptions as fd
from shared.models import Job, JobStatus
from tests.test_conversion_assets import (  # noqa: F401  (fixtures)
    ALICE, JOB_ID, FakeMinio, Session, add_job, document, gradient, limits, run_pages, split_pages, worker,
)
from workers import figure_tasks, tasks
from workers.image_assets import AssetCollector, FigureCollector, encode_png, extract_pictures

pytest.importorskip("docling_core")


# ---------------------------------------------------------------------------
# Markdown rewriting (pure)
# ---------------------------------------------------------------------------

def entry(name, sha, anchor, skip=None):
    return {"name": name, "page": 1, "sha256": sha, "object": f"figures/x/{name}", "anchor": anchor, "skip": skip}


def test_none_mode_replaces_markers_in_document_order_and_omits_empty_lines():
    a, b = "p0001-img01-aaaaaaaaaaaa.png", "p0002-img01-bbbbbbbbbbbb.png"
    markdown = f"# T\n\n{fd.marker(a)}\n\ntext\n\n{fd.marker(b)}"
    results = {"sha-a": {"description": "A chart.", "ocr_text": ""},
               "sha-b": {"description": "", "ocr_text": "Revenue 2024"}}
    out, counts, texts = fd.rewrite(markdown, [entry(a, "sha-a", fd.marker(a)), entry(b, "sha-b", fd.marker(b))],
                                    results, describe=True, ocr=True)
    assert out == ("# T\n\n> **Figure (description, English):** A chart.\n\ntext\n\n"
                   "> **Text in figure (OCR):** Revenue 2024")
    assert counts == {"figures_described": 2, "figures_ocr": 2, "figures_skipped": 0}
    assert texts[a] == {"description": "A chart.", "ocr_text": ""}


def test_referenced_mode_keeps_the_image_line_and_quotes_after_it():
    url = "/jobs/j/assets/p0001-img01-aaaaaaaaaaaa.png"
    markdown = f"intro\n\n![Image]({url})\n\nafter"
    out, counts, _ = fd.rewrite(markdown, [entry("p0001-img01-aaaaaaaaaaaa.png", "s", url)],
                                {"s": {"description": "A cat.", "ocr_text": "MEOW"}}, describe=True, ocr=True)
    assert out == (f"intro\n\n![Image]({url})\n\n> **Figure (description, English):** A cat.\n"
                   f"> **Text in figure (OCR):** MEOW\n\nafter")
    assert counts["figures_described"] == 1 and counts["figures_ocr"] == 1


def test_text_is_escaped_so_it_cannot_break_the_markdown():
    name = "p0001-img01-aaaaaaaaaaaa.png"
    nasty = "line one\r\nline two\x00\x07\n\n\n<!-- hidden -->\tend</s>"
    out, _, _ = fd.rewrite(fd.marker(name), [entry(name, "s", fd.marker(name))],
                           {"s": {"description": None, "ocr_text": nasty}}, describe=True, ocr=True)
    assert out == ("> **Text in figure (OCR):** line one\n> line two\n>\n> &lt;!-- hidden --&gt; end")
    assert "\x00" not in out and "<!--" not in out


def test_long_text_is_cut():
    assert fd.clean_text("word " * 5000, max_chars=20).endswith("…")
    assert len(fd.clean_text("word " * 5000, max_chars=20)) <= 21


def test_a_figure_without_any_text_keeps_the_placeholder_and_counts_as_skipped():
    name = "p0001-img01-aaaaaaaaaaaa.png"
    entries = [entry(name, "s", fd.marker(name)), entry(None, None, None, skip="too_small")]
    out, counts, _ = fd.rewrite(f"{fd.marker(name)}\n\n<!-- image -->", entries,
                                {"s": {"description": None, "ocr_text": None, "error": "TIMEOUT"}},
                                describe=True, ocr=False)
    assert out == "<!-- image -->\n\n<!-- image -->"
    assert counts == {"figures_described": 0, "figures_ocr": 0, "figures_skipped": 2}


def test_only_the_requested_operation_is_inlined():
    name = "p0001-img01-aaaaaaaaaaaa.png"
    out, counts, texts = fd.rewrite(fd.marker(name), [entry(name, "s", fd.marker(name))],
                                    {"s": {"description": "x", "ocr_text": "y"}}, describe=False, ocr=True)
    assert out == "> **Text in figure (OCR):** y"
    assert counts == {"figures_described": 0, "figures_ocr": 1, "figures_skipped": 0}
    assert texts[name]["description"] is None


def test_plan_dedups_by_sha256_and_applies_the_limit():
    entries = [entry("a", "s1", "x"), entry("b", "s1", "y"), entry("c", "s2", "z"),
               entry(None, None, None, skip="too_small"), entry("d", "s3", "w")]
    assert [w["sha256"] for w in fd.plan(entries, 10)] == ["s1", "s2", "s3"]
    assert [w["sha256"] for w in fd.plan(entries, 2)] == ["s1", "s2"]


def test_leftover_markers_never_reach_the_published_markdown():
    assert fd.strip_markers(fd.marker("p0001-img01-aaaaaaaaaaaa.png")) == "<!-- image -->"


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def test_none_mode_extraction_marks_figures_and_stores_them_temporarily():
    storage = FakeMinio()
    big = gradient(200, 150, seed=1)
    doc = document([(1, big), (1, gradient(10, 10, seed=2)), (1, big)])
    figures = FigureCollector(JOB_ID, lambda: storage, settings=limits(conversion_figure_max_count=50))

    markdown = extract_pictures(doc, None, figures)

    sha = __import__("hashlib").sha256(encode_png(big)).hexdigest()
    first, tiny, again = figures.entries
    assert first["name"] == f"p0001-img01-{sha[:12]}.png" and first["anchor"] == fd.marker(first["name"])
    assert tiny["skip"] == "too_small" and again["sha256"] == sha and again["object"] == first["object"]
    assert markdown == f"## Curso de exemplo\n\n{first['anchor']}\n\n<!-- image -->\n\n{again['anchor']}"
    # the same bytes are stored once, in the temporary area, never as an asset
    assert [k[1] for k in storage.objects] == [f"figures/{JOB_ID}/{first['name']}"]


def test_referenced_extraction_uses_the_assets_as_figures():
    storage = FakeMinio()
    doc = document([(1, gradient(200, 150)), (1, gradient(10, 10, seed=2))])
    collector = AssetCollector(JOB_ID, lambda: storage, settings=limits())
    figures = FigureCollector(JOB_ID, lambda: storage, settings=limits(conversion_figure_max_count=50))

    markdown = extract_pictures(doc, collector, figures)

    asset = collector.assets[0]
    assert figures.entries[0]["anchor"] == asset["url"]
    assert figures.entries[0]["object"] == ca.object_name(JOB_ID, asset["name"])
    assert figures.entries[1]["skip"] == "too_small"
    assert f"![Image]({asset['url']})" in markdown
    assert not any(name.startswith("figures/") for _, name in storage.objects)


# ---------------------------------------------------------------------------
# The describe stage (workers)
# ---------------------------------------------------------------------------

class DownloadingMinio(FakeMinio):
    def download_file(self, bucket_name, object_name, file_path=None):
        data = self.objects.get((bucket_name, object_name))
        if data is None:
            raise FileNotFoundError(object_name)
        return data

    def figures(self):
        return sorted(name for _, name in self.objects if name.startswith(f"figures/{JOB_ID}/"))


def add_figure_job(Session, *, image_mode="none", describe=True, ocr=False, purge=False,
                   status=JobStatus.PENDING, pages=None):
    add_job(Session, image_mode=image_mode, purge=purge, status=status, pages=pages)
    with Session() as db:
        job = db.get(Job, JOB_ID)
        ca.save_options(db, job, image_mode, False, describe, ocr)
        db.commit()


@pytest.fixture
def stage(worker, monkeypatch):
    """`worker` plus the describe stage: vision tasks queued in a list, run on demand."""
    minio = DownloadingMinio()
    minio.objects, worker.minio = worker.minio.objects, minio
    monkeypatch.setattr(tasks, "get_minio_client", lambda: minio)
    monkeypatch.setattr(figure_tasks, "_minio", lambda: minio)
    monkeypatch.setattr(figure_tasks, "_redis", lambda: worker.redis)
    es = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
    es.store_job_result.return_value = True
    monkeypatch.setattr(figure_tasks, "_es", lambda: es)
    monkeypatch.setattr(figure_tasks, "SessionLocal", worker.Session)
    monkeypatch.setattr(figure_tasks.conversion_assets, "durable_options",
                        lambda job_id, _factory: ca.job_options(worker.job()))
    monkeypatch.setattr(figure_tasks, "_user_of", lambda job_id: ALICE)
    queued, finalizes, watchdogs, calls = [], [], [], []

    def dispatch(job_id, user_id, kwargs):
        queued.append(kwargs)
        return True

    monkeypatch.setattr(figure_tasks, "_dispatch", dispatch)
    monkeypatch.setattr(figure_tasks.celery_app, "send_task", lambda name, kwargs: finalizes.append(kwargs))
    monkeypatch.setattr(figure_tasks.finalize_figures_task, "apply_async",
                        lambda kwargs, countdown: watchdogs.append((kwargs, countdown)))
    real = figure_tasks.describe_one

    def counted(path, **kw):
        calls.append(path.name)
        return real(path, **kw)

    monkeypatch.setattr(figure_tasks, "describe_one", counted)

    def run_vision(fail=()):
        while queued:
            kwargs = queued.pop(0)
            if kwargs["sha256"] in fail:
                minio.objects.pop((minio.bucket_results, kwargs["object_name"]), None)
            figure_tasks.describe_figure_task.run(**kwargs)

    def finalize(**kw):
        return figure_tasks.finalize_figures_task.run(job_id=JOB_ID, **kw)

    return SimpleNamespace(**{**vars(worker), "minio": minio}, queued=queued, finalizes=finalizes, watchdogs=watchdogs,
                           calls=calls, run_vision=run_vision, finalize=finalize, es=es)


def test_single_document_waits_for_vision_then_inlines_and_completes(stage):
    add_figure_job(stage.Session, describe=True, ocr=True)
    big = gradient(200, 150, seed=1)
    stage.state.make_document = lambda path: document([(1, big), (1, big), (1, gradient(10, 10, seed=3))])

    started = stage.convert()

    # the conversion returned without waiting: the job is still processing at 90%
    assert started["status"] == "describing_figures" and started["figures"] == 1
    assert stage.job().status == JobStatus.PROCESSING
    assert stage.redis.get_job_status(JOB_ID)["progress"] == 90
    assert stage.redis.get_job_result(JOB_ID) is None
    assert len(stage.queued) == 1 and len(stage.watchdogs) == 1  # same image twice -> one vision task

    stage.run_vision()
    assert len(stage.calls) == 1
    assert stage.finalizes == [{"job_id": JOB_ID}]
    assert stage.finalize()["status"] == "completed"

    job = stage.job()
    assert job.status == JobStatus.COMPLETED
    result = stage.redis.get_job_result(JOB_ID)
    quote = ("> **Figure (description, English):** A stub description of a 200x150 image.\n"
             "> **Text in figure (OCR):** Stub <OCR>: 200x150")
    assert result["markdown"] == f"## Curso de exemplo\n\n{quote}\n\n{quote}\n\n<!-- image -->"
    assert (result["figures_described"], result["figures_ocr"], result["figures_skipped"]) == (2, 2, 1)
    assert result["metadata"]["figures"]["figures_described"] == 2
    assert "figures" not in result or not isinstance(result.get("figures"), list)
    assert job.char_count == len(result["markdown"])
    assert stage.minio.figures() == []  # temporary PNGs + pending.json gone
    assert stage.redis.get_job_status(JOB_ID)["status"] == "completed"


def test_referenced_mode_annotates_the_assets_and_the_manifest(stage):
    add_figure_job(stage.Session, image_mode="referenced", describe=True, ocr=False)
    stage.state.make_document = lambda path: document([(1, gradient(200, 150))])

    stage.convert()
    stage.run_vision()
    stage.finalize()

    job = stage.job()
    asset = job.assets_manifest["assets"][0]
    assert asset["description"] == "A stub description of a 200x150 image." and asset["ocr_text"] is None
    assert job.assets_manifest["figures"] == {"figures_described": 1, "figures_ocr": 0, "figures_skipped": 0}
    result = stage.redis.get_job_result(JOB_ID)
    assert f"![Image]({asset['url']})\n\n> **Figure (description, English):** A stub" in result["markdown"]
    assert result["assets"][0]["description"] == asset["description"]
    assert ca.result_fields(job)["figures_described"] == 1
    assert ca.public_asset(asset)["description"] == asset["description"]
    # the asset itself is kept (it is an output), nothing temporary was stored
    assert stage.minio.assets() == [asset["name"]] and stage.minio.figures() == []


def test_one_failing_image_does_not_fail_the_job(stage):
    add_figure_job(stage.Session, describe=True)
    stage.state.make_document = lambda path: document([(1, gradient(200, 150, seed=1)), (1, gradient(90, 90, seed=2))])

    stage.convert()
    failing = stage.queued[1]["sha256"]
    stage.run_vision(fail={failing})
    stage.finalize()

    job = stage.job()
    result = stage.redis.get_job_result(JOB_ID)
    assert job.status == JobStatus.COMPLETED
    assert (result["figures_described"], result["figures_skipped"]) == (1, 1)
    assert result["markdown"].endswith("<!-- image -->")
    assert "figure:" not in result["markdown"]


def test_limits_cap_the_unique_figures_sent_to_vision(stage, monkeypatch):
    monkeypatch.setattr(figure_tasks.settings, "conversion_figure_max_count", 1)
    add_figure_job(stage.Session, describe=True)
    stage.state.make_document = lambda path: document([(1, gradient(60, 60, seed=n)) for n in range(1, 4)])

    stage.convert()
    assert len(stage.queued) == 1
    stage.run_vision()
    stage.finalize()

    result = stage.redis.get_job_result(JOB_ID)
    assert (result["figures_described"], result["figures_skipped"]) == (1, 2)


def test_a_document_without_figures_completes_at_once(stage):
    add_figure_job(stage.Session, describe=True)
    stage.state.make_document = lambda path: document([])

    assert stage.convert()["status"] == "completed"
    assert stage.job().status == JobStatus.COMPLETED and stage.queued == []
    assert stage.redis.get_job_result(JOB_ID)["figures_skipped"] == 0


def test_split_pdf_pages_merge_then_describe(stage):
    add_figure_job(stage.Session, describe=True, ocr=True, pages=[1, 2, 3], status=JobStatus.PROCESSING)
    files = split_pages(stage, 3)
    shared_logo = gradient(70, 70, seed=9)
    stage.state.make_document = lambda path: document(
        [(1, shared_logo)] + ([(1, gradient(80, 60, seed=int(path.stem[-1])))] if path.stem[-1] == "2" else []),
        title=f"Pagina {path.stem[-1]}")

    run_pages(stage, files, order=[2, 3, 1])
    page2 = stage.redis.get_job_result("page-2")
    assert len(page2["figures"]) == 2 and page2["figures"][0]["page"] == 2

    tasks.merge_pages_task.run(**stage.state.merges[0])
    assert stage.job().status == JobStatus.PROCESSING
    # the logo repeated on 3 pages -> one vision task; plus page 2's own figure
    assert len(stage.queued) == 2

    stage.run_vision()
    stage.finalize()

    result = stage.redis.get_job_result(JOB_ID)
    markdown = result["markdown"]
    assert stage.job().status == JobStatus.COMPLETED
    assert markdown.index("Pagina 1") < markdown.index("Pagina 2") < markdown.index("Pagina 3")
    assert markdown.count("A stub description of a 70x70 image.") == 3
    assert markdown.count("A stub description of a 80x60 image.") == 1
    assert (result["figures_described"], result["figures_ocr"], result["figures_skipped"]) == (4, 4, 0)
    assert len(stage.calls) == 2
    assert stage.minio.figures() == []


def test_purge_source_runs_only_after_the_texts_are_inlined(stage):
    add_figure_job(stage.Session, describe=True, purge=True)
    stage.state.make_document = lambda path: document([(1, gradient(200, 150))])

    stage.convert()
    job = stage.job()
    assert job.source_deleted_at is None and job.minio_upload_path is not None
    assert stage.minio.figures()  # the vision worker can still read them

    stage.run_vision()
    assert stage.job().source_deleted_at is None  # vision done, not inlined yet: still kept

    stage.finalize()
    job = stage.job()
    assert job.status == JobStatus.COMPLETED and job.source_deleted_at is not None
    assert stage.minio.figures() == []


def test_the_watchdog_finishes_a_stalled_stage(stage):
    add_figure_job(stage.Session, describe=True)
    stage.state.make_document = lambda path: document([(1, gradient(200, 150, seed=1)), (1, gradient(90, 90, seed=2))])

    stage.convert()
    first = stage.queued.pop(0)
    figure_tasks.describe_figure_task.run(**first)  # the second one never reports
    stage.watchdogs.clear()

    # progress since the last check: re-armed
    assert stage.finalize(watchdog=True, seen=0)["status"] == "waiting"
    assert stage.watchdogs and stage.watchdogs[0][0]["seen"] == 1
    # nothing moved: finish with what there is
    assert stage.finalize(watchdog=True, seen=1)["status"] == "completed"
    result = stage.redis.get_job_result(JOB_ID)
    assert (result["figures_described"], result["figures_skipped"]) == (1, 1)
    # a late finalize is a no-op
    assert stage.finalize()["status"] == "discarded"


def test_a_finalize_before_every_figure_reported_waits(stage):
    add_figure_job(stage.Session, describe=True)
    stage.state.make_document = lambda path: document([(1, gradient(200, 150))])
    stage.convert()
    assert stage.finalize()["status"] == "waiting"
    assert stage.job().status == JobStatus.PROCESSING


def test_jobs_without_the_options_never_enter_the_stage(stage):
    add_job(stage.Session, image_mode="none")
    assert stage.convert()["status"] == "completed"
    assert stage.queued == [] and stage.watchdogs == []
    assert "figures_described" not in stage.redis.get_job_result(JOB_ID)


# ---------------------------------------------------------------------------
# Options, dedup, API
# ---------------------------------------------------------------------------

def test_operation_key_changes_only_when_the_options_are_on():
    from api.projects_api import conversion_operation_key as key

    assert key("fast") == key("fast", "none", False, False, False)
    assert key("fast", describe_images=True) != key("fast")
    assert key("fast", ocr_images=True) != key("fast", describe_images=True)
    assert key("fast", describe_images=True, ocr_images=True) not in {key("fast", describe_images=True),
                                                                       key("fast", ocr_images=True)}


def test_options_are_durable_with_the_job(Session):
    add_figure_job(Session, describe=True, ocr=True)
    with Session() as db:
        options = ca.job_options(db.get(Job, JOB_ID))
    assert options["describe_images"] is True and options["ocr_images"] is True
    assert ca.wants_figures(options) and ca.wants_pictures(options) and not ca.wants_assets(options)


def test_describe_requests_never_reuse_a_job_without_them(Session):
    from api.projects_api import conversion_operation_key, find_duplicate_job

    add_job(Session, image_mode="none", status=JobStatus.COMPLETED, checksum="abc",
            operation_key=conversion_operation_key("fast"))
    location = SimpleNamespace(project_id=None)
    with Session() as db:
        plain, _ = find_duplicate_job(db, ALICE, "abc", location, operation_key=conversion_operation_key("fast"))
        described, _ = find_duplicate_job(db, ALICE, "abc", location,
                                          operation_key=conversion_operation_key("fast", describe_images=True),
                                          assets_requested=True)
    assert plain is not None and described is None


def test_upload_and_convert_document_the_fields():
    from api.main import app

    schema = app.openapi()
    for body in ("Body_upload_and_convert_upload_post", "Body_convert_document_convert_post"):
        fields = schema["components"]["schemas"][body]["properties"]
        assert fields["describe_images"]["default"] is False and "INGLÊS" in fields["describe_images"]["description"]
        assert fields["ocr_images"]["default"] is False
    convert_fields = schema["components"]["schemas"]["Body_convert_document_convert_post"]["properties"]
    assert "docling_preset" in convert_fields


# ---------------------------------------------------------------------------
# Opt-in: the real Florence-2 path (worker image with the HF cache mounted)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(os.environ.get("RUN_REAL_FLORENCE") != "1", reason="opt-in: RUN_REAL_FLORENCE=1")
def test_real_florence_figure_description(tmp_path, monkeypatch):
    from shared.config import get_settings
    from workers.vision import factory

    monkeypatch.setattr(get_settings(), "vision_provider", "florence2")
    factory_reset = getattr(factory, "reset_image_describer", None)
    if factory_reset:
        factory_reset()
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (480, 200), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle([20, 20, 460, 180], outline="black", width=4)
    draw.text((60, 80), "INGESTIFY 2026", fill="black")
    path = tmp_path / "figure.png"
    image.save(path)

    describer = factory.get_image_describer(force_provider="florence2")
    try:
        outcome = figure_tasks.describe_one(path, describe=True, ocr=True, caption_task="<MORE_DETAILED_CAPTION>",
                                            describer=describer)
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"Florence-2 unavailable here: {type(e).__name__}: {e}")
    if outcome.get("errors"):
        pytest.skip(f"Florence-2 unavailable here: {outcome['errors']}")
    print("REAL FLORENCE OUTCOME:", outcome)
    assert outcome["description"]
    assert isinstance(outcome["ocr_text"], str)
    out, counts, _ = fd.rewrite(fd.marker("p0001-img01-aaaaaaaaaaaa.png"),
                                [entry("p0001-img01-aaaaaaaaaaaa.png", "s", fd.marker("p0001-img01-aaaaaaaaaaaa.png"))],
                                {"s": outcome}, describe=True, ocr=True)
    print(out)
    assert out.startswith("> **Figure (description, English):** ") and counts["figures_described"] == 1


def test_figures_go_through_the_vision_route(monkeypatch):
    from shared.engines import dispatch as engine_dispatch

    sent, published = [], []
    monkeypatch.setattr(figure_tasks.describe_figure_task, "apply_async", lambda kwargs: sent.append(kwargs))
    monkeypatch.setattr("shared.iam.remote.remote_use_of", lambda user_id, session_factory=None: None)
    monkeypatch.setattr(engine_dispatch, "publish_sync",
                        lambda factory, usage_id, send: (published.append(usage_id), send()))
    kwargs = {"job_id": JOB_ID, "sha256": "f" * 64, "object_name": "x"}

    monkeypatch.setattr(engine_dispatch, "place_now", lambda **kw: engine_dispatch.Placement("unavailable"))
    assert figure_tasks._dispatch(JOB_ID, ALICE, dict(kwargs)) is False and sent == []

    monkeypatch.setattr(engine_dispatch, "place_now", lambda **kw: engine_dispatch.Placement("placed", usage_id=7))
    assert figure_tasks._dispatch(JOB_ID, ALICE, dict(kwargs)) is True
    assert published == [7] and sent[-1]["usage_id"] == 7

    def broken(**kw):
        raise RuntimeError("routing tables unreadable")

    monkeypatch.setattr(engine_dispatch, "place_now", broken)
    assert figure_tasks._dispatch(JOB_ID, ALICE, dict(kwargs)) is True and "usage_id" not in sent[-1]
