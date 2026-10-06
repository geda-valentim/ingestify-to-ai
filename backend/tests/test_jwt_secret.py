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


def test_legacy_hs256_tokens_remain_compatible(monkeypatch):
    """Decode the standard HS256 wire format independently of either JWT library."""
    import base64
    import hashlib
    import hmac
    import json
    import time
    from shared import auth
    key = "unit-legacy-key-with-more-than-thirty-two-characters"
    monkeypatch.setattr(auth.settings, "jwt_secret_key", key)
    monkeypatch.setattr(auth.settings, "jwt_algorithm", "HS256")
    def encode(value):
        return base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).rstrip(b"=")
    signing = encode({"alg": "HS256", "typ": "JWT"}) + b"." + encode({"sub": "legacy-user", "exp": int(time.time()) + 60})
    signature = base64.urlsafe_b64encode(hmac.new(key.encode(), signing, hashlib.sha256).digest()).rstrip(b"=")
    assert auth.verify_token((signing + b"." + signature).decode()) == "legacy-user"


def test_invalid_subject_and_unsigned_tokens_are_rejected(monkeypatch):
    import jwt
    from shared import auth
    key = "unit-token-key-with-more-than-thirty-two-characters"
    monkeypatch.setattr(auth.settings, "jwt_secret_key", key)
    for subject in (123, None, ["user"]):
        assert auth.verify_token(jwt.encode({"sub": subject}, key, algorithm="HS256")) is None
    assert auth.verify_token(jwt.encode({"sub": "user"}, key="", algorithm="none")) is None
