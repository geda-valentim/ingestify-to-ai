from typing import Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from shared.datalake.partitioning import PartitionStrategy, validate_values

Provider = Literal["s3", "minio", "gcs", "azure"]


def clean_prefix(value: str) -> str:
    value = value.strip().strip("/")
    if any(part in (".", "..") for part in value.split("/")) or "\\" in value or any(ord(c) < 32 for c in value):
        raise ValueError("Pasta inválida")
    return value


def clean_bucket(value: str) -> str:
    value = value.strip()
    if not value or len(value) > 255 or any(c in value for c in "/\\") or any(ord(c) < 33 for c in value):
        raise ValueError("Bucket inválido")
    return value


class ConnectionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    endpoint: Optional[str] = None
    region: Optional[str] = Field(None, max_length=100)
    project_id: Optional[str] = Field(None, max_length=255)
    buckets: list[str] = Field(default_factory=list, max_length=100)
    default_bucket: Optional[str] = None
    default_prefix: str = Field("", max_length=700)
    partitioning: Optional[PartitionStrategy] = None
    default_partition_values: dict[str, str] = Field(default_factory=dict,
        description="Valores personalizados padrão. Também preserva contexto sem criar partições, como agent_id.")

    @field_validator("default_partition_values")
    @classmethod
    def partition_values(cls, value):
        return validate_values(value)

    @field_validator("endpoint")
    @classmethod
    def endpoint_url(cls, value):
        if not value:
            return None
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
            raise ValueError("Informe um endpoint HTTP(S) sem credenciais, parâmetros ou caminho")
        return value.rstrip("/")

    @field_validator("default_prefix")
    @classmethod
    def prefix(cls, value):
        return clean_prefix(value)

    @field_validator("buckets")
    @classmethod
    def bucket_names(cls, value):
        return list(dict.fromkeys(clean_bucket(name) for name in value))

    @field_validator("default_bucket")
    @classmethod
    def default_bucket_name(cls, value):
        return clean_bucket(value) if value else None

    @model_validator(mode="after")
    def default_is_allowed(self):
        if self.buckets and self.default_bucket and self.default_bucket not in self.buckets:
            raise ValueError("O bucket padrão deve estar na lista de buckets permitidos")
        return self


class ConnectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=150)
    provider: Provider
    config: ConnectionConfig = Field(default_factory=ConnectionConfig)
    credentials: dict[str, SecretStr]
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def trimmed_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Informe um nome")
        return value


class ConnectionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Optional[str] = Field(None, min_length=1, max_length=150)
    config: Optional[ConnectionConfig] = None
    credentials: Optional[dict[str, SecretStr]] = None
    enabled: Optional[bool] = None


class Destination(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connection_id: str = Field(min_length=1, max_length=36)
    bucket: str = Field(min_length=1, max_length=255)
    prefix: str = Field("", max_length=700)
    partitioning: Optional[PartitionStrategy] = Field(None,
        description="Estratégia desta solicitação. Ausência herda a conexão; mode=none desativa partições.")
    partition_values: dict[str, str] = Field(default_factory=dict,
        description="Valores personalizados por job, como client_id, conversation_id e agent_id. "
        "Somente chaves da estratégia criam diretórios; todos os valores ficam congelados e, "
        "com analytics=jsonl, preservados em partition_values_json. Sobrescrevem os padrões da conexão.")

    @field_validator("partition_values")
    @classmethod
    def valid_partition_values(cls, value):
        return validate_values(value)

    @field_validator("bucket")
    @classmethod
    def bucket_name(cls, value):
        return clean_bucket(value)

    @field_validator("prefix")
    @classmethod
    def prefix_path(cls, value):
        return clean_prefix(value)
