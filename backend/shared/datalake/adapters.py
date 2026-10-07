"""Explicit credentials only: never use server/cloud ambient credentials."""
import io
import json
from abc import ABC, abstractmethod
from itertools import islice
from urllib.parse import urlparse

import urllib3
from minio import Minio

from shared.datalake.secrets import unseal


class StorageAdapter(ABC):
    @abstractmethod
    def buckets(self) -> list[str]: ...

    @abstractmethod
    def bucket_exists(self, bucket: str) -> bool: ...

    @abstractmethod
    def create_bucket(self, bucket: str, location: str | None = None): ...

    @abstractmethod
    def put(self, bucket: str, key: str, data: bytes, content_type: str): ...

    @abstractmethod
    def objects(self, bucket: str, prefix: str, limit: int = 100) -> list[dict]: ...

    @abstractmethod
    def download(self, bucket: str, key: str, path: str, max_bytes: int): ...


class S3Adapter(StorageAdapter):
    def __init__(self, config, credentials, client=None):
        endpoint = config.get("endpoint") or "https://s3.amazonaws.com"
        parsed = urlparse(endpoint)
        self.region = config.get("region") or "us-east-1"
        self.client = client or Minio(parsed.netloc, access_key=credentials["access_key"],
            secret_key=credentials["secret_key"], session_token=credentials.get("session_token") or None,
            region=config.get("region") or None, secure=parsed.scheme == "https",
            http_client=urllib3.PoolManager(timeout=urllib3.Timeout(connect=5, read=30), retries=1))

    def buckets(self):
        return [b.name for b in self.client.list_buckets()]

    def bucket_exists(self, bucket):
        return self.client.bucket_exists(bucket)

    def create_bucket(self, bucket, location=None):
        self.client.make_bucket(bucket, location=location or self.region)

    def put(self, bucket, key, data, content_type):
        self.client.put_object(bucket, key, io.BytesIO(data), len(data), content_type=content_type)

    def objects(self, bucket, prefix, limit=100):
        return [{"key": o.object_name, "size": o.size} for o in
                islice(self.client.list_objects(bucket, prefix=prefix, recursive=True), limit)]

    def download(self, bucket, key, path, max_bytes):
        if self.client.stat_object(bucket, key).size > max_bytes:
            raise ValueError("Arquivo excede o limite de tamanho")
        response = self.client.get_object(bucket, key)
        try:
            _write_bounded(response.stream(1024 * 1024), path, max_bytes)
        finally:
            response.close()
            response.release_conn()


class MinioAdapter(S3Adapter):
    """MinIO uses the S3 protocol, with a required custom endpoint."""


class GCSAdapter(StorageAdapter):
    def __init__(self, config, credentials, client=None):
        if client is None:
            from google.cloud import storage
            client = storage.Client.from_service_account_info(json.loads(credentials["service_account_json"]),
                                                             project=config.get("project_id") or None)
        self.client = client

    def buckets(self):
        return [b.name for b in self.client.list_buckets(max_results=300, timeout=15)]

    def bucket_exists(self, bucket):
        return self.client.bucket(bucket).exists(timeout=15)

    def create_bucket(self, bucket, location=None):
        self.client.create_bucket(bucket, location=location or "US", timeout=30, retry=None)

    def put(self, bucket, key, data, content_type):
        self.client.bucket(bucket).blob(key).upload_from_string(data, content_type=content_type, timeout=60)

    def objects(self, bucket, prefix, limit=100):
        return [{"key": o.name, "size": o.size} for o in self.client.list_blobs(bucket, prefix=prefix, max_results=limit, timeout=15)]

    def download(self, bucket, key, path, max_bytes):
        blob = self.client.bucket(bucket).blob(key)
        blob.reload(timeout=15)
        if blob.size > max_bytes:
            raise ValueError("Arquivo excede o limite de tamanho")
        # Range reads remain bounded even if the source is replaced mid-download.
        with open(path, "wb") as out:
            for start in range(0, blob.size, 1024 * 1024):
                data = blob.download_as_bytes(start=start, end=min(start + 1024 * 1024, blob.size) - 1,
                                             if_generation_match=blob.generation, timeout=30)
                out.write(data)


class AzureAdapter(StorageAdapter):
    def __init__(self, config, credentials, client=None):
        if client is None:
            from azure.storage.blob import BlobServiceClient
            client = BlobServiceClient.from_connection_string(credentials["connection_string"],
                connection_timeout=5, read_timeout=30, retry_total=1)
        self.client = client

    def buckets(self):
        return [b.name for b in islice(self.client.list_containers(timeout=15), 300)]

    def bucket_exists(self, bucket):
        return self.client.get_container_client(bucket).exists(timeout=15)

    def create_bucket(self, bucket, location=None):
        self.client.create_container(bucket, public_access=None, timeout=30)

    def put(self, bucket, key, data, content_type):
        from azure.storage.blob import ContentSettings
        self.client.get_blob_client(bucket, key).upload_blob(data, overwrite=True,
            content_settings=ContentSettings(content_type=content_type), timeout=60)

    def objects(self, bucket, prefix, limit=100):
        return [{"key": o.name, "size": o.size} for o in islice(
            self.client.get_container_client(bucket).list_blobs(name_starts_with=prefix, timeout=15), limit)]

    def download(self, bucket, key, path, max_bytes):
        blob = self.client.get_blob_client(bucket, key)
        props = blob.get_blob_properties(timeout=15)
        if props.size > max_bytes:
            raise ValueError("Arquivo excede o limite de tamanho")
        _write_bounded(blob.download_blob(etag=props.etag, match_condition=_if_not_modified(), timeout=30).chunks(), path, max_bytes)


def _if_not_modified():
    from azure.core import MatchConditions
    return MatchConditions.IfNotModified


def _write_bounded(chunks, path, max_bytes):
    size = 0
    with open(path, "wb") as out:
        for chunk in chunks:
            size += len(chunk)
            if size > max_bytes:
                raise ValueError("Arquivo excede o limite de tamanho")
            out.write(chunk)


ADAPTERS = {"s3": S3Adapter, "minio": MinioAdapter, "gcs": GCSAdapter, "azure": AzureAdapter}


def validate_credentials(provider, config, credentials):
    required = {"s3": ("access_key", "secret_key"), "minio": ("access_key", "secret_key"),
                "gcs": ("service_account_json",), "azure": ("connection_string",)}[provider]
    if any(not credentials.get(key, "").strip() for key in required):
        raise ValueError("Informe todas as credenciais do provedor")
    if provider == "minio" and not config.get("endpoint"):
        raise ValueError("Informe o endpoint do MinIO")
    if provider == "gcs":
        try:
            account = json.loads(credentials["service_account_json"])
            if not all(account.get(k) for k in ("client_email", "private_key", "token_uri")):
                raise ValueError()
            # Never send private-key assertions to a user-supplied token host.
            if account["token_uri"] != "https://oauth2.googleapis.com/token":
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise ValueError("Informe um JSON de conta de serviço válido do Google") from None


def adapter_for(connection):
    return ADAPTERS[connection.provider](connection.config, unseal(connection))
