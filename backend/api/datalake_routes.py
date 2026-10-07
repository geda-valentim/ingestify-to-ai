from datetime import datetime
import re
import json
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Response, Request, UploadFile
from pydantic import BaseModel, Field, SecretStr, ConfigDict, field_validator
from sqlalchemy.orm import Session

from shared.auth import get_current_active_user
from shared.database import get_db
from shared.datalake.adapters import adapter_for, validate_credentials
from shared.datalake.schemas import ConnectionCreate, ConnectionUpdate, ConnectionConfig, Provider, Destination, clean_prefix, clean_bucket
from shared.datalake.secrets import seal, unseal
from shared.datalake import service
from shared.datalake.partitioning import PartitionStrategy, PartitionError, resolve_layout, validate_values
from shared.audio_capabilities import AudioConversionOptions
from shared.document_capabilities import DocumentOptions
from shared.models import DatalakeConnection, JobDatalakeExport, User, JobStatus
from api.deps import get_owned_job
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers

router = APIRouter(prefix="/datalakes", tags=["Datalakes"])


class DiscoverConnection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Provider
    config: ConnectionConfig = Field(default_factory=ConnectionConfig)
    credentials: Optional[dict[str, SecretStr]] = None
    connection_id: Optional[str] = Field(None, max_length=36)
    bucket: Optional[str] = Field(None, max_length=255)

    @field_validator("bucket")
    @classmethod
    def bucket_name(cls, value):
        return clean_bucket(value) if value is not None else None


def draft_connection(body: DiscoverConnection, user: User, db: Session):
    row = connection_or_404(db, user, body.connection_id) if body.connection_id else None
    if row is not None and row.provider != body.provider:
        raise HTTPException(422, "O provedor da conexão não pode ser alterado")
    if body.credentials is None and row is None:
        raise HTTPException(422, "Informe as credenciais do provedor")
    credentials = ({key: value.get_secret_value() for key, value in body.credentials.items()}
                   if body.credentials is not None else unseal(row))
    config = body.config.model_dump()
    ensure_credentials(body.provider, config, credentials)
    # Draft operations never persist or change an existing connection.
    connection_id = str(uuid4())
    return DatalakeConnection(id=connection_id, user_id=user.id, provider=body.provider,
        config=config, credentials_encrypted=seal(user.id, connection_id, credentials))


@router.post("/discover")
def discover_connection(body: DiscoverConnection, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """Read buckets with draft settings, without creating or updating a connection."""
    draft = draft_connection(body, user, db)
    try:
        adapter = adapter_for(draft)
        if body.bucket is not None:
            bucket = clean_bucket(body.bucket)
            if not adapter.bucket_exists(bucket):
                raise HTTPException(422, "Bucket não encontrado ou sem acesso")
            return {"buckets": [bucket], "verified": True}
        return {"buckets": sorted(set(adapter.buckets())), "verified": True}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, "Não foi possível listar os buckets. Verifique a conexão ou informe um bucket para validar seu acesso.") from None


class CreateBucket(DiscoverConnection):
    bucket: str = Field(min_length=3, max_length=222)
    location: Optional[str] = Field(None, min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9-]+$")


def validate_new_bucket(provider, bucket):
    pattern = r"[a-z0-9][a-z0-9.-]*[a-z0-9]"
    maximum = 63
    if provider == "azure":
        pattern = r"[a-z0-9][a-z0-9-]*[a-z0-9]"
    elif provider == "gcs":
        pattern = r"[a-z0-9][a-z0-9._-]*[a-z0-9]"
        maximum = 222 if "." in bucket else 63
    invalid = (not re.fullmatch(pattern, bucket) or not 3 <= len(bucket) <= maximum
        or ".." in bucket or re.fullmatch(r"\d+\.\d+\.\d+\.\d+", bucket))
    if provider == "azure":
        invalid = invalid or "--" in bucket
    elif provider == "gcs":
        invalid = invalid or any(len(part) > 63 for part in bucket.split(".")) or bucket.startswith("goog") or "google" in bucket or "g00gle" in bucket
    else:
        invalid = invalid or ".-" in bucket or "-." in bucket or bucket.startswith(("xn--", "sthree-", "amzn-s3-demo-")) or bucket.endswith(("-s3alias", "--ol-s3", ".mrap", "--x-s3", "--table-s3", "-an"))
    if invalid:
        raise HTTPException(422, "Nome inválido para o provedor. Use de 3 a 63 letras minúsculas, números e hífens, começando e terminando com letra ou número.")


@router.post("/buckets", status_code=201)
def create_bucket(body: CreateBucket, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """Create storage now; saving the connection remains a separate operation."""
    draft = draft_connection(body, user, db)
    validate_new_bucket(body.provider, body.bucket)
    location = None
    if body.provider in ("s3", "minio"):
        location = body.config.region or "us-east-1"
    elif body.provider == "gcs":
        location = "US"
    if body.location is not None:
        if body.provider == "azure" or (body.provider in ("s3", "minio") and body.location != location):
            raise HTTPException(422, "Use a região configurada na conexão; no Azure, o container usa a região da conta.")
        location = body.location
    try:
        adapter = adapter_for(draft)
        # S3 in us-east-1 can succeed when recreating an owned bucket and reset
        # its ACL. Always check first, so this action never changes existing storage.
        if adapter.bucket_exists(body.bucket):
            raise HTTPException(409, "Este bucket já existe. Use ‘Verificar outro bucket’ para selecioná-lo.")
        adapter.create_bucket(body.bucket, location=location)
        return {"bucket": body.bucket, "created": True, "location": location}
    except HTTPException:
        raise
    except Exception as exc:
        code = getattr(exc, "code", None)
        status = getattr(exc, "status_code", None)
        if code in ("BucketAlreadyExists", "BucketAlreadyOwnedByYou", "ContainerAlreadyExists") or code == 409 or status == 409:
            raise HTTPException(409, "Nome já utilizado. Escolha outro nome ou verifique o bucket existente.") from None
        if code in ("AccessDenied", "AuthorizationFailure", "AuthorizationPermissionMismatch") or code in (401, 403) or status in (401, 403):
            raise HTTPException(403, "A conta não tem permissão para verificar ou criar este bucket. Verifique as credenciais e permissões no provedor.") from None
        raise HTTPException(502, "Não foi possível confirmar a criação. Verifique o nome do bucket no provedor antes de tentar novamente.") from None


def public_connection(row):
    return {"id": row.id, "name": row.name, "provider": row.provider, "config": row.config,
            "enabled": row.enabled, "credentials_configured": True,
            "created_at": row.created_at, "updated_at": row.updated_at}


def connection_or_404(db, user, connection_id):
    row = service.owned_connection(db, connection_id, user.id)
    if row is None:
        raise HTTPException(404, "Conexão não encontrada")
    return row


def ensure_credentials(provider, config, credentials):
    try:
        validate_credentials(provider, config, credentials)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


class PartitionPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connection_id: Optional[str] = Field(None, max_length=36)
    partitioning: Optional[PartitionStrategy] = None
    partition_values: dict[str, str] = Field(default_factory=dict)
    prefix: str = Field("", max_length=700)
    created_at: Optional[datetime] = None
    project_id: Optional[str] = Field(None, max_length=36)
    folder_id: Optional[str] = Field(None, max_length=36)
    source_type: Optional[str] = Field(None, max_length=50)

    @field_validator("prefix")
    @classmethod
    def clean_path(cls, value):
        return clean_prefix(value)

    @field_validator("partition_values")
    @classmethod
    def valid_values(cls, value):
        return validate_values(value)


@router.post("/partition-preview")
def partition_preview(body: PartitionPreview, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    connection = connection_or_404(db, user, body.connection_id) if body.connection_id else None
    config = connection.config if connection else {}
    strategy = body.partitioning or PartitionStrategy.model_validate(config.get("partitioning") or {})
    values = {**(config.get("default_partition_values") or {}), **body.partition_values}
    context = {"job_id": "00000000-0000-0000-0000-000000000000", "created_at": body.created_at or datetime.utcnow(),
        "project_id": body.project_id, "folder_id": body.folder_id, "source_type": body.source_type}
    try:
        return {**resolve_layout(strategy, body.prefix, context, values), "partitioning": strategy.model_dump()}
    except PartitionError as exc:
        raise HTTPException(422, str(exc)) from None


@router.get("")
def list_connections(user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    return {"connections": [public_connection(row) for row in db.query(DatalakeConnection)
                            .filter(DatalakeConnection.user_id == user.id).order_by(DatalakeConnection.name).all()]}


@router.post("", status_code=201)
def create_connection(body: ConnectionCreate, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    credentials = {key: value.get_secret_value() for key, value in body.credentials.items()}
    config = body.config.model_dump()
    ensure_credentials(body.provider, config, credentials)
    connection_id = str(uuid4())
    row = DatalakeConnection(id=connection_id, user_id=user.id, name=body.name, provider=body.provider,
        config=config, enabled=body.enabled, credentials_encrypted=seal(user.id, connection_id, credentials))
    db.add(row)
    db.commit()
    return public_connection(row)


@router.patch("/{connection_id}")
def update_connection(connection_id: str, body: ConnectionUpdate,
                      user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    row = connection_or_404(db, user, connection_id)
    credentials = {key: value.get_secret_value() for key, value in body.credentials.items()} if body.credentials is not None else unseal(row)
    config = body.config.model_dump() if body.config is not None else row.config
    ensure_credentials(row.provider, config, credentials)
    if body.name is not None:
        if not body.name.strip():
            raise HTTPException(422, "Informe um nome")
        row.name = body.name.strip()
    row.config = config
    if body.enabled is not None:
        row.enabled = body.enabled
    row.credentials_encrypted = seal(user.id, row.id, credentials)
    db.commit()
    return public_connection(row)


@router.delete("/{connection_id}", status_code=204)
def delete_connection(connection_id: str, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    row = connection_or_404(db, user, connection_id)
    if db.query(JobDatalakeExport).filter(JobDatalakeExport.connection_id == row.id).first():
        raise HTTPException(409, "Esta conexão está vinculada a jobs. Desative-a para impedir novas solicitações.")
    db.delete(row)
    db.commit()
    return Response(status_code=204)


@router.get("/{connection_id}/buckets")
def list_buckets(connection_id: str, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    row = connection_or_404(db, user, connection_id)
    if not row.enabled:
        raise HTTPException(409, "Conexão desativada")
    configured = row.config.get("buckets") or []
    try:
        buckets = configured or adapter_for(row).buckets()
        return {"buckets": sorted(buckets), "configured": bool(configured)}
    except Exception:
        raise HTTPException(502, "Não foi possível listar os buckets. Verifique as credenciais ou configure os buckets permitidos.") from None


class TestConnection(BaseModel):
    bucket: Optional[str] = Field(None, max_length=255)


class ImportObject(BaseModel):
    connection_id: str = Field(min_length=1, max_length=36)
    bucket: str = Field(min_length=1, max_length=255)
    key: str = Field(min_length=1, max_length=1024)
    project: Optional[str] = None
    project_id: Optional[str] = None
    folder: Optional[str] = None
    folder_id: Optional[str] = None
    name: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    docling_preset: str = "fast"
    conversion_options: Optional[DocumentOptions] = None
    audio_options: Optional[AudioConversionOptions] = None
    datalake: Optional[Destination] = None


@router.post("/import", status_code=202)
async def import_object(body: ImportObject, request: Request,
                        user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    import mimetypes
    from pathlib import Path
    from api.projects_api import LocationFields, prepare_upload_location
    from api.routes import upload_and_convert, transcribe_audio, _document_request_options, _audio_request_options
    from shared.config import get_settings
    from shared.utils import sanitize_upload_filename
    from workers.audio.base_transcriber import VIDEO_FORMATS
    from shared.engines.media import is_audio_filename

    filename = sanitize_upload_filename(body.key.rsplit("/", 1)[-1])
    video = Path(filename).suffix.lstrip(".").lower() in VIDEO_FORMATS
    audio = is_audio_filename(filename) or video
    if body.docling_preset not in ("fast", "balanced", "quality"):
        raise HTTPException(422, "Preset inválido")
    if audio:
        if body.conversion_options is not None or body.docling_preset != 'fast':
            raise HTTPException(422, 'Controles Docling não se aplicam a áudio/vídeo')
        audio_options = body.audio_options or AudioConversionOptions()
        provider, _, _ = _audio_request_options(audio_options)
    else:
        if body.audio_options is not None:
            raise HTTPException(422, 'audio_options exige um arquivo de áudio/vídeo')
        _document_request_options(body.conversion_options, body.docling_preset)
    location = LocationFields(body.project, body.project_id, body.folder, body.folder_id)
    prepare_upload_location(db, user, request, location)
    row = connection_or_404(db, user, body.connection_id)
    await run_in_threadpool(prepare_body_destination, db, user, Destination(connection_id=row.id, bucket=body.bucket))
    destination = await run_in_threadpool(prepare_body_destination, db, user, body.datalake) if body.datalake else None
    settings = get_settings()
    limit = settings.max_video_file_size_mb if video else settings.max_audio_file_size_mb if audio else settings.max_file_size_mb
    if audio and provider == 'openai-api':
        limit = min(limit, 25)
    path = Path(settings.temp_storage_path) / "datalake-imports" / f"{uuid4()}.download"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        try:
            await run_in_threadpool(adapter_for(row).download, body.bucket, body.key, str(path), limit * 1024 * 1024)
        except ValueError:
            raise HTTPException(413, "Arquivo excede o limite de tamanho") from None
        except Exception:
            raise HTTPException(502, "Não foi possível ler o arquivo do bucket") from None
        with path.open("rb") as stream:
            upload = UploadFile(stream, filename=filename, headers=Headers({"content-type": mimetypes.guess_type(filename)[0] or "application/octet-stream"}))
            common = dict(file=upload, name=body.name, tags=",".join(body.tags) or None, request=request,
                          location=location, destination=destination, current_user=user, db=db)
            previous_source = getattr(request.state, "datalake_source_type", None)
            request.state.datalake_source_type = "datalake"
            try:
                if audio:
                    result = await transcribe_audio(**common, language=None, include_timestamps=audio_options.include_timestamps,
                        include_word_timestamps=audio_options.include_word_timestamps,
                        output_format=audio_options.output_format, purge_source=audio_options.purge_source,
                        operation=audio_options.operation,
                        decoding_options=json.dumps(audio_options.decoding.model_dump(exclude_unset=True)))
                else:
                    result = await upload_and_convert(**common, docling_preset=body.docling_preset, conversion_options=body.conversion_options)
            finally:
                request.state.datalake_source_type = previous_source
            return result
    finally:
        path.unlink(missing_ok=True)


@router.post("/{connection_id}/test")
def test_connection(connection_id: str, body: TestConnection,
                    user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    row = connection_or_404(db, user, connection_id)
    bucket = body.bucket or row.config.get("default_bucket")
    try:
        if bucket:
            service.prepare_destination(db, user.id, Destination(connection_id=row.id, bucket=bucket))
        else:
            adapter_for(row).buckets()
    except Exception:
        raise HTTPException(502, "Não foi possível acessar a conexão. Verifique as credenciais, o endpoint e as permissões.") from None
    return {"ok": True, "bucket": bucket}


@router.get("/{connection_id}/objects")
def list_objects(connection_id: str, bucket: str, prefix: str = "", limit: int = Query(100, ge=1, le=1000),
                 user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    row = connection_or_404(db, user, connection_id)
    try:
        choice = Destination(connection_id=row.id, bucket=bucket)
        service.prepare_destination(db, user.id, choice)
        return {"objects": adapter_for(row).objects(choice.bucket, prefix, limit), "limit": limit}
    except Exception:
        raise HTTPException(502, "Não foi possível listar os arquivos deste bucket") from None


def destination_form(
    datalake_connection_id: Optional[str] = Form(None), datalake_bucket: Optional[str] = Form(None),
    datalake_prefix: str = Form(""), datalake_partitioning: Optional[str] = Form(None,
        description="JSON da estratégia por solicitação; omitir herda a conexão. Ex.: "
        '{"mode":"custom","fields":[{"field":"custom","key":"client_id"}],"missing":"require","analytics":"jsonl"}'),
    datalake_partition_values: Optional[str] = Form(None,
        description="JSON de valores por job. Chaves fora da estratégia preservam contexto no dataset "
        "sem criar diretórios. Ex.: "
        '{"client_id":"client-42","conversation_id":"chat-7","agent_id":"support-agent"}'),
    user: User = Depends(get_current_active_user), db: Session = Depends(get_db),
):
    if not datalake_connection_id and not datalake_bucket and not datalake_prefix and not datalake_partitioning and not datalake_partition_values:
        return None
    try:
        choice = Destination(connection_id=datalake_connection_id or "", bucket=datalake_bucket or "", prefix=datalake_prefix,
            partitioning=json.loads(datalake_partitioning) if datalake_partitioning else None,
            partition_values=json.loads(datalake_partition_values) if datalake_partition_values else {})
        return service.prepare_destination(db, user.id, choice)
    except LookupError:
        raise HTTPException(404, "Conexão não encontrada") from None
    except ValueError:
        raise HTTPException(422, "Informe uma conexão, um bucket permitido e uma pasta válida") from None
    except Exception:
        raise HTTPException(502, "Não foi possível acessar o bucket de destino") from None


def bind_request_destination(db, job, destination, source_type=None):
    # Direct unit callers leave FastAPI's Depends default in place.
    if not isinstance(destination, Destination):
        return
    try:
        service.bind_destination(db, job, destination, source_type=source_type)
    except PartitionError as exc:
        raise HTTPException(422, str(exc)) from None


def discard_uncommitted_destination(cache, job_id, user_id):
    """Evict all submission metadata only when the SQL job was rolled back."""
    cache.delete_job(job_id)
    cache.remove_job_from_user(user_id, job_id)
    try:
        cache.client.delete(f"job:{job_id}:owner", f"job:{job_id}:output_format")
    except Exception:
        import logging
        logging.getLogger(__name__).warning("Could not discard uncommitted job metadata: job_id=%s", job_id)


def prepare_body_destination(db, user, choice):
    try:
        return service.prepare_destination(db, user.id, choice)
    except LookupError:
        raise HTTPException(404, "Conexão não encontrada") from None
    except ValueError:
        raise HTTPException(422, "Destino inválido ou conexão desativada") from None
    except Exception:
        raise HTTPException(502, "Não foi possível acessar o bucket de destino") from None


job_router = APIRouter(tags=["Datalakes"])


@job_router.get("/jobs/{job_id}/datalake")
def get_delivery(job_id: str, owned_job=Depends(get_owned_job), db: Session = Depends(get_db)):
    return {"destination": service.export_ref(db, job_id)}


@job_router.post("/jobs/{job_id}/datalake/retry", status_code=202)
def retry_delivery(job_id: str, owned_job=Depends(get_owned_job), db: Session = Depends(get_db)):
    if owned_job is None or owned_job.id != job_id or owned_job.status != JobStatus.COMPLETED:
        raise HTTPException(409, "Aguarde a conclusão do job")
    dest = db.get(JobDatalakeExport, job_id)
    if dest is None:
        raise HTTPException(404, "Destino não encontrado")
    if dest.status != "completed":
        dest.status, dest.error, dest.attempts = "pending", None, 0
        db.commit()
        service.enqueue_export(job_id)
    return {"destination": service.export_ref(db, job_id)}
