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

from api import routes
from shared import conversion_assets as ca
from shared.config import get_settings
from shared import figure_descriptions as fd
from shared.models import Job, JobStatus
from tests.test_conversion_assets import (  # noqa: F401  (fixtures)
    ALICE, JOB_ID, FakeMinio, Session, add_job, api, document, gradient, limits, run_pages, split_pages, worker,
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
    assert [k[1] for k in storage.objects] == [f"figures/{JOB_ID}/{sha}.png"]


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
    from unittest.mock import MagicMock

    minio = DownloadingMinio()
    minio.objects, worker.minio = worker.minio.objects, minio
    monkeypatch.setattr(tasks, "get_minio_client", lambda: minio)
    monkeypatch.setattr(figure_tasks, "_minio", lambda: minio)
    monkeypatch.setattr(figure_tasks, "_redis", lambda: worker.redis)
    es = MagicMock()
    es.store_job_result.return_value = True
    monkeypatch.setattr(figure_tasks, "_es", lambda: es)
    monkeypatch.setattr(figure_tasks, "SessionLocal", worker.Session)
    monkeypatch.setattr(figure_tasks.conversion_assets, "durable_options",
                        lambda job_id, _factory: ca.job_options(worker.job()))
    queued, finalizes, watchdogs, ticks, calls, placements = [], [], [], [], [], []

    def place(job_id, user_id, sha):
        from shared.engines import dispatch as engine_dispatch

        placements.append(sha)
        return engine_dispatch.Placement("today")

    monkeypatch.setattr(figure_tasks, "_place", place)
    monkeypatch.setattr(figure_tasks, "_send", lambda kwargs, usage_id: queued.append(kwargs))
    monkeypatch.setattr(figure_tasks.celery_app, "send_task", lambda name, kwargs: finalizes.append(kwargs))
    monkeypatch.setattr(figure_tasks.finalize_figures_task, "apply_async",
                        lambda kwargs, countdown=None: watchdogs.append((kwargs, countdown)))
    monkeypatch.setattr(figure_tasks.dispatch_figures_task, "apply_async",
                        lambda kwargs, countdown=None: ticks.append((kwargs, countdown)))
    real = figure_tasks.describe_one

    def counted(path, **kw):
        calls.append(path.name)
        return real(path, **kw)

    monkeypatch.setattr(figure_tasks, "describe_one", counted)

    def run_vision(fail=(), limit=None):
        ran = 0
        while queued and (limit is None or ran < limit):
            kwargs = queued.pop(0)
            if kwargs["sha256"] in fail:
                minio.objects.pop((minio.bucket_results, kwargs["object_name"]), None)
            figure_tasks.describe_figure_task.run(**kwargs)
            ran += 1

    def finalize(**kw):
        return figure_tasks.finalize_figures_task.run(job_id=JOB_ID, **kw)

    def set_job(**fields):
        with worker.Session() as db:
            job = db.get(Job, JOB_ID)
            for key, value in fields.items():
                setattr(job, key, value)
            db.commit()

    return SimpleNamespace(**{**vars(worker), "minio": minio}, queued=queued, finalizes=finalizes,
                           watchdogs=watchdogs, ticks=ticks, calls=calls, placements=placements,
                           run_vision=run_vision, finalize=finalize, es=es, set_job=set_job)


def test_single_document_waits_for_vision_then_inlines_and_completes(stage):
    add_figure_job(stage.Session, describe=True, ocr=True)
    big = gradient(200, 150, seed=1)
    stage.state.make_document = lambda path: document([(1, big), (1, big), (1, gradient(10, 10, seed=3))])

    started = stage.convert()

    # the conversion returned without waiting: the job is still processing at 90%
    assert started["status"] == "describing_figures" and started["figures"] == 1
    job = stage.job()
    assert job.status == JobStatus.PROCESSING and job.figures_stage == "describing"
    assert stage.redis.get_job_status(JOB_ID)["progress"] == 90
    assert stage.redis.get_job_result(JOB_ID) is None
    assert len(stage.queued) == 1 and len(stage.watchdogs) == 1  # same image twice -> one vision task

    stage.run_vision()
    assert len(stage.calls) == 1
    assert stage.finalizes == [{"job_id": JOB_ID}]
    assert stage.finalize()["status"] == "completed"

    job = stage.job()
    assert job.status == JobStatus.COMPLETED and job.figures_stage is None
    result = stage.redis.get_job_result(JOB_ID)
    quote = ("> **Figure (description, English):** A stub description of a 200x150 image.\n"
             "> **Text in figure (OCR):** Stub <OCR>: 200x150")
    assert result["markdown"] == f"## Curso de exemplo\n\n{quote}\n\n{quote}\n\n<!-- image -->"
    assert (result["figures_described"], result["figures_ocr"], result["figures_skipped"]) == (2, 2, 1)
    assert result["metadata"]["figures"]["figures_described"] == 2
    assert not isinstance(result.get("figures"), list)
    assert job.char_count == len(result["markdown"])
    stage.es.store_job_result.assert_called_once()
    assert stage.es.store_job_result.call_args.kwargs["markdown_content"] == result["markdown"]
    assert stage.minio.figures() == []  # temporary PNGs + pending.json gone
    assert stage.redis.get_job_status(JOB_ID)["status"] == "completed"
    assert not stage.redis.client.exists(fd.results_key(JOB_ID))


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


def test_figures_are_dispatched_through_a_bounded_window(stage, monkeypatch):
    monkeypatch.setattr(figure_tasks.settings, "conversion_figure_window", 2)
    add_figure_job(stage.Session, describe=True)
    stage.state.make_document = lambda path: document([(1, gradient(60, 60, seed=n)) for n in range(1, 6)])

    stage.convert()
    assert len(stage.queued) == 2 and len(stage.placements) == 2  # placed when sent, never all upfront
    assert figure_tasks.in_flight(JOB_ID) == {k["sha256"] for k in stage.queued}

    stage.run_vision(limit=1)  # one settles -> exactly one more goes
    assert len(stage.queued) == 2 and len(stage.placements) == 3
    stage.run_vision()
    assert len(stage.calls) == 5 and stage.finalizes == [{"job_id": JOB_ID}]
    assert stage.finalize()["figures_described"] == 5


def test_a_full_vision_route_backs_off_instead_of_skipping(stage, monkeypatch):
    from shared.engines import dispatch as engine_dispatch

    outcomes = ["unavailable"]
    monkeypatch.setattr(figure_tasks, "_place",
                        lambda job_id, user_id, sha: engine_dispatch.Placement(outcomes[0], reason="engine:full"))
    add_figure_job(stage.Session, describe=True)
    stage.state.make_document = lambda path: document([(1, gradient(60, 60))])

    stage.convert()
    assert stage.queued == [] and len(stage.ticks) == 1  # retried later, nothing recorded as skipped
    assert stage.redis.client.hlen(fd.results_key(JOB_ID)) == 0
    assert figure_tasks.in_flight(JOB_ID) == set()

    outcomes[0] = "today"
    stage.redis.client.delete(fd.tick_key(JOB_ID))
    assert figure_tasks.dispatch_figures_task.run(job_id=JOB_ID)["sent"] == 1
    stage.run_vision()
    assert stage.finalize()["figures_described"] == 1


def test_send_uses_the_low_priority_and_publish_sync(monkeypatch):
    from shared.engines import dispatch as engine_dispatch

    sent, published = [], []
    monkeypatch.setattr(figure_tasks.describe_figure_task, "apply_async",
                        lambda kwargs, priority=None: sent.append((kwargs, priority)))
    monkeypatch.setattr(engine_dispatch, "publish_sync",
                        lambda factory, usage_id, send: (published.append(usage_id), send()))
    figure_tasks._send({"job_id": JOB_ID}, None)
    figure_tasks._send({"job_id": JOB_ID}, 7)
    assert [p for _, p in sent] == [9, 9] and published == [7] and sent[1][0]["usage_id"] == 7


def test_placement_errors_fall_back_to_the_vision_queue(monkeypatch):
    from shared.engines import dispatch as engine_dispatch

    monkeypatch.setattr("shared.iam.remote.remote_use_of", lambda user_id, session_factory=None: None)

    def broken(**kw):
        raise RuntimeError("routing tables unreadable")

    monkeypatch.setattr(engine_dispatch, "place_now", broken)
    assert figure_tasks._place(JOB_ID, ALICE, "f" * 64).outcome == "today"
    monkeypatch.setattr(engine_dispatch, "place_now", lambda **kw: engine_dispatch.Placement("placed", usage_id=3))
    assert figure_tasks._place(JOB_ID, ALICE, "f" * 64).usage_id == 3


def test_a_document_without_figures_completes_at_once(stage):
    add_figure_job(stage.Session, describe=True)
    stage.state.make_document = lambda path: document([])

    assert stage.convert()["status"] == "completed"
    assert stage.job().status == JobStatus.COMPLETED and stage.queued == []
    assert stage.redis.get_job_result(JOB_ID)["figures_skipped"] == 0
    assert stage.job().figures_stage is None


def test_split_pdf_pages_merge_then_describe(stage):
    add_figure_job(stage.Session, describe=True, ocr=True, pages=[1, 2, 3], status=JobStatus.PROCESSING)
    files = split_pages(stage, 3)
    shared_logo = gradient(70, 70, seed=9)
    stage.state.make_document = lambda path: document(
        [(1, shared_logo)] + ([(1, gradient(80, 60, seed=int(path.stem[-1])))] if path.stem[-1] == "2" else []),
        title=f"Pagina {path.stem[-1]}")

    run_pages(stage, files, order=[2, 3, 1])
    page2 = stage.redis.get_job_result("page-2")
    # public page outputs never carry the markers; the merge reads private fields
    assert "figure:" not in page2["markdown"] and "<!-- image -->" in page2["markdown"]
    assert "figures" not in page2 and len(page2["_figures"]) == 2 and page2["_figures"][0]["page"] == 2
    assert "<!-- figure:" in page2["_figure_markdown"]
    with stage.Session() as db:
        from shared.models import Page
        assert all("figure:" not in (p.markdown_content or "") for p in db.query(Page).all())
    page_mds = [v for (b, k), v in stage.minio.objects.items() if k.startswith(f"results/{JOB_ID}/page_")]
    assert page_mds and all(b"figure:" not in v for v in page_mds)
    from shared.figure_descriptions import public_result
    assert set(public_result(page2)) == {"markdown", "metadata"}

    tasks.merge_pages_task.run(**stage.state.merges[0])
    assert stage.job().status == JobStatus.PROCESSING
    # the logo repeated on 3 pages -> one vision task; plus page 2's own figure
    stage.run_vision()
    assert len(stage.calls) == 2
    stage.finalize()

    result = stage.redis.get_job_result(JOB_ID)
    markdown = result["markdown"]
    assert stage.job().status == JobStatus.COMPLETED
    assert markdown.index("Pagina 1") < markdown.index("Pagina 2") < markdown.index("Pagina 3")
    assert markdown.count("A stub description of a 70x70 image.") == 3
    assert markdown.count("A stub description of a 80x60 image.") == 1
    assert (result["figures_described"], result["figures_ocr"], result["figures_skipped"]) == (4, 4, 0)
    assert stage.minio.figures() == []


def test_a_redelivered_merge_keeps_the_recorded_outcomes(stage):
    add_figure_job(stage.Session, describe=True, pages=[1, 2], status=JobStatus.PROCESSING)
    files = split_pages(stage, 2)
    stage.state.make_document = lambda path: document([(1, gradient(60, 60, seed=int(path.stem[-1])))])
    run_pages(stage, files)
    tasks.merge_pages_task.run(**stage.state.merges[0])
    stage.run_vision(limit=1)
    recorded = stage.redis.client.hlen(fd.results_key(JOB_ID))
    assert recorded == 1

    tasks.merge_pages_task.run(**stage.state.merges[0])  # redelivered
    assert stage.redis.client.hlen(fd.results_key(JOB_ID)) == 1
    stage.run_vision()
    assert len(stage.calls) == 2  # nothing described twice
    stage.finalize()
    assert stage.redis.get_job_result(JOB_ID)["figures_described"] == 2


def test_partial_split_pdf_never_publishes_markers(stage, monkeypatch):
    add_figure_job(stage.Session, describe=True, pages=[1, 2], status=JobStatus.PROCESSING)
    files = split_pages(stage, 2)
    stage.state.make_document = lambda path: document([(1, gradient(60, 60, seed=int(path.stem[-1])))])
    run_pages(stage, {1: files[1]})
    tasks._mark_page_failed("[t]", "page-2", JOB_ID, 2, "boom")

    job = stage.job()
    assert job.status == JobStatus.PARTIAL and job.figures_stage is None
    assert "figure:" not in stage.redis.get_job_result("page-1")["markdown"]
    with stage.Session() as db:
        from shared.models import Page
        assert all("figure:" not in (p.markdown_content or "") for p in db.query(Page).all())
    # kept for a page retry (no purge_source)...
    assert stage.minio.figures()


def test_partial_with_purge_source_drops_the_temporary_figures(stage):
    add_figure_job(stage.Session, describe=True, purge=True, pages=[1, 2], status=JobStatus.PROCESSING)
    files = split_pages(stage, 2)
    stage.state.make_document = lambda path: document([(1, gradient(60, 60, seed=int(path.stem[-1])))])
    run_pages(stage, {1: files[1]})
    tasks._mark_page_failed("[t]", "page-2", JOB_ID, 2, "boom")
    assert stage.job().status == JobStatus.PARTIAL and stage.minio.figures() == []


def test_split_pdf_temporary_figures_have_one_document_wide_cap(stage, monkeypatch):
    monkeypatch.setattr(tasks.settings, "conversion_figure_max_count", 2)
    add_figure_job(stage.Session, describe=True, pages=[1, 2, 3, 4], status=JobStatus.PROCESSING)
    files = split_pages(stage, 4)
    logo = gradient(50, 50, seed=7)
    stage.state.make_document = lambda path: document(
        [(1, logo), (1, gradient(60, 60, seed=int(path.stem[-1])))])
    run_pages(stage, files)
    # the logo (shared slot) + one page's own image: never one PNG per page
    assert len(stage.minio.figures()) == 2


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


def test_the_watchdog_finishes_a_stalled_stage_and_records_why(stage):
    from datetime import datetime, timedelta

    add_figure_job(stage.Session, describe=True)
    stage.state.make_document = lambda path: document([(1, gradient(200, 150, seed=1)), (1, gradient(90, 90, seed=2))])
    stage.convert()
    stage.run_vision(limit=1)  # the second one never reports
    lost = next(iter(figure_tasks.in_flight(JOB_ID)))
    stage.queued.clear()
    stage.watchdogs.clear()

    # recent progress: re-armed
    assert stage.finalize(watchdog=True)["status"] == "waiting" and stage.watchdogs

    # no progress, a figure in flight, the vision queue busy: extended (heartbeat refreshed)
    old = datetime.utcnow() - timedelta(hours=1)
    stage.set_job(figures_stage_at=old)
    stage.redis.client.rpush(get_settings().vision_queue + "\x06\x169", "other-work")
    assert stage.finalize(watchdog=True)["status"] == "waiting"
    assert stage.job().figures_stage_at > old

    # no progress and the queue idle: the in-flight figure is lost -> finish with what there is
    stage.redis.client.delete(get_settings().vision_queue + "\x06\x169")
    stage.set_job(figures_stage_at=old)
    assert stage.finalize(watchdog=True)["status"] == "completed"
    result = stage.redis.get_job_result(JOB_ID)
    assert (result["figures_described"], result["figures_skipped"]) == (1, 1)
    assert result["metadata"]["figures"]["reason"] == "stalled"
    # the late vision task neither runs inference nor recreates the state
    figure_tasks.describe_figure_task.run(job_id=JOB_ID, sha256=lost, object_name="x")
    assert not stage.redis.client.exists(fd.results_key(JOB_ID))
    assert stage.finalize()["status"] == "discarded"


def test_the_hard_deadline_ends_a_stage_waiting_behind_a_busy_queue(stage, monkeypatch):
    add_figure_job(stage.Session, describe=True)
    stage.state.make_document = lambda path: document([(1, gradient(200, 150))])
    stage.convert()
    monkeypatch.setattr(figure_tasks.settings, "conversion_figure_max_stage_seconds", -1)
    assert stage.finalize(watchdog=True)["status"] == "completed"
    assert stage.redis.get_job_result(JOB_ID)["metadata"]["figures"]["reason"] == "deadline"


def test_a_finalize_before_every_figure_reported_waits(stage):
    add_figure_job(stage.Session, describe=True)
    stage.state.make_document = lambda path: document([(1, gradient(200, 150))])
    stage.convert()
    assert stage.finalize()["status"] == "waiting"
    assert stage.job().status == JobStatus.PROCESSING


def test_a_job_failed_by_someone_else_is_still_completed(stage):
    add_figure_job(stage.Session, describe=True)
    stage.state.make_document = lambda path: document([(1, gradient(200, 150))])
    stage.convert()
    stage.set_job(status=JobStatus.FAILED, error_message="stuck")
    stage.run_vision()
    assert stage.finalize()["status"] == "completed"
    job = stage.job()
    assert job.status == JobStatus.COMPLETED and job.error_message is None
    assert "A stub description" in stage.redis.get_job_result(JOB_ID)["markdown"]


def test_the_stuck_monitor_respects_the_heartbeat_and_never_loses_the_conversion(stage, monkeypatch):
    from datetime import datetime, timedelta

    from shared import queries
    from workers import monitoring

    monkeypatch.setattr(queries, "SessionLocal", stage.Session)
    monkeypatch.setattr(monitoring, "SessionLocal", stage.Session)
    add_figure_job(stage.Session, describe=True)
    stage.state.make_document = lambda path: document([(1, gradient(200, 150))])
    stage.convert()
    stage.set_job(started_at=datetime.utcnow() - timedelta(hours=2))

    # started long ago, but the stage's heartbeat is fresh: not stuck
    assert queries.get_stuck_jobs(threshold_minutes=30) == []

    stage.set_job(figures_stage_at=datetime.utcnow() - timedelta(hours=1))
    stuck = queries.get_stuck_jobs(threshold_minutes=30)
    assert [j.id for j in stuck] == [JOB_ID]
    assert monitoring._fail_stuck_job(JOB_ID, stage.redis) is True
    job = stage.job()
    assert job.status == JobStatus.COMPLETED  # completed with placeholders, not FAILED
    result = stage.redis.get_job_result(JOB_ID)
    assert result["figures_skipped"] == 1 and result["metadata"]["figures"]["reason"] == "stuck"
    assert result["markdown"] == "## Curso de exemplo\n\n<!-- image -->"


def test_config_requires_the_stuck_threshold_to_exceed_the_stall():
    from shared.config import Settings

    with pytest.raises(Exception, match="MONITORING_STUCK_JOB_THRESHOLD_MINUTES"):
        Settings(monitoring_stuck_job_threshold_minutes=10, conversion_figure_stall_seconds=900)


def test_a_finalize_that_keeps_failing_completes_with_placeholders(stage, monkeypatch):
    add_figure_job(stage.Session, describe=True)
    stage.state.make_document = lambda path: document([(1, gradient(200, 150))])
    stage.convert()
    stage.run_vision()
    real = figure_tasks.finalize
    calls = []

    def flaky(job_id, pending, results, **kw):
        calls.append(kw.get("reason"))
        if len(calls) == 1:
            raise RuntimeError("elasticsearch exploded mid-way")
        return real(job_id, pending, results, **kw)

    monkeypatch.setattr(figure_tasks, "finalize", flaky)
    assert stage.finalize()["status"] == "completed"
    result = stage.redis.get_job_result(JOB_ID)
    assert stage.job().status == JobStatus.COMPLETED
    assert result["markdown"] == "## Curso de exemplo\n\n<!-- image -->" and result["figures_skipped"] == 1
    assert "finalize_failed" in result["metadata"]["figures"]["reason"]


def test_only_a_lost_pending_result_fails_the_job(stage):
    add_figure_job(stage.Session, describe=True)
    stage.state.make_document = lambda path: document([(1, gradient(200, 150))])
    stage.convert()
    stage.run_vision()
    stage.minio.objects.pop((stage.minio.bucket_results, fd.pending_object(JOB_ID)))
    assert stage.finalize()["status"] == "failed"
    job = stage.job()
    assert job.status == JobStatus.FAILED and "figuras" in job.error_message


def test_post_completion_steps_are_retried_without_refinalizing(stage, monkeypatch):
    add_figure_job(stage.Session, describe=True, purge=True)
    stage.state.make_document = lambda path: document([(1, gradient(200, 150))])
    stage.convert()
    stage.run_vision()
    real_purge = tasks._purge_source_if_requested

    def down(job_id):
        raise ConnectionError("minio down")

    monkeypatch.setattr(tasks, "_purge_source_if_requested", down)
    assert stage.finalize()["status"] == "completed"
    job = stage.job()
    assert job.status == JobStatus.COMPLETED and job.figures_stage == "finishing" and job.source_deleted_at is None
    first = stage.redis.get_job_result(JOB_ID)

    monkeypatch.setattr(tasks, "_purge_source_if_requested", real_purge)
    stage.calls.clear()
    assert stage.finalize()["status"] == "completed"
    job = stage.job()
    assert job.figures_stage is None and job.source_deleted_at is not None
    assert stage.redis.get_job_result(JOB_ID) == first and stage.calls == []


def test_a_late_failure_never_uncompletes_a_job(stage):
    add_job(stage.Session, image_mode="none", status=JobStatus.COMPLETED)
    tasks._record_main_failure(JOB_ID, stage.redis, "late", retrying=False)
    assert stage.job().status == JobStatus.COMPLETED


def test_the_beat_sweep_rearms_stale_stages(stage):
    from datetime import datetime, timedelta

    add_figure_job(stage.Session, describe=True)
    stage.state.make_document = lambda path: document([(1, gradient(200, 150))])
    stage.convert()
    stage.watchdogs.clear()
    assert figure_tasks.sweep() == 0
    stage.set_job(figures_stage_at=datetime.utcnow() - timedelta(hours=1))
    assert figure_tasks.sweep() == 1 and stage.watchdogs[0][0] == {"job_id": JOB_ID, "watchdog": True}


def test_jobs_without_the_options_never_enter_the_stage(stage):
    add_job(stage.Session, image_mode="none")
    assert stage.convert()["status"] == "completed"
    assert stage.queued == [] and stage.watchdogs == []
    assert "figures_described" not in stage.redis.get_job_result(JOB_ID)
    assert stage.job().figures_stage is None


def test_picture_images_only_when_figures_or_referenced_are_requested(monkeypatch):
    seen = []
    monkeypatch.setattr(tasks, "get_converter", lambda preset=None, picture_images=None: seen.append(picture_images))
    tasks._converter_for({"page_images": True}, object(), None)
    tasks._converter_for({"describe_images": True}, None, object())
    tasks._converter_for({"image_mode": "referenced"}, object(), None)
    tasks._converter_for({"docling_preset": "fast"}, None, None)
    assert seen == [False, True, True, None]


def test_delete_job_removes_the_temporary_figures(api, monkeypatch):
    from unittest.mock import MagicMock

    from tests.test_conversion_assets import jwt

    add_figure_job(api.Session, describe=True, status=JobStatus.PROCESSING)
    api.minio.objects[(api.minio.bucket_results, fd.pending_object(JOB_ID))] = b"{}"
    api.minio.objects[(api.minio.bucket_results, fd.figure_object(JOB_ID, "p0001-img01-aaaaaaaaaaaa.png"))] = b"x"
    monkeypatch.setattr(routes, "get_es_client", lambda: MagicMock())

    assert api.client.delete(f"/jobs/{JOB_ID}", headers=jwt()).status_code == 200
    assert not any(k.startswith(f"figures/{JOB_ID}/") for _, k in api.minio.objects)


@pytest.mark.parametrize("endpoint", ["/upload", "/convert"])
def test_the_api_persists_the_figure_options(api, endpoint):
    from shared.models import JobConfiguration
    from tests.test_conversion_assets import post

    r = post(api, endpoint, describe_images="true", ocr_images="true", docling_preset="balanced")
    assert r.status_code == 200, r.text
    api.db.expire_all()
    assert api.db.get(JobConfiguration, r.json()["job_id"]).options == {"describe_images": True, "ocr_images": True}
    assert api.enqueued[-1]["options"]["describe_images"] is True
    assert api.enqueued[-1]["options"]["docling_preset"] == "balanced"
    # another option set is another job, the same one is a duplicate
    assert post(api, endpoint, describe_images="true", ocr_images="true",
                docling_preset="balanced").json()["duplicate"] is True
    assert post(api, endpoint, describe_images="true", docling_preset="balanced").json()["duplicate"] is False


# ---------------------------------------------------------------------------
# Vision priority (Redis transport)
# ---------------------------------------------------------------------------

def test_figure_tasks_route_to_the_vision_queue_at_the_lowest_priority():
    from workers.celery_app import celery_app

    route = celery_app.amqp.router.route({}, figure_tasks.DESCRIBE_TASK, args=(), kwargs={})
    assert route["queue"].name == get_settings().vision_queue and route["priority"] == 9
    interactive = celery_app.amqp.router.route({}, "workers.vision_tasks.describe_image_task", args=(), kwargs={})
    assert interactive["queue"].name == get_settings().vision_queue and not interactive.get("priority")
    assert celery_app.conf.broker_transport_options["priority_steps"] == list(range(10))
    assert celery_app.conf.worker_prefetch_multiplier == 1 and celery_app.conf.task_acks_late is True


def test_interactive_vision_tasks_are_served_before_queued_figures():
    """kombu's Redis transport with the app's transport options: priority 0 first."""
    import fakeredis
    from kombu import Connection, Exchange, Queue
    from kombu.transport import redis as kombu_redis

    from workers.celery_app import celery_app

    server = fakeredis.FakeServer()

    class FakeChannel(kombu_redis.Channel):
        def _create_client(self, asynchronous=False):
            return fakeredis.FakeRedis(server=server)

    class Transport(kombu_redis.Transport):
        Channel = FakeChannel

    options = dict(celery_app.conf.broker_transport_options)
    conn = Connection(transport=Transport, transport_options=options)
    name = get_settings().vision_queue
    queue = Queue(name, Exchange(name), name)
    figure_priority = celery_app.amqp.router.route({}, figure_tasks.DESCRIBE_TASK, args=(), kwargs={})["priority"]
    with conn.Producer() as producer:
        for label, priority in [("figure-1", figure_priority), ("figure-2", figure_priority),
                                ("describe-request", None)]:
            extra = {} if priority is None else {"priority": priority}
            producer.publish({"n": label}, exchange=queue.exchange, routing_key=name, declare=[queue], **extra)
    bound = queue(conn.default_channel)
    order = [bound.get(no_ack=True).payload["n"] for _ in range(3)]
    assert order == ["describe-request", "figure-1", "figure-2"]
    conn.release()


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

