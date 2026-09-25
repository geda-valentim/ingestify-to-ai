"""Stored documents are private: page PDFs go through the API with an ownership check."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from minio.error import S3Error

import workers.celery_app  # noqa: F401  (import order used by the worker; avoids a circular import)
from api import routes
from shared.minio_client import MinIOClient

OWNER = SimpleNamespace(id="owner-1")
OTHER = SimpleNamespace(id="other-2")
JOB_ID = "job-1"
PDF = b"%PDF-1.4 page"


class FakeQuery:
    def __init__(self, result):
        self.result = result

    def filter(self, *args):
        return self

    def first(self):
        return self.result


class FakeDB:
    def __init__(self, job, page):
        self.results = {routes.Job: job, routes.Page: page}

    def query(self, model):
        return FakeQuery(self.results[model])


class FakeObject:
    def __init__(self, data):
        self.data, self.closed, self.released = data, False, False

    def stream(self, chunk_size):
        for i in range(0, len(self.data), chunk_size):
            yield self.data[i:i + chunk_size]

    def close(self):
        self.closed = True

    def release_conn(self):
        self.released = True


class FakeMinio:
    bucket_pages = "ingestify-pages"

    def __init__(self, objects):
        self.objects = objects
        self.opened = []

    def open_object(self, bucket_name, object_name):
        if object_name not in self.objects:
            raise FileNotFoundError(object_name)
        obj = FakeObject(self.objects[object_name])
        self.opened.append(obj)
        return obj


async def read_body(response):
    return b"".join([chunk async for chunk in response.body_iterator])


@pytest.fixture
def storage(monkeypatch):
    def setup(objects):
        fake = FakeMinio(objects)
        monkeypatch.setattr(routes, "get_minio_client", lambda: fake)
        return fake
    return setup


def get_pdf(user, job, page, page_number=1):
    db = FakeDB(job, page)
    return asyncio.run(routes.get_page_pdf(JOB_ID, page_number, current_user=user, db=db))


JOB = SimpleNamespace(id=JOB_ID, user_id=OWNER.id)
PAGE = SimpleNamespace(minio_page_path=f"pages/{JOB_ID}/page_0001.pdf")


def test_owner_gets_the_pdf_streamed_from_the_api(storage):
    big = PDF * 20000  # several chunks
    fake = storage({PAGE.minio_page_path: big})
    response = get_pdf(OWNER, JOB, PAGE)
    assert asyncio.run(read_body(response)) == big
    assert fake.opened[0].closed and fake.opened[0].released  # connection returned to the pool
    assert response.media_type == "application/pdf"
    assert "no-store" in response.headers["cache-control"]


def test_other_user_gets_404(storage):
    storage({PAGE.minio_page_path: PDF})
    with pytest.raises(HTTPException) as exc:
        get_pdf(OTHER, JOB, PAGE)
    assert exc.value.status_code == 404


@pytest.mark.parametrize("job, page", [(None, PAGE), (JOB, None)])
def test_missing_job_or_page_gets_404(storage, job, page):
    storage({PAGE.minio_page_path: PDF})
    with pytest.raises(HTTPException) as exc:
        get_pdf(OWNER, job, page)
    assert exc.value.status_code == 404


def test_missing_file_gets_404(storage):
    storage({})
    with pytest.raises(HTTPException) as exc:
        get_pdf(OWNER, JOB, PAGE)
    assert exc.value.status_code == 404


def s3_error(code, bucket):
    # Keyword arguments: the positional order differs between minio versions
    return S3Error(code=code, message=code, resource=bucket, request_id="req", host_id="host", response=None)


class FakeS3:
    """Minimal MinIO SDK stand-in: buckets exist, some have a public policy"""

    def __init__(self, policies):
        self.policies = dict(policies)
        self.deleted = []

    def bucket_exists(self, name):
        return True

    def get_bucket_policy(self, name):
        if name not in self.policies:
            raise s3_error("NoSuchBucketPolicy", name)
        return self.policies[name]

    def delete_bucket_policy(self, name):
        self.deleted.append(name)
        del self.policies[name]

    def set_bucket_policy(self, name, policy):
        raise AssertionError("buckets must never be made public")


@pytest.mark.parametrize("fail_on", ["get_bucket_policy", "delete_bucket_policy"])
def test_client_fails_closed_when_buckets_cannot_be_made_private(fail_on):
    public = '{"Statement":[{"Principal":{"AWS":["*"]}}]}'
    fake = FakeS3({"ingestify-uploads": public})

    def denied(name):
        raise s3_error("AccessDenied", name)
    setattr(fake, fail_on, denied)

    with pytest.raises(RuntimeError):
        MinIOClient(client=fake)


def test_public_policies_are_removed_from_existing_buckets():
    public = '{"Statement":[{"Effect":"Allow","Principal":{"AWS":["*"]},"Action":["s3:GetObject"]}]}'
    fake = FakeS3({"ingestify-uploads": public, "ingestify-pages": public, "ingestify-results": public})

    MinIOClient(client=fake)

    assert sorted(fake.deleted) == ["ingestify-pages", "ingestify-results", "ingestify-uploads"]
    assert fake.policies == {}
