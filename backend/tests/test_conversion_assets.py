"""
Image assets of a document conversion (`image_mode`, `page_images` on /upload and
/convert; shared/conversion_assets.py, workers/image_assets.py).

- extraction: every docling PictureItem becomes a PNG under the MAIN job, the
  markdown references it by asset URL (`ImageRefMode.REFERENCED`), skipped ones
  keep the placeholder; `image_mode=none` keeps today's output byte for byte;
- `page_images=true` renders every PDF page (pypdfium2);
- a split PDF: each page job stores its assets with the absolute page number and
  the merge concatenates them in page order, under the MAIN job, with the per-job
  limits applied across pages;
- GET /jobs/{id}/assets/{name}: 200 / 304 / 404 / 410, names validated against
  the job's manifest;
- purge_source: assets are kept when the job settles and deleted by the beat
  ASSET_RETENTION_SECONDS later; DELETE /jobs/{id}/source deletes them at once;
- dedup: image options are part of the conversion operation key.

The docling *models* are never needed here: documents are built with
docling_core directly. `test_real_docling_*` (opt-in) runs the real pipeline and
is skipped when docling's models are not available.
"""
import hashlib
import io
import os
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import workers.celery_app  # noqa: F401  (import order used by the worker)
from api import routes
from shared import conversion_assets as ca
from shared import projects as projects_module
from shared.auth import create_access_token
from shared.config import get_settings
from shared.database import Base, get_db
from shared.job_source import save_purge_option
from shared.models import Job, JobConfiguration, JobStatus, Page, Project, User
from tests import _pdf_samples
from workers import tasks
from workers.converter import DoclingConverter
from workers.image_assets import AssetCollector, encode_png, extract_pictures, render_pages

docling_core = pytest.importorskip("docling_core")
from docling_core.types.doc import (  # noqa: E402
    BoundingBox, CoordOrigin, DocItemLabel, DoclingDocument, ImageRef, ProvenanceItem, Size,
)
from PIL import Image  # noqa: E402

ALICE = "user-alice"
BOB = "user-bob"
JOB_ID = "aaaaaaaa-1111-4222-8333-444444444444"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeStream:
    def __init__(self, data):
        self.data = data
        self.closed = False

    def stream(self, size):
        for start in range(0, len(self.data), size):
            yield self.data[start:start + size]

    def close(self):
        self.closed = True

    def release_conn(self):
        pass


class NoSuchKey(Exception):
    code = "NoSuchKey"


class FakeMinio:
    """Keeps the bytes, so what the workers store is what the API serves."""
    bucket_uploads = "ingestify-uploads"
    bucket_audio = "ingestify-audio"
    bucket_pages = "ingestify-pages"
    bucket_results = "ingestify-results"

    def __init__(self):
        self.objects = {}
        self.deleted = []
        self.fail = False
        self.fail_buckets = set()

    def upload_file(self, bucket_name, object_name, file_data=None, file_path=None, content_type=None):
        if self.fail:
            raise ConnectionError("minio down")
        self.objects[(bucket_name, object_name)] = file_data if file_data is not None else Path(file_path).read_bytes()
        return object_name

    def open_object(self, bucket_name, object_name):
        if self.fail:
            raise ConnectionError("minio down")
        if (bucket_name, object_name) not in self.objects:
            raise NoSuchKey(object_name)
        return FakeStream(self.objects[(bucket_name, object_name)])

    def delete_file(self, bucket_name, object_name):
        if self.fail or bucket_name in self.fail_buckets:
            raise ConnectionError("minio down")
        self.objects.pop((bucket_name, object_name), None)
        self.deleted.append((bucket_name, object_name))
        return True

    def delete_folder(self, bucket_name, folder_prefix):
        if self.fail:
            raise ConnectionError("minio down")
        for key in [k for k in self.objects if k[0] == bucket_name and k[1].startswith(folder_prefix)]:
            del self.objects[key]
        self.deleted.append((bucket_name, folder_prefix))
        return True

    def file_exists(self, bucket_name, object_name):
        return True

    def assets(self, job_id=JOB_ID):
        prefix = ca.asset_prefix(job_id)
        return sorted(name[len(prefix):] for bucket, name in self.objects
                      if bucket == self.bucket_results and name.startswith(prefix))


def limits(**overrides):
    values = dict(conversion_asset_min_px=32, conversion_asset_max_count=500, conversion_asset_max_total_mb=200,
                  conversion_page_image_dpi=72)
    values.update(overrides)
    return SimpleNamespace(**values)


def gradient(width, height, seed=1):
    image = Image.new("RGB", (width, height))
    image.putdata([((x * 7 + seed * 40) % 256, (y * 5 + seed * 90) % 256, seed * 30 % 256)
                   for y in range(height) for x in range(width)])
    return image


def picture_prov(page_no, l=100, t=526, r=400, b=300):
    return ProvenanceItem(page_no=page_no, bbox=BoundingBox(l=l, t=t, r=r, b=b, coord_origin=CoordOrigin.BOTTOMLEFT),
                          charspan=(0, 0))


def document(pictures, pages=1, title="Curso de exemplo"):
    """A docling_core document like docling's PDF pipeline produces: `pictures` = [(page_no, PIL image)]."""
    doc = DoclingDocument(name="curso")
    for number in range(1, pages + 1):
        doc.add_page(page_no=number, size=Size(width=612, height=792))
    doc.add_text(label=DocItemLabel.SECTION_HEADER, text=title,
                 prov=ProvenanceItem(page_no=1, bbox=BoundingBox(l=72, t=740, r=300, b=720,
                                                                 coord_origin=CoordOrigin.BOTTOMLEFT),
                                     charspan=(0, len(title))))
    for page_no, image in pictures:
        doc.add_picture(image=ImageRef.from_pil(image, dpi=72), prov=picture_prov(page_no))
    return doc


def converter_for(make_document):
    """A real DoclingConverter whose docling pipeline returns `make_document(path)`."""
    converter = DoclingConverter.__new__(DoclingConverter)
    inner = MagicMock()
    inner.convert.side_effect = lambda path: SimpleNamespace(document=make_document(Path(path)))
    converter.converter = inner
    return converter


# ---------------------------------------------------------------------------
# Extraction (no docling models)
# ---------------------------------------------------------------------------

def test_referenced_pictures_become_assets_referenced_from_the_markdown():
    storage = FakeMinio()
    big = gradient(200, 150, seed=1)
    doc = document([(1, big), (1, gradient(10, 10, seed=2)), (2, gradient(64, 64, seed=3))], pages=2)
    collector = AssetCollector(JOB_ID, lambda: storage, settings=limits())

    markdown = extract_pictures(doc, collector)

    assets = collector.ordered()
    png = encode_png(big)
    sha = hashlib.sha256(png).hexdigest()
    first = assets[0]
    assert first["name"] == f"p0001-img01-{sha[:12]}.png"
    assert first["kind"] == "picture" and first["page"] == 1 and first["sha256"] == sha
    assert (first["width"], first["height"], first["size_bytes"], first["mime"]) == (200, 150, len(png), "image/png")
    assert first["url"] == f"/jobs/{JOB_ID}/assets/{first['name']}"
    # page coordinates, top-left origin (792 - 526 = 266)
    assert first["bbox"] == {"l": 100.0, "t": 266.0, "r": 400.0, "b": 492.0, "coord_origin": "TOPLEFT",
                             "page_width": 612.0, "page_height": 792.0}
    assert storage.objects[(storage.bucket_results, f"assets/{JOB_ID}/{first['name']}")] == png
    # the 10x10 picture is below CONVERSION_ASSET_MIN_PX: skipped, placeholder kept
    assert [a["page"] for a in assets] == [1, 2]
    assert assets[1]["name"].startswith("p0002-img01-")
    assert collector.skipped == {"too_small": 1, "count_limit": 0, "size_limit": 0, "unavailable": 0}
    assert markdown == (f"## Curso de exemplo\n\n![Image]({first['url']})\n\n<!-- image -->\n\n"
                        f"![Image]({assets[1]['url']})")
    assert "data:image" not in markdown


def test_image_mode_none_keeps_todays_output(tmp_path):
    source = tmp_path / "curso.pdf"
    source.write_bytes(_pdf_samples.text_and_image_pdf())
    converter = converter_for(lambda path: document([(1, gradient(200, 150))]))

    result = converter.convert_to_markdown(source, {"docling_preset": "fast"})

    assert result["markdown"] == document([(1, gradient(200, 150))]).export_to_markdown()
    assert result["markdown"] == "## Curso de exemplo\n\n<!-- image -->"
    assert "assets" not in result


def test_count_and_size_limits_record_what_was_skipped():
    storage = FakeMinio()
    pictures = [(1, gradient(40, 40, seed=n)) for n in range(1, 5)]
    collector = AssetCollector(JOB_ID, lambda: storage, settings=limits(conversion_asset_max_count=2))
    markdown = extract_pictures(document(pictures), collector)
    assert len(collector.assets) == 2 and collector.skipped["count_limit"] == 2
    assert markdown.count("![Image](") == 2 and markdown.count("<!-- image -->") == 2

    tiny_budget = AssetCollector(JOB_ID, lambda: FakeMinio(), settings=limits(conversion_asset_max_total_mb=0))
    extract_pictures(document(pictures), tiny_budget)
    assert tiny_budget.assets == [] and tiny_budget.skipped["size_limit"] == 4


def test_page_images_render_every_page(tmp_path):
    source = tmp_path / "curso.pdf"
    source.write_bytes(_pdf_samples.course_pdf())
    storage = FakeMinio()
    collector = AssetCollector(JOB_ID, lambda: storage, settings=limits(conversion_page_image_dpi=150))

    assert render_pages(source, collector) == 3

    pages = collector.ordered()
    assert [(a["kind"], a["page"]) for a in pages] == [("page", 1), ("page", 2), ("page", 3)]
    # 612 x 792 pt at 150 DPI (pdfium rounds the height up)
    assert all(a["width"] == 1275 and a["height"] in (1650, 1651) for a in pages)
    assert all(a["bbox"] is None and a["name"].startswith(f"p{a['page']:04d}-page-") for a in pages)
    stored = storage.objects[(storage.bucket_results, ca.object_name(JOB_ID, pages[1]["name"]))]
    assert hashlib.sha256(stored).hexdigest() == pages[1]["sha256"]
    assert Image.open(io.BytesIO(stored)).format == "PNG"


def test_page_images_without_image_mode_leave_the_markdown_alone(tmp_path):
    source = tmp_path / "curso.pdf"
    source.write_bytes(_pdf_samples.course_pdf())
    storage = FakeMinio()
    converter = converter_for(lambda path: document([(1, gradient(200, 150))], pages=3))

    result = converter.convert_to_markdown(source, {"page_images": True},
                                           assets=AssetCollector(JOB_ID, lambda: storage, settings=limits()))

    assert result["markdown"] == "## Curso de exemplo\n\n<!-- image -->"
    assert [a["kind"] for a in result["assets"]] == ["page"] * 3
    assert result["assets_skipped"]["too_small"] == 0


def test_ordering_is_page_then_page_render_then_pictures(tmp_path):
    source = tmp_path / "curso.pdf"
    source.write_bytes(_pdf_samples.course_pdf())
    storage = FakeMinio()
    converter = converter_for(lambda path: document(
        [(1, gradient(50, 50, 1)), (1, gradient(60, 60, 2)), (3, gradient(70, 70, 3))], pages=3))

    result = converter.convert_to_markdown(source, {"image_mode": "referenced", "page_images": True},
                                           assets=AssetCollector(JOB_ID, lambda: storage, settings=limits()))

    assert [(a["page"], a["kind"], a["name"][:11]) for a in result["assets"]] == [
        (1, "page", "p0001-page-"), (1, "picture", "p0001-img01"), (1, "picture", "p0001-img02"),
        (2, "page", "p0002-page-"), (3, "page", "p0003-page-"), (3, "picture", "p0003-img01")]


# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------

@pytest.fixture
def Session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add_all([User(id=ALICE, email="alice@example.com", username="alice", hashed_password="x"),
                    User(id=BOB, email="bob@example.com", username="bob", hashed_password="x")])
        db.commit()
    return factory


def add_job(Session, *, image_mode="referenced", page_images=False, purge=False, status=JobStatus.PENDING,
            pages=None, user_id=ALICE, checksum=None, project_id=None, operation_key=None, job_id=JOB_ID):
    with Session() as db:
        job = Job(id=job_id, user_id=user_id, filename="curso.pdf", name="curso.pdf", job_type="MAIN",
                  source_type="file", status=status, minio_upload_path=f"uploads/{job_id}/curso.pdf",
                  total_pages=len(pages) if pages else None, file_checksum=checksum, project_id=project_id,
                  operation_key=operation_key, created_at=datetime(2026, 10, 1, 8, 0, 0))
        db.add(job)
        ca.save_options(db, job, image_mode, page_images)
        if purge:
            save_purge_option(db, job)
        for number in (pages or []):
            db.add(Page(job_id=job_id, page_number=number, page_job_id=f"page-{number}", status=JobStatus.PENDING,
                        minio_page_path=f"pages/{job_id}/page_{number:04d}.pdf"))
        db.commit()


@pytest.fixture
def worker(Session, fake_redis, tmp_path, monkeypatch):
    minio = FakeMinio()
    es = MagicMock()
    es.store_job_result.return_value = True
    es.store_page_result.return_value = True
    state = SimpleNamespace(make_document=lambda path: document([(1, gradient(200, 150))]), merges=[])
    converter = converter_for(lambda path: state.make_document(path))

    monkeypatch.setattr(tasks.settings, "temp_storage_path", str(tmp_path))
    monkeypatch.setattr(get_settings(), "temp_storage_path", str(tmp_path))
    monkeypatch.setattr(get_settings(), "conversion_page_image_dpi", 72)
    monkeypatch.setattr(tasks, "SessionLocal", Session)
    monkeypatch.setattr(tasks, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(tasks, "get_es_client", lambda: es)
    monkeypatch.setattr(tasks, "get_minio_client", lambda: minio)
    monkeypatch.setattr(tasks, "get_converter", lambda *a, **kw: converter)
    monkeypatch.setattr(tasks, "should_split_pdf", lambda *a, **kw: False)
    monkeypatch.setattr(tasks.merge_pages_task, "delay", lambda **kw: state.merges.append(kw))

    def upload(content=None):
        directory = tmp_path / "uploads" / JOB_ID
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "curso.pdf"
        path.write_bytes(content or _pdf_samples.text_and_image_pdf())
        return path

    def convert(options=None):
        return tasks.process_conversion.run(job_id=JOB_ID, source_type="file", source=str(upload()),
                                            options=options if options is not None else {"docling_preset": "fast"})

    def job():
        with Session() as db:
            job = db.get(Job, JOB_ID)
            job.configuration_row, job.pages
            return job

    return SimpleNamespace(convert=convert, job=job, minio=minio, redis=fake_redis, state=state, tmp=tmp_path,
                           Session=Session, converter=converter)


def test_single_document_referenced_stores_assets_manifest_and_result(worker):
    add_job(worker.Session, image_mode="referenced", page_images=True)

    # The Celery message carries no image options: they come from the DB
    assert worker.convert({"docling_preset": "fast"})["status"] == "completed"

    job = worker.job()
    assets = job.assets_manifest["assets"]
    assert [(a["kind"], a["page"]) for a in assets] == [("page", 1), ("picture", 1)]
    assert worker.minio.assets() == sorted(a["name"] for a in assets)
    result = worker.redis.get_job_result(JOB_ID)
    assert f"![Image](/jobs/{JOB_ID}/assets/{assets[1]['name']})" in result["markdown"]
    assert [a["name"] for a in result["assets"]] == [a["name"] for a in assets]
    assert "position" not in result["assets"][0]
    assert job.assets_expire_at is None and ca.assets_available(job)


def test_a_job_without_image_options_converts_exactly_as_before(worker):
    add_job(worker.Session, image_mode="none")

    worker.convert()

    job = worker.job()
    assert job.assets_manifest is None and worker.minio.assets() == []
    result = worker.redis.get_job_result(JOB_ID)
    assert result["markdown"] == "## Curso de exemplo\n\n<!-- image -->"
    assert "assets" not in result
    worker.converter.converter.convert.assert_called_once()


def split_pages(worker, count):
    """Page files of a split PDF and their page jobs, as split_pdf_task leaves them."""
    files = {}
    worker.redis.set_job_status(job_id=JOB_ID, job_type="main", status="processing", progress=20)
    for number in range(1, count + 1):
        path = worker.tmp / JOB_ID / "pages" / f"page_{number:04d}.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_pdf_samples.pdf([_pdf_samples.text_page(f"Pagina {number}")]))
        files[number] = path
        worker.redis.add_child_job(JOB_ID, "page", f"page-{number}")
    worker.redis.set_job_pages(JOB_ID, count)
    return files


def run_pages(worker, files, order=None):
    for number in order or sorted(files):
        tasks.convert_page_task.run(page_job_id=f"page-{number}", parent_job_id=JOB_ID, page_number=number,
                                    page_file_path=str(files[number]), options={"docling_preset": "fast"})


def test_split_pdf_assets_are_merged_in_page_order_under_the_main_job(worker):
    add_job(worker.Session, image_mode="referenced", page_images=True, pages=[1, 2, 3], status=JobStatus.PROCESSING)
    files = split_pages(worker, 3)
    # Each page job's document is one page (page_no 1 locally); pages 1 and 3 have a picture
    worker.state.make_document = lambda path: document(
        [(1, gradient(80, 60, seed=int(path.stem[-1])))] if path.stem[-1] in "13" else [],
        title=f"Pagina {path.stem[-1]}")

    run_pages(worker, files, order=[3, 1, 2])  # completion order does not matter
    page3 = worker.redis.get_job_result("page-3")
    assert [(a["kind"], a["page"]) for a in page3["assets"]] == [("page", 3), ("picture", 3)]
    assert all(a["url"].startswith(f"/jobs/{JOB_ID}/assets/p0003-") for a in page3["assets"])

    assert len(worker.state.merges) == 1
    tasks.merge_pages_task.run(**worker.state.merges[0])

    job = worker.job()
    assert job.status == JobStatus.COMPLETED
    assets = job.assets_manifest["assets"]
    assert [(a["page"], a["kind"]) for a in assets] == [
        (1, "page"), (1, "picture"), (2, "page"), (3, "page"), (3, "picture")]
    assert all(a["url"] == f"/jobs/{JOB_ID}/assets/{a['name']}" for a in assets)
    assert all(a["name"].startswith(f"p{a['page']:04d}-") for a in assets)
    merged = worker.redis.get_job_result(JOB_ID)
    pictures = [a for a in assets if a["kind"] == "picture"]
    assert merged["markdown"].index(pictures[0]["url"]) < merged["markdown"].index(pictures[1]["url"])
    assert [a["name"] for a in merged["assets"]] == [a["name"] for a in assets]
    assert worker.minio.assets() == sorted(a["name"] for a in assets)


def test_the_merge_applies_the_job_limits_across_pages(worker, monkeypatch):
    monkeypatch.setattr(tasks.settings, "conversion_asset_max_count", 2)
    add_job(worker.Session, image_mode="referenced", pages=[1, 2, 3], status=JobStatus.PROCESSING)
    files = split_pages(worker, 3)
    worker.state.make_document = lambda path: document([(1, gradient(50, 50, seed=int(path.stem[-1])))])

    run_pages(worker, files)
    tasks.merge_pages_task.run(**worker.state.merges[0])

    job = worker.job()
    assert [a["page"] for a in job.assets_manifest["assets"]] == [1, 2]
    assert job.assets_manifest["skipped"]["count_limit"] == 1
    merged = worker.redis.get_job_result(JOB_ID)["markdown"]
    assert merged.count("![Image](") == 2 and merged.count("<!-- image -->") == 1
    assert worker.minio.assets() == sorted(a["name"] for a in job.assets_manifest["assets"])


def test_purge_source_keeps_the_assets_and_schedules_their_expiry(worker):
    add_job(worker.Session, image_mode="referenced", purge=True)
    before = datetime.utcnow()

    worker.convert()

    job = worker.job()
    assert job.minio_upload_path is None and job.source_deleted_at is not None  # the source went
    assert worker.minio.assets() and ca.assets_available(job)  # the assets did not
    retention = timedelta(seconds=get_settings().asset_retention_seconds)
    assert before + retention <= job.assets_expire_at <= datetime.utcnow() + retention


def test_the_beat_deletes_expired_assets_once(worker, monkeypatch):
    add_job(worker.Session, image_mode="referenced", purge=True)
    worker.convert()
    expire_at = worker.job().assets_expire_at

    assert ca.expire_due_assets(worker.Session, lambda: worker.minio, now=expire_at - timedelta(seconds=1)) == 0
    assert worker.minio.assets()

    from workers import image_full_tasks
    monkeypatch.setattr(image_full_tasks, "SessionLocal", worker.Session)
    monkeypatch.setattr(image_full_tasks, "get_minio_client", lambda: worker.minio)
    monkeypatch.setattr(ca, "datetime", SimpleNamespace(utcnow=lambda: expire_at + timedelta(seconds=1)))
    assert image_full_tasks.expire_conversion_assets(force=True) == 1

    job = worker.job()
    assert worker.minio.assets() == [] and job.assets_deleted_at is not None
    assert not ca.assets_available(job) and job.assets_manifest["assets"]  # the manifest stays (410)
    assert image_full_tasks.expire_conversion_assets(force=True) == 0  # idempotent


def test_the_beat_retries_a_failed_deletion(worker):
    add_job(worker.Session, image_mode="referenced", purge=True)
    worker.convert()
    later = worker.job().assets_expire_at + timedelta(seconds=1)
    worker.minio.fail = True

    assert ca.expire_due_assets(worker.Session, lambda: worker.minio, now=later) == 0
    assert worker.job().assets_deleted_at is None

    # postponed (backoff), so it never blocks the oldest-first batch
    postponed = worker.job().assets_expire_at
    assert postponed == later + timedelta(seconds=ca.ASSET_EXPIRY_RETRY_SECONDS)
    worker.minio.fail = False
    assert ca.expire_due_assets(worker.Session, lambda: worker.minio, now=later) == 0
    assert ca.expire_due_assets(worker.Session, lambda: worker.minio, now=postponed) == 1


def test_options_are_durable_for_page_retries(worker):
    add_job(worker.Session, image_mode="referenced", pages=[1, 2], status=JobStatus.PROCESSING)
    files = split_pages(worker, 2)

    # A page retry's message carries only the preset: the DB supplies image_mode
    run_pages(worker, files)

    assert worker.redis.get_job_result("page-1")["assets"][0]["kind"] == "picture"


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@pytest.fixture
def api(Session, fake_redis, tmp_path, monkeypatch):
    minio = FakeMinio()
    enqueued = []
    db = Session()
    monkeypatch.setattr(routes.settings, "temp_storage_path", str(tmp_path))
    monkeypatch.setattr(get_settings(), "temp_storage_path", str(tmp_path))
    monkeypatch.setattr(projects_module.get_settings(), "upload_fallback_project", "")
    monkeypatch.setattr(routes, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(routes, "get_minio_client", lambda: minio)
    es = MagicMock()
    es.get_job_result.return_value = None
    monkeypatch.setattr(routes, "get_es_client", lambda: es)
    monkeypatch.setattr(tasks.process_conversion, "delay", lambda **kw: enqueued.append(kw))
    monkeypatch.setattr(tasks.process_conversion, "apply_async", lambda **kw: enqueued.append(kw))

    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_db] = lambda: db
    project = Project(user_id=ALICE, name="Cursos", name_key=projects_module.name_key("Cursos"))
    db.add(project)
    db.commit()
    yield SimpleNamespace(client=TestClient(app), db=db, Session=Session, minio=minio, enqueued=enqueued,
                          project=project, redis=fake_redis, es=es)
    db.close()


def jwt(user_id=ALICE):
    return {"Authorization": f"Bearer {create_access_token({'sub': user_id})}"}


PDF = _pdf_samples.text_and_image_pdf()
METADATA = {"pages": 1, "words": 3, "format": "pdf", "size_bytes": len(PDF), "title": "curso", "author": None}


def post(api, endpoint="/upload", content=PDF, **fields):
    data = {"project_id": api.project.id, **fields}
    if endpoint == "/convert":
        data["source_type"] = "file"
    return api.client.post(endpoint, headers=jwt(), data=data,
                           files={"file": ("curso.pdf", content, "application/pdf")})


@pytest.mark.parametrize("endpoint", ["/upload", "/convert"])
def test_upload_accepts_and_persists_the_image_options(api, endpoint):
    r = post(api, endpoint, image_mode="referenced", page_images="true")

    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    api.db.expire_all()
    assert api.db.get(JobConfiguration, job_id).options == {"image_mode": "referenced", "page_images": True}
    assert api.enqueued[-1]["options"]["image_mode"] == "referenced"
    assert api.enqueued[-1]["options"]["page_images"] is True


@pytest.mark.parametrize("endpoint", ["/upload", "/convert"])
def test_defaults_store_nothing(api, endpoint):
    r = post(api, endpoint)

    assert r.status_code == 200, r.text
    api.db.expire_all()
    assert api.db.get(JobConfiguration, r.json()["job_id"]) is None
    assert "image_mode" not in api.enqueued[-1]["options"]


def test_an_unknown_image_mode_is_422(api):
    assert post(api, image_mode="embedded").status_code == 422


def test_image_options_are_part_of_the_dedup_key(api):
    plain = post(api).json()
    referenced = post(api, image_mode="referenced").json()
    assert referenced["job_id"] != plain["job_id"] and referenced["duplicate"] is False
    assert post(api, image_mode="referenced").json()["job_id"] == referenced["job_id"]
    with_pages = post(api, image_mode="referenced", page_images="true").json()
    assert with_pages["job_id"] not in (plain["job_id"], referenced["job_id"])
    assert post(api).json()["job_id"] == plain["job_id"]

    from api.projects_api import conversion_operation_key
    assert conversion_operation_key("fast") == conversion_operation_key("fast", "none", False)
    assert conversion_operation_key("fast", "referenced") != conversion_operation_key("fast")


def test_a_job_recorded_before_operation_keys_never_answers_a_referenced_request(api):
    add_job(api.Session, image_mode="none", status=JobStatus.COMPLETED, project_id=api.project.id,
            checksum=hashlib.sha256(PDF).hexdigest(), operation_key=None)

    assert post(api).json()["job_id"] == JOB_ID  # as before
    assert post(api, image_mode="referenced").json()["job_id"] != JOB_ID


def test_a_referenced_duplicate_whose_assets_were_deleted_is_not_reused(api):
    from api.projects_api import conversion_operation_key
    add_job(api.Session, status=JobStatus.COMPLETED, project_id=api.project.id,
            checksum=hashlib.sha256(PDF).hexdigest(), operation_key=conversion_operation_key("fast", "referenced"))
    assert post(api, image_mode="referenced").json()["job_id"] == JOB_ID
    with api.Session() as db:
        db.get(Job, JOB_ID).assets_deleted_at = datetime.utcnow()
        db.commit()
    api.db.expire_all()
    assert post(api, image_mode="referenced").json()["job_id"] != JOB_ID


def completed_with_assets(api, *, purge=False, deleted=False):
    """A completed job whose worker stored two assets (bytes in the fake MinIO)."""
    add_job(api.Session, status=JobStatus.COMPLETED, purge=purge)
    storage = FakeMinio()
    collector = AssetCollector(JOB_ID, lambda: storage, settings=limits())
    markdown = extract_pictures(document([(1, gradient(120, 90, 1)), (1, gradient(60, 60, 2))]), collector)
    api.minio.objects.update(storage.objects)
    assets = collector.ordered()
    with api.Session() as db:
        job = db.get(Job, JOB_ID)
        job.assets_manifest = {"assets": assets, "skipped": collector.skipped}
        job.completed_at = datetime(2026, 10, 1, 9, 0, 0)
        if deleted:
            job.assets_deleted_at = datetime(2026, 10, 1, 10, 0, 0)
        db.commit()
    api.redis.set_job_status(job_id=JOB_ID, job_type="main", status="completed", progress=100)
    api.redis.set_job_result(JOB_ID, {"markdown": markdown, "metadata": METADATA})
    api.db.expire_all()
    return assets


def test_result_lists_the_assets_from_the_durable_manifest(api):
    assets = completed_with_assets(api)
    api.es.get_job_result.return_value = {"markdown_content": "x", "metadata": METADATA}  # ES keeps no assets

    body = api.client.get(f"/jobs/{JOB_ID}/result", headers=jwt()).json()["result"]

    assert [a["name"] for a in body["assets"]] == [a["name"] for a in assets]
    assert set(body["assets"][0]) == {"name", "kind", "page", "bbox", "sha256", "mime", "width", "height",
                                      "size_bytes", "url", "description", "ocr_text"}
    assert body["assets_skipped"] == {"too_small": 0, "count_limit": 0, "size_limit": 0, "unavailable": 0}


def test_result_of_a_job_without_assets_has_none(api):
    add_job(api.Session, image_mode="none", status=JobStatus.COMPLETED)
    api.redis.set_job_status(job_id=JOB_ID, job_type="main", status="completed", progress=100)
    api.redis.set_job_result(JOB_ID, {"markdown": "# x", "metadata": METADATA})

    body = api.client.get(f"/jobs/{JOB_ID}/result", headers=jwt()).json()["result"]
    assert body["assets"] is None and body["markdown"] == "# x"


def test_asset_endpoint_streams_the_png(api):
    asset = completed_with_assets(api)[0]

    r = api.client.get(asset["url"], headers=jwt())

    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.headers["etag"] == f'"{asset["sha256"]}"'
    assert r.headers["cache-control"].startswith("private")
    assert hashlib.sha256(r.content).hexdigest() == asset["sha256"]
    assert int(r.headers["content-length"]) == asset["size_bytes"]

    again = api.client.get(asset["url"], headers={**jwt(), "If-None-Match": f'"{asset["sha256"]}"'})
    assert again.status_code == 304 and again.content == b""


@pytest.mark.parametrize("name", [
    "p0001-img09-000000000000.png",        # well-formed, not in the manifest
    "..%2F..%2Fuploads%2Fx.png",           # traversal, encoded
    "curso.pdf",
    "p0001-img01-ABCDEF.png",
])
def test_asset_endpoint_serves_only_listed_names(api, name):
    completed_with_assets(api)
    api.minio.objects[(api.minio.bucket_results, f"assets/{JOB_ID}/{name}")] = b"never served"

    r = api.client.get(f"/jobs/{JOB_ID}/assets/{name}", headers=jwt())

    assert r.status_code == 404
    detail = r.json()["detail"]
    # an encoded "/" is decoded before routing: no route matches at all
    assert "/" in name.replace("%2F", "/") or detail["code"] == "ASSET_NOT_FOUND"


def test_asset_endpoint_path_traversal_never_reaches_storage(api):
    completed_with_assets(api)
    assert api.client.get(f"/jobs/{JOB_ID}/assets/../../uploads/{JOB_ID}/curso.pdf", headers=jwt()).status_code == 404


def test_asset_of_someone_elses_job_is_404(api):
    asset = completed_with_assets(api)[0]
    assert api.client.get(asset["url"], headers=jwt(BOB)).status_code == 404
    assert api.client.get(f"/jobs/{'0' * 8}-0000-4000-8000-000000000000/assets/{asset['name']}",
                          headers=jwt()).status_code == 404


def test_asset_endpoint_after_deletion_is_410_source_purged(api):
    asset = completed_with_assets(api, deleted=True)[0]

    r = api.client.get(asset["url"], headers=jwt())

    assert r.status_code == 410
    detail = r.json()["detail"]
    assert detail["code"] == "SOURCE_PURGED" and detail["cause"] == "ASSETS_PURGED"
    assert detail["assets_deleted_at"].startswith("2026-10-01T10:00:00")


def test_asset_storage_down_is_503(api):
    asset = completed_with_assets(api)[0]
    api.minio.fail = True
    r = api.client.get(asset["url"], headers=jwt())
    assert r.status_code == 503 and r.json()["detail"]["code"] == "ASSET_STORAGE_UNAVAILABLE"


def test_get_job_reports_assets_available_and_expiry(api):
    completed_with_assets(api)
    body = api.client.get(f"/jobs/{JOB_ID}", headers=jwt()).json()
    assert body["assets_available"] is True and body["assets_expire_at"] is None

    expire = datetime(2026, 10, 1, 10, 0, 0)
    with api.Session() as db:
        db.get(Job, JOB_ID).assets_expire_at = expire
        db.commit()
    api.db.expire_all()
    body = api.client.get(f"/jobs/{JOB_ID}", headers=jwt()).json()
    assert body["assets_expire_at"].startswith("2026-10-01T10:00:00")


def test_delete_source_also_deletes_the_assets(api):
    asset = completed_with_assets(api)[0]

    r = api.client.delete(f"/jobs/{JOB_ID}/source", headers=jwt())

    assert r.status_code == 200, r.text
    assert r.json()["source_deleted"] is True and r.json()["assets_deleted"] is True
    assert api.minio.assets() == []
    assert ("ingestify-uploads", f"uploads/{JOB_ID}/curso.pdf") in api.minio.deleted
    assert api.client.get(asset["url"], headers=jwt()).status_code == 410
    body = api.client.get(f"/jobs/{JOB_ID}", headers=jwt()).json()
    assert body["assets_available"] is False and body["source_available"] is False


def test_delete_source_removes_assets_kept_for_retention_after_the_purge(api):
    completed_with_assets(api, purge=True)
    with api.Session() as db:  # the worker purge already took the original
        job = db.get(Job, JOB_ID)
        job.minio_upload_path, job.source_deleted_at = None, datetime.utcnow()
        job.assets_expire_at = datetime.utcnow() + timedelta(hours=1)
        db.commit()
    api.db.expire_all()

    r = api.client.delete(f"/jobs/{JOB_ID}/source", headers=jwt())

    assert r.status_code == 200, r.text
    assert r.json()["source_deleted"] is False and r.json()["assets_deleted"] is True
    assert api.minio.assets() == []
    assert api.client.delete(f"/jobs/{JOB_ID}/source", headers=jwt()).status_code == 404


def test_delete_source_storage_failure_keeps_the_assets(api):
    completed_with_assets(api)
    api.minio.fail = True
    r = api.client.delete(f"/jobs/{JOB_ID}/source", headers=jwt())
    assert r.status_code == 503 and r.json()["detail"]["code"] == "SOURCE_DELETE_FAILED"
    api.db.expire_all()
    assert ca.assets_available(api.db.get(Job, JOB_ID))


def test_delete_job_removes_the_assets(api, monkeypatch):
    completed_with_assets(api)
    monkeypatch.setattr(routes, "get_es_client", lambda: MagicMock())

    assert api.client.delete(f"/jobs/{JOB_ID}", headers=jwt()).status_code == 200
    assert api.minio.assets() == []


def test_a_duplicate_purge_request_schedules_the_asset_expiry(api):
    from api.projects_api import conversion_operation_key
    completed_with_assets(api)
    with api.Session() as db:
        job = db.get(Job, JOB_ID)
        job.file_checksum, job.project_id = hashlib.sha256(PDF).hexdigest(), api.project.id
        job.operation_key = conversion_operation_key("fast", "referenced")
        db.commit()
    api.db.expire_all()

    body = post(api, image_mode="referenced", purge_source="true").json()

    assert body["job_id"] == JOB_ID and body["duplicate"] is True
    api.db.expire_all()
    job = api.db.get(Job, JOB_ID)
    assert job.minio_upload_path is None and job.assets_expire_at is not None
    assert api.minio.assets()  # still downloadable until the retention ends


# ---------------------------------------------------------------------------
# Real docling (opt-in: needs docling's layout models, e.g. the worker image with
# the HF cache volume; skipped otherwise)
# ---------------------------------------------------------------------------

def _docling_models_available() -> bool:
    if os.environ.get("INGESTIFY_REAL_DOCLING") == "0":
        return False
    try:
        import docling  # noqa: F401
    except ImportError:
        return False
    if os.environ.get("DOCLING_ARTIFACTS_PATH"):
        return True
    home = Path(os.environ.get("HF_HOME") or Path.home() / ".cache" / "huggingface")
    hub = Path(os.environ.get("HF_HUB_CACHE") or home / "hub")
    return any(hub.glob("models--docling-project--docling-layout-*")) or any(
        hub.glob("models--ds4sd--docling-models"))


@pytest.mark.skipif(not _docling_models_available(), reason="docling models not available (opt-in test)")
def test_real_docling_extracts_pictures_and_renders_pages(tmp_path, monkeypatch):
    monkeypatch.setenv("DEVICE", os.environ.get("DEVICE", "cpu"))
    get_settings.cache_clear()
    try:
        source = tmp_path / "curso.pdf"
        source.write_bytes(_pdf_samples.course_pdf())
        converter = DoclingConverter(enable_ocr=False, enable_table_structure=True, enable_images=True)
        assert converter.converter is not None
        storage = FakeMinio()

        result = converter.convert_to_markdown(
            source, {"image_mode": "referenced", "page_images": True},
            assets=AssetCollector(JOB_ID, lambda: storage, settings=limits(conversion_page_image_dpi=100)))
    finally:
        get_settings.cache_clear()

    pictures = [a for a in result["assets"] if a["kind"] == "picture"]
    pages = [a for a in result["assets"] if a["kind"] == "page"]
    assert [a["page"] for a in pages] == [1, 2, 3]
    assert pictures and pictures[0]["page"] == 1  # the raster image embedded on page 1
    assert f"![Image]({pictures[0]['url']})" in result["markdown"]
    assert "data:image" not in result["markdown"]
    assert "Curso de exemplo" in result["markdown"]
    for asset in result["assets"]:
        data = storage.objects[(storage.bucket_results, ca.object_name(JOB_ID, asset["name"]))]
        assert hashlib.sha256(data).hexdigest() == asset["sha256"]



# ---------------------------------------------------------------------------
# Review fixes
# ---------------------------------------------------------------------------

def test_image_mode_none_never_changes_the_picture_scale(monkeypatch):
    """balanced/quality and DOCLING_ENABLE_IMAGES keep docling's own images_scale."""
    pytest.importorskip("docling")
    from docling.document_converter import InputFormat
    from workers import converter as converter_module

    def scale(converter):
        return converter.converter.format_to_options[InputFormat.PDF].pipeline_options

    monkeypatch.setenv("DEVICE", "cpu")
    get_settings.cache_clear()
    try:
        plain = DoclingConverter(enable_ocr=False, enable_table_structure=True, enable_images=True)
        referenced = DoclingConverter(enable_ocr=False, enable_table_structure=True, enable_images=False,
                                      picture_images=True)
    finally:
        get_settings.cache_clear()
    default_scale = type(scale(plain))().images_scale
    assert scale(plain).generate_picture_images is True and scale(plain).images_scale == default_scale
    assert scale(referenced).generate_picture_images is True
    assert scale(referenced).images_scale == get_settings().conversion_images_scale

    built = []
    monkeypatch.setattr(converter_module, "DoclingConverter", lambda **kw: built.append(kw) or kw)
    converter_module._cached_converter.cache_clear()
    try:
        assert converter_module.get_converter("balanced") == {
            "enable_ocr": False, "enable_table_structure": True, "enable_images": True}
        assert converter_module.get_converter("balanced", picture_images=True)["picture_images"] is True
        assert len(built) == 2  # its own cache slot
    finally:
        converter_module._cached_converter.cache_clear()


def test_limits_are_checked_before_encoding_and_rendering(tmp_path, monkeypatch):
    from workers import image_assets
    encoded = []
    real = image_assets.encode_png
    monkeypatch.setattr(image_assets, "encode_png", lambda image: encoded.append(1) or real(image))

    collector = AssetCollector(JOB_ID, lambda: FakeMinio(), settings=limits(conversion_asset_max_count=1))
    extract_pictures(document([(1, gradient(40, 40, n)) for n in range(1, 4)]), collector)
    assert len(encoded) == 1 and collector.skipped["count_limit"] == 2

    import pypdfium2
    rendered = []
    real_render = pypdfium2.PdfPage.render
    monkeypatch.setattr(pypdfium2.PdfPage, "render", lambda self, **kw: rendered.append(1) or real_render(self, **kw))
    source = tmp_path / "curso.pdf"
    source.write_bytes(_pdf_samples.course_pdf())
    pages = AssetCollector(JOB_ID, lambda: FakeMinio(), settings=limits(conversion_asset_max_count=1))
    assert render_pages(source, pages) == 1
    assert len(rendered) == 1 and pages.skipped["count_limit"] == 2


def test_split_pages_share_the_job_budget_before_uploading(worker, monkeypatch):
    monkeypatch.setattr(tasks.settings, "conversion_asset_max_count", 2)
    add_job(worker.Session, image_mode="none", page_images=True, pages=[1, 2, 3], status=JobStatus.PROCESSING)
    files = split_pages(worker, 3)
    worker.state.make_document = lambda path: document([])

    run_pages(worker, files)

    assert len(worker.minio.assets()) == 2  # page 3 was never rendered nor uploaded
    assert worker.redis.get_job_result("page-3")["assets_skipped"]["count_limit"] == 1
    run_pages(worker, files, order=[1])  # a retry of a page reuses its reservation
    assert worker.redis.get_job_result("page-1")["assets"]
    tasks.merge_pages_task.run(**worker.state.merges[0])
    assert [a["page"] for a in worker.job().assets_manifest["assets"]] == [1, 2]


def test_without_redis_the_budget_falls_back_to_per_page_limits_and_the_merge(worker, monkeypatch):
    monkeypatch.setattr(tasks.settings, "conversion_asset_max_count", 2)
    add_job(worker.Session, image_mode="none", page_images=True, pages=[1, 2, 3], status=JobStatus.PROCESSING)
    files = split_pages(worker, 3)
    worker.state.make_document = lambda path: document([])

    class DownRedis:
        client = property(lambda self: self)

        def __getattr__(self, name):
            raise ConnectionError("redis down")
    real = ca.JobAssetBudget.__init__
    monkeypatch.setattr(ca.JobAssetBudget, "__init__",
                        lambda self, client, job_id, **kw: real(self, DownRedis(), job_id, **kw))

    run_pages(worker, files)
    assert len(worker.minio.assets()) == 3
    tasks.merge_pages_task.run(**worker.state.merges[0])
    assert [a["page"] for a in worker.job().assets_manifest["assets"]] == [1, 2]
    assert len(worker.minio.assets()) == 2  # the merge trimmed and deleted the third


def test_a_partial_job_lists_the_assets_of_its_completed_pages(worker, monkeypatch):
    add_job(worker.Session, image_mode="referenced", pages=[1, 2], status=JobStatus.PROCESSING)
    files = split_pages(worker, 2)
    monkeypatch.setattr("shared.redis_client.get_redis_client", lambda: worker.redis)
    run_pages(worker, files, order=[1])
    with worker.Session() as db:  # page 2 failed for good: the job settles PARTIAL
        page = db.query(Page).filter(Page.job_id == JOB_ID, Page.page_number == 2).one()
        page.status = JobStatus.FAILED
        db.get(Job, JOB_ID).status = JobStatus.PARTIAL
        db.commit()

    tasks._purge_source_if_requested(JOB_ID)

    job = worker.job()
    assert [a["page"] for a in job.assets_manifest["assets"]] == [1]
    assert job.minio_upload_path is not None  # no purge_source: the source stays
    assert ca.assets_available(job)


def test_a_failed_job_without_a_manifest_deletes_its_assets(worker, monkeypatch):
    add_job(worker.Session, image_mode="referenced", status=JobStatus.FAILED)
    worker.minio.objects[(worker.minio.bucket_results, ca.object_name(JOB_ID, "p0001-img01-0123456789ab.png"))] = b"x"
    monkeypatch.setattr("shared.redis_client.get_redis_client", lambda: worker.redis)

    tasks._purge_source_if_requested(JOB_ID)

    assert worker.minio.assets() == [] and worker.job().assets_manifest is None


def _fail_manifest_writes(Session):
    from sqlalchemy import event

    def before_flush(session, *_):
        for obj in session.dirty:
            if isinstance(obj, Job) and session.is_modified(obj) and \
                    "assets_manifest" in {a.key for a in Job.__mapper__.attrs if
                                          getattr(__import__("sqlalchemy").inspect(obj).attrs, a.key).history.has_changes()}:
                raise RuntimeError("database refused")
    event.listen(Session, "before_flush", before_flush)


def test_a_manifest_that_cannot_be_stored_publishes_no_urls(worker):
    add_job(worker.Session, image_mode="referenced")
    _fail_manifest_writes(worker.Session)

    assert worker.convert()["status"] == "completed"

    result = worker.redis.get_job_result(JOB_ID)
    assert "/assets/" not in result["markdown"] and "<!-- image -->" in result["markdown"]
    assert "assets" not in result
    assert worker.minio.assets() == [] and worker.job().assets_manifest is None


def test_the_merge_writes_the_manifest_even_when_the_options_cannot_be_read(worker, monkeypatch):
    add_job(worker.Session, image_mode="referenced", pages=[1, 2], status=JobStatus.PROCESSING)
    files = split_pages(worker, 2)
    run_pages(worker, files)
    monkeypatch.setattr(ca, "durable_options", lambda *a, **kw: {})

    tasks.merge_pages_task.run(**worker.state.merges[0])

    assert [a["page"] for a in worker.job().assets_manifest["assets"]] == [1, 2]


def test_delete_source_records_the_assets_even_when_the_source_delete_fails(api):
    asset = completed_with_assets(api)[0]
    api.minio.fail_buckets = {api.minio.bucket_uploads}

    r = api.client.delete(f"/jobs/{JOB_ID}/source", headers=jwt())

    assert r.status_code == 503
    assert api.client.get(asset["url"], headers=jwt()).status_code == 410  # not 404
    api.minio.fail_buckets = set()
    again = api.client.delete(f"/jobs/{JOB_ID}/source", headers=jwt())
    assert again.status_code == 200 and again.json()["source_deleted"] is True
    assert again.json()["assets_deleted"] is False


PAGE_JOB = "bbbbbbbb-1111-4222-8333-444444444444"


def test_a_page_job_result_publishes_only_the_asset_fields(api, monkeypatch):
    monkeypatch.setattr("shared.redis_client.get_redis_client", lambda: api.redis)
    assets = completed_with_assets(api)
    api.redis.set_job_status(job_id=PAGE_JOB, job_type="page", status="completed", parent_job_id=JOB_ID,
                             page_number=1)
    api.redis.set_job_result(PAGE_JOB, {"markdown": "x", "metadata": METADATA,
                                        "assets": [{**assets[0], "position": 1, "internal": "y"}]})

    r = api.client.get(f"/jobs/{PAGE_JOB}/result", headers=jwt())

    assert r.status_code == 200, r.text
    assert set(r.json()["result"]["assets"][0]) == set(ca.PUBLIC_FIELDS + ca.FIGURE_FIELDS)


@pytest.mark.parametrize("remaining, reused", [(timedelta(minutes=10), False), (timedelta(minutes=50), True)])
def test_dedup_skips_jobs_whose_assets_expire_soon(api, remaining, reused):
    from api.projects_api import conversion_operation_key
    completed_with_assets(api)
    with api.Session() as db:
        job = db.get(Job, JOB_ID)
        job.file_checksum, job.project_id = hashlib.sha256(PDF).hexdigest(), api.project.id
        job.operation_key = conversion_operation_key("fast", "referenced")
        job.assets_expire_at = datetime.utcnow() + remaining
        db.commit()
    api.db.expire_all()

    body = post(api, image_mode="referenced", purge_source="true").json()

    assert (body["job_id"] == JOB_ID) is reused


def test_the_expiry_runs_once_per_interval_across_processes(worker, fake_redis, monkeypatch):
    from workers import image_full_tasks
    monkeypatch.setattr("shared.redis_client.get_redis_client", lambda: fake_redis)
    calls = []
    monkeypatch.setattr(ca, "expire_due_assets", lambda *a, **kw: calls.append(1) or 0)

    image_full_tasks.expire_conversion_assets()
    image_full_tasks.expire_conversion_assets()  # another process, same minute: skipped

    assert len(calls) == 1
