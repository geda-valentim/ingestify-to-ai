"""Authenticated encryption tied to the owner and connection identifier."""
import base64
import hashlib
import json

from cryptography.fernet import Fernet
from shared.config import get_settings


def cipher():
    settings = get_settings()
    key = settings.datalake_encryption_key or base64.urlsafe_b64encode(
        hashlib.sha256(b"ingestify:datalake:v1\0" + settings.jwt_secret_key.encode()).digest())
    return Fernet(key)


def seal(user_id, connection_id, credentials):
    return cipher().encrypt(json.dumps({"owner": user_id, "connection": connection_id,
                                       "credentials": credentials}).encode())


def unseal(connection):
    payload = json.loads(cipher().decrypt(connection.credentials_encrypted))
    if payload["owner"] != connection.user_id or payload["connection"] != connection.id:
        raise ValueError("Credential binding mismatch")
    return payload["credentials"]
