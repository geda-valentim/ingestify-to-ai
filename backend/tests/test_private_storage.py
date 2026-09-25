"""Stored documents are private: no bucket may be anonymously readable.

The page-PDF endpoint's ownership check is covered by test_page_pdf_endpoint.py.
"""
import pytest
from minio.error import S3Error

from shared.minio_client import MinIOClient


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
