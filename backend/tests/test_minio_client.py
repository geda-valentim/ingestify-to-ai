"""
Tests for the two MinIO behaviours the page-PDF fix depends on.

1. Buckets must not be anonymously readable. Every client init used to apply an
   `s3:GetObject` policy for `Principal: *` to uploads/pages/results, which made
   the original documents, the page PDFs and the converted markdown world
   readable at predictable paths. Deleting that code is not enough - a MinIO
   that already received the policy keeps it - so the client now actively
   deletes the policy on init, idempotently and without ever breaking startup.

2. Presigned URLs must be signed for the endpoint the BROWSER will use. The
   SigV4 signature covers the Host header: a URL signed for `minio:9000` and
   fetched at `192.168.1.10:9000` fails verification, and every PDF 403s.

Everything runs against a fake Minio SDK client - no live MinIO.
"""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from minio.error import S3Error

import shared.minio_client as minio_module
from shared.minio_client import MinIOClient


def _settings(**overrides):
    values = {
        "minio_endpoint": "minio:9000",
        "minio_public_endpoint": "127.0.0.1:9000",
        "minio_access_key": "key",
        "minio_secret_key": "secret",
        "minio_secure": False,
        "minio_ca_certs": "",
        "minio_bucket_uploads": "ingestify-uploads",
        "minio_bucket_pages": "ingestify-pages",
        "minio_bucket_audio": "ingestify-audio",
        "minio_bucket_crawled": "ingestify-crawled",
        "minio_bucket_results": "ingestify-results",
        "model_fields_set": set(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _s3_error(code):
    return S3Error(
        response=SimpleNamespace(status=404, headers={}),
        code=code,
        message=code,
        resource="/bucket",
        request_id="req",
        host_id="host",
    )


class FakeSDKClient:
    """Minimal stand-in for minio.Minio."""

    def __init__(self, delete_policy_error=None):
        self.deleted_policies = []
        self.set_policies = []
        self.presigned = []
        self._delete_policy_error = delete_policy_error

    def bucket_exists(self, bucket_name):
        return True

    def make_bucket(self, bucket_name):  # pragma: no cover - buckets exist here
        raise AssertionError("should not be called")

    def get_bucket_policy(self, bucket_name):
        raise _s3_error("NoSuchBucketPolicy")

    def delete_bucket_policy(self, bucket_name):
        self.deleted_policies.append(bucket_name)
        if self._delete_policy_error is not None:
            raise self._delete_policy_error

    def set_bucket_policy(self, bucket_name, policy):  # pragma: no cover
        self.set_policies.append((bucket_name, policy))

    def _get_region(self, bucket_name=None):
        return "us-east-1"

    def presigned_get_object(self, bucket_name, object_name, expires=None):
        self.presigned.append((bucket_name, object_name, expires))
        return f"http://minio:9000/{bucket_name}/{object_name}?X-Amz-Signature=x"


@pytest.fixture
def settings(monkeypatch):
    """Settings are lru_cached globally; swap the accessor instead."""
    current = _settings()
    monkeypatch.setattr(minio_module, "get_settings", lambda: current)
    return current


class TestBrowserEndpoint:
    def test_configured_public_endpoint_wins(self, monkeypatch):
        """Explicit config beats the request host: behind a proxy or on TLS it
        is the only value that can be right."""
        configured = _settings(
            minio_public_endpoint="storage.example.com",
            model_fields_set={"minio_public_endpoint"},
        )
        monkeypatch.setattr(minio_module, "get_settings", lambda: configured)
        client = MinIOClient(client=FakeSDKClient())

        assert client.browser_endpoint("192.168.1.10:8000") == "storage.example.com"

    def test_empty_configured_value_is_ignored(self, monkeypatch):
        """docker-compose passes `MINIO_PUBLIC_ENDPOINT=${...:-}`; an empty
        string must not become the endpoint."""
        configured = _settings(
            minio_public_endpoint="",
            model_fields_set={"minio_public_endpoint"},
        )
        monkeypatch.setattr(minio_module, "get_settings", lambda: configured)
        client = MinIOClient(client=FakeSDKClient())

        assert client.browser_endpoint("192.168.1.10:8000") == "192.168.1.10:9000"

    def test_falls_back_to_request_host(self, settings):
        """Reaching the app by LAN IP must keep working without configuration."""
        client = MinIOClient(client=FakeSDKClient())

        assert client.browser_endpoint("192.168.1.10:8000") == "192.168.1.10:9000"

    def test_falls_back_to_the_default_without_a_host(self, settings):
        client = MinIOClient(client=FakeSDKClient())

        assert client.browser_endpoint(None) == "127.0.0.1:9000"


class TestPresignedUrlHost:
    def test_url_is_signed_for_the_browser_host_not_the_internal_one(
        self, settings, monkeypatch
    ):
        """The regression that would silently 403 every PDF."""
        built = {}

        class SigningClient(FakeSDKClient):
            def presigned_get_object(self, bucket_name, object_name, expires=None):
                return f"http://{built['endpoint']}/{bucket_name}/{object_name}?X-Amz-Signature=x"

        def fake_minio(endpoint, access_key, secret_key, secure, region):
            built["endpoint"] = endpoint
            built["region"] = region
            return SigningClient()

        monkeypatch.setattr(minio_module, "Minio", fake_minio)
        client = MinIOClient(client=FakeSDKClient())

        url = client.get_presigned_url(
            "ingestify-pages",
            "pages/job-1/page_0001.pdf",
            expires=timedelta(minutes=15),
            request_host="192.168.1.10:8000",
        )

        assert built["endpoint"] == "192.168.1.10:9000"
        assert url.startswith("http://192.168.1.10:9000/")

    def test_region_is_pinned_so_signing_needs_no_network(self, settings, monkeypatch):
        """Without an explicit region the SDK would call GetBucketLocation on the
        browser-facing endpoint, which the API server may not be able to reach."""
        built = {}

        def fake_minio(endpoint, access_key, secret_key, secure, region):
            built["region"] = region
            return FakeSDKClient()

        monkeypatch.setattr(minio_module, "Minio", fake_minio)
        client = MinIOClient(client=FakeSDKClient())
        client.get_presigned_url("ingestify-pages", "x.pdf", request_host="other-host:8000")

        assert built["region"] == "us-east-1"

    def test_same_endpoint_reuses_the_primary_client(self, settings, monkeypatch):
        """run_api.sh runs with internal == browser endpoint: no second client."""
        monkeypatch.setattr(
            minio_module,
            "Minio",
            lambda **kw: pytest.fail("must not create a second client"),
        )
        sdk = FakeSDKClient()
        client = MinIOClient(client=sdk)

        client.get_presigned_url(
            "ingestify-pages",
            "pages/job-1/page_0001.pdf",
            expires=timedelta(minutes=15),
            request_host="minio:9000",
        )

        assert sdk.presigned == [
            ("ingestify-pages", "pages/job-1/page_0001.pdf", timedelta(minutes=15))
        ]

    def test_signing_clients_are_cached_per_endpoint(self, settings, monkeypatch):
        created = []

        def fake_minio(endpoint, access_key, secret_key, secure, region):
            created.append(endpoint)
            return FakeSDKClient()

        monkeypatch.setattr(minio_module, "Minio", fake_minio)
        client = MinIOClient(client=FakeSDKClient())

        for _ in range(3):
            client.get_presigned_url("ingestify-pages", "x.pdf", request_host="10.0.0.5:8000")

        assert created == ["10.0.0.5:9000"]
