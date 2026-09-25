"""JWT secret validation: the API must never sign or accept tokens with a weak or known secret."""
import pytest

from shared import auth

STRONG_SECRET = "a" * 64


@pytest.fixture
def jwt_secret(monkeypatch):
    def set_secret(value):
        monkeypatch.setattr(auth.settings, "jwt_secret_key", value)
    return set_secret


@pytest.mark.parametrize(
    "secret",
    ["", "your-secret-key-change-in-production-min-32-chars", "x" * 31],
    ids=["missing", "known-placeholder", "too-short"],
)
def test_rejects_insecure_secrets(secret):
    with pytest.raises(RuntimeError):
        auth.validate_jwt_secret(secret)


def test_accepts_strong_secret():
    auth.validate_jwt_secret(STRONG_SECRET)


def test_token_creation_blocked_without_secret(jwt_secret):
    jwt_secret("")
    with pytest.raises(RuntimeError):
        auth.create_access_token({"sub": "user-1"})


def test_token_round_trip(jwt_secret):
    jwt_secret(STRONG_SECRET)
    token = auth.create_access_token({"sub": "user-1"})
    assert auth.verify_token(token) == "user-1"


def test_token_signed_with_other_secret_is_rejected(jwt_secret):
    jwt_secret("b" * 64)
    token = auth.create_access_token({"sub": "user-1"})
    jwt_secret(STRONG_SECRET)
    assert auth.verify_token(token) is None
