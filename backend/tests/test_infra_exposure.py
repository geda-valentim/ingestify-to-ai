"""Infrastructure services must not be published on all interfaces; Redis password is optional."""
from pathlib import Path

import pytest

from shared.config import redis_url_with_password

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[2]
INFRA_SERVICES = {"redis", "elasticsearch", "minio"}


@pytest.mark.parametrize("compose_file", ["docker-compose.yml", "docker-compose.infra.yml"])
def test_infra_ports_are_bound_to_localhost(compose_file):
    services = yaml.safe_load((ROOT / compose_file).read_text())["services"]
    checked = 0
    for name, service in services.items():
        if name not in INFRA_SERVICES:
            continue
        for port in service.get("ports", []):
            assert str(port).startswith("127.0.0.1:"), f"{compose_file}: {name} publishes {port} on all interfaces"
            checked += 1
    assert checked >= 4  # redis, elasticsearch, minio api + console


@pytest.mark.parametrize(
    "url, password, expected",
    [
        ("redis://redis:6379/0", "", "redis://redis:6379/0"),
        ("redis://redis:6379/0", "s3cret", "redis://:s3cret@redis:6379/0"),
        ("redis://redis:6379/1", "p@ss/w:rd", "redis://:p%40ss%2Fw%3Ard@redis:6379/1"),
        ("rediss://cache:6380/0", "x", "rediss://:x@cache:6380/0"),
        ("redis://:other@redis:6379/0", "s3cret", "redis://:other@redis:6379/0"),  # explicit creds win
        ("amqp://rabbit//", "s3cret", "amqp://rabbit//"),
    ],
)
def test_redis_url_with_password(url, password, expected):
    assert redis_url_with_password(url, password) == expected
