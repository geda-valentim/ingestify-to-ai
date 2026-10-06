"""Production infrastructure fails closed before any service connection."""
import pytest
from pydantic import ValidationError
from shared.config import Settings


def production(**overrides):
    config = dict(
        _env_file=None, environment="production",
        jwt_secret_key="unit-test-only-secret-with-more-than-32-chars",
        minio_access_key="unit-access", minio_secret_key="unit-secret",
        redis_password="unit-redis-secret", redis_ssl=True,
        celery_broker_url="rediss://redis:6379/0",
        celery_result_backend="rediss://redis:6379/1",
        elasticsearch_url="https://elasticsearch:9200",
        elasticsearch_user="unit-user", elasticsearch_password="unit-password",
        elasticsearch_verify_certs=True, minio_secure=True,
        database_url="mysql+pymysql://app:unit-secret@db/ingestify",
    )
    config.update(overrides)
    return Settings(**config)


@pytest.mark.parametrize("override", [
    {"audio_transcriber_provider": "whisperx"}, {"live_diarization_enabled": True},
    {"redis_password": ""}, {"redis_ssl": False},
    {"celery_broker_url": "redis://redis/0"},
    {"celery_result_backend": "rediss://redis/1?ssl_cert_reqs=none"},
    {"celery_broker_url": "rediss://redis/0?ssl_check_hostname=false"},
    {"celery_broker_url": "rediss://redis/0?ssl_check_hostname=true&ssl_check_hostname=false"},
    {"celery_result_backend": "rediss://redis/1?ssl_cert_reqs=required&ssl_cert_reqs=none"},
    {"database_url": "mysql+pymysql://%72oot:unit-secret@db/ingestify"},
    {"database_url": "mysql+pymysql://app:%70assword@db/ingestify"},
    {"elasticsearch_url": "http://elasticsearch:9200"},
    {"elasticsearch_user": ""}, {"elasticsearch_password": ""},
    {"elasticsearch_verify_certs": False}, {"minio_secure": False},
    {"database_url": "mysql+pymysql://root:root@db/ingestify"},
])
def test_production_rejects_insecure_infrastructure(override):
    with pytest.raises(ValidationError):
        production(**override)


def test_production_accepts_authenticated_verified_tls():
    assert production().redis_ssl


def test_development_allows_local_plaintext_infrastructure():
    assert production(environment="development", redis_ssl=False,
                      redis_password="", minio_secure=False).environment == "development"
