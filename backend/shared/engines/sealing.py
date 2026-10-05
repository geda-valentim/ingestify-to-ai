"""
Engine credentials sealed to a public key: whoever only has the public key
(the API, the import CLI) can seal, never open. Only worker-remote holds the
private keys, so a compromise of the API - the process that parses uploads -
does not reveal any provider token.

Construction (libsodium's sealed box, built on `cryptography`, already a
dependency): a fresh X25519 key per seal, HKDF-SHA256 over the shared secret and
both public keys, ChaCha20-Poly1305. The engine id and the key id are bound as
associated data, so a sealed blob copied onto another engine's row fails to open.

Blob layout: b"ING1" | ephemeral public key (32) | nonce (12) | ciphertext+tag.
Keys travel as unpadded-or-padded base64 of the raw 32 bytes.
"""

import base64
import hashlib
import json
import os
from typing import Dict, Iterable, Tuple

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

MAGIC = b"ING1"
_RAW = serialization.Encoding.Raw
_RAW_PUBLIC = serialization.PublicFormat.Raw


class SealingError(Exception):
    """A key is missing or malformed, or a blob does not open with any key"""


def _b64decode(value: str) -> bytes:
    value = value.strip()
    return base64.b64decode(value + "=" * (-len(value) % 4))


def _public_raw(public_key: X25519PublicKey) -> bytes:
    return public_key.public_bytes(_RAW, _RAW_PUBLIC)


def key_id(public_key_b64: str) -> str:
    """Short, non-secret id of a key pair (from its public key), stored next to each blob"""
    return hashlib.sha256(_b64decode(public_key_b64)).hexdigest()[:16]


def generate_keypair() -> Tuple[str, str]:
    """(public_key_b64, private_key_b64) for ENGINE_SECRETS_PUBLIC_KEY / _PRIVATE_KEYS"""
    private = X25519PrivateKey.generate()
    private_raw = private.private_bytes(_RAW, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    return (
        base64.b64encode(_public_raw(private.public_key())).decode(),
        base64.b64encode(private_raw).decode(),
    )


def _key(shared: bytes, ephemeral_public: bytes, recipient_public: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None,
        info=b"ingestify-engine-credentials" + ephemeral_public + recipient_public,
    ).derive(shared)


def _aad(engine_id: str, kid: str) -> bytes:
    return f"{engine_id}|{kid}".encode()


def seal(credentials: Dict[str, str], public_key_b64: str, engine_id: str) -> Tuple[bytes, str]:
    """Seal a credentials dict for one engine. Returns (blob, key_id)"""
    if not public_key_b64:
        raise SealingError("ENGINE_SECRETS_PUBLIC_KEY is not set: credentials cannot be stored")
    try:
        recipient = X25519PublicKey.from_public_bytes(_b64decode(public_key_b64))
    except Exception as e:
        raise SealingError(f"ENGINE_SECRETS_PUBLIC_KEY is not a valid X25519 public key: {e}") from None

    ephemeral = X25519PrivateKey.generate()
    ephemeral_public = _public_raw(ephemeral.public_key())
    recipient_public = _public_raw(recipient)
    kid = key_id(public_key_b64)
    nonce = os.urandom(12)
    plaintext = json.dumps(credentials, separators=(",", ":"), sort_keys=True).encode()
    ciphertext = ChaCha20Poly1305(_key(ephemeral.exchange(recipient), ephemeral_public, recipient_public)).encrypt(
        nonce, plaintext, _aad(engine_id, kid)
    )
    return MAGIC + ephemeral_public + nonce + ciphertext, kid


def open_sealed(blob: bytes, private_keys_b64: Iterable[str], engine_id: str, kid: str) -> Dict[str, str]:
    """
    Open a blob sealed for `engine_id` with the private key whose public half has
    id `kid` (several keys may be configured during a rotation).
    """
    if not blob or not blob.startswith(MAGIC) or len(blob) < len(MAGIC) + 32 + 12 + 16:
        raise SealingError("Not a sealed credentials blob")
    ephemeral_public = blob[4:36]
    nonce = blob[36:48]
    ciphertext = blob[48:]

    for private_b64 in private_keys_b64:
        if not private_b64 or not private_b64.strip():
            continue
        try:
            private = X25519PrivateKey.from_private_bytes(_b64decode(private_b64))
        except Exception:
            raise SealingError("A configured private key is not a valid X25519 private key") from None
        recipient_public = _public_raw(private.public_key())
        if hashlib.sha256(recipient_public).hexdigest()[:16] != kid:
            continue
        shared = private.exchange(X25519PublicKey.from_public_bytes(ephemeral_public))
        try:
            plaintext = ChaCha20Poly1305(_key(shared, ephemeral_public, recipient_public)).decrypt(
                nonce, ciphertext, _aad(engine_id, kid)
            )
        except InvalidTag:
            raise SealingError("Sealed credentials do not open: wrong engine, or tampered with") from None
        return json.loads(plaintext)

    raise SealingError(f"No configured private key matches key id {kid}")


def mask(value: str, hint_mode: str = "none") -> Dict[str, object]:
    """What the API shows for a credential field: whether it is set and, at most, its last 4 characters"""
    return {"is_set": bool(value), "hint": value[-4:] if (hint_mode == "last4" and value and len(value) > 8) else None}
