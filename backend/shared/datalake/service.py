import json
from datetime import datetime

from sqlalchemy.orm import Session

from shared.database import SessionLocal
from shared.iam import ownership
from shared.datalake.adapters import adapter_for
from shared.datalake.schemas import Destination
from shared.minio_client import get_minio_client
from shared.models import DatalakeConnection, Job, JobDatalakeExport, JobDatalakePartition, JobStatus, LiveSession
from shared.datalake.partitioning import PartitionStrategy, PartitionError, job_context, resolve_layout, analytic_outputs
from shared.transcripts import TRANSCRIPT_CONTENT_TYPES, transcript_result_object_name


def owned_connection(db: Session, connection_id: str, user_id: str):
    """The connection when `user_id` owns it, decided by `shared.iam.ownership` (spec 0014)."""
    return ownership.owned_row(db, DatalakeConnection, connection_id, user_id)


def prepare_destination(db, user_id, choice):
    if choice is None:
        return None
    connection = owned_connection(db, choice.connection_id, user_id)
    if connection is None:
        raise LookupError("Conexão não encontrada")
    if not connection.enabled:
        raise ValueError("Conexão desativada")
    allowed = connection.config.get("buckets") or []
    if allowed and choice.bucket not in allowed:
        raise ValueError("Bucket não permitido para esta conexão")
    if not adapter_for(connection).bucket_exists(choice.bucket):
        raise ValueError("Bucket não encontrado ou sem acesso")
    return choice


def bind_destination(db, job, choice, source_type=None):
    if choice is None:
        return
    db.flush()  # Parent job must exist before inserting its destination FK.
    existing = db.get(JobDatalakeExport, job.id)
    if existing is not None:
        if (existing.connection_id, existing.bucket, existing.prefix) != (choice.connection_id, choice.bucket, choice.prefix):
            raise ValueError("Este job já possui outro destino")
        return
    db.add(JobDatalakeExport(job_id=job.id, connection_id=choice.connection_id,
                            bucket=choice.bucket, prefix=choice.prefix, status="pending"))
    connection = owned_connection(db, choice.connection_id, job.user_id)
    if connection is None:
        raise PartitionError("Conexão não encontrada")
    strategy = choice.partitioning or PartitionStrategy.model_validate(connection.config.get("partitioning") or {})
    values = {**(connection.config.get("default_partition_values") or {}), **choice.partition_values}
    context = job_context(job, source_type)
    resolved = resolve_layout(strategy, choice.prefix, context, values)
    db.add(JobDatalakePartition(job_id=job.id, strategy=strategy.model_dump(), context=context, values=values, **resolved))


def export_ref(db, job_id):
    dest = db.get(JobDatalakeExport, job_id)
    if dest is None:
        return None
    connection = db.get(DatalakeConnection, dest.connection_id)
    partition = db.get(JobDatalakePartition, job_id)
    return {"connection_id": dest.connection_id, "connection_name": connection.name if connection else None,
            "provider": connection.provider if connection else None, "bucket": dest.bucket, "prefix": dest.prefix,
            "status": dest.status, "error": dest.error, "attempts": dest.attempts,
            "objects": dest.objects or [], "completed_at": dest.completed_at,
            "partitioning": partition.strategy if partition else None,
            "partition_values": partition.values if partition else {},
            "partitions": partition.partitions if partition else {},
            "layout_id": partition.layout_id if partition else None,
            "resolved_path": partition.resolved_path if partition else (f"{dest.prefix}/{job_id}" if dest.prefix else job_id),
            "dataset_path": partition.dataset_path if partition else None, "schema_path": partition.schema_path if partition else None}


def stage_result(job_id, payload, session_factory=None):
    """Persist output before cache expiry; only jobs with a selected destination."""
    with (session_factory or SessionLocal)() as db:
        dest = db.get(JobDatalakeExport, job_id)
        if dest is None:
            return
        name = f"datalake/{job_id}/result.json"
        minio = get_minio_client()
        if not minio.upload_file(bucket_name=minio.bucket_results, object_name=name,
            file_data=json.dumps(payload, ensure_ascii=False, default=str).encode(), content_type="application/json"):
            raise RuntimeError("Não foi possível preservar o resultado para entrega ao datalake")
        dest.snapshot_path = name
        db.commit()


def _publish_export(job_id):
    from celery import Celery
    from shared.config import get_settings, redis_url_with_password
    settings = get_settings()
    with Celery('ingestify-delivery', broker=redis_url_with_password(settings.celery_broker_url, settings.redis_password)) as publisher:
        publisher.send_task('workers.datalake_tasks.export_result', args=[job_id],
                            queue=settings.celery_task_default_queue, retry=False)


def enqueue_export(job_id, session_factory=None):
    """A beat sweep recovers delivery even when the broker is temporarily down."""
    with (session_factory or SessionLocal)() as db:
        if db.get(JobDatalakeExport, job_id) is None:
            return
    try:
        _publish_export(job_id)
    except Exception:
        # No secret or SDK exception body belongs in logs or the job response.
        import logging
        logging.getLogger(__name__).warning("Datalake delivery queued for reconciliation: job_id=%s", job_id)


def export_result(job_id):
    """Idempotent writes. SQL lock serializes retries and deletion for one job."""
    with SessionLocal() as db:
        job = db.query(Job).filter(Job.id == job_id).with_for_update().first()
        if job is None or job.status not in (JobStatus.COMPLETED, JobStatus.PARTIAL):
            return
        dest = db.query(JobDatalakeExport).filter(JobDatalakeExport.job_id == job_id).with_for_update().first()
        if dest is None or dest.status == "completed" or (dest.attempts or 0) >= 5:
            return
        dest.status = "exporting"
        dest.attempts = (dest.attempts or 0) + 1
        dest.updated_at = datetime.utcnow()
        try:
            connection = owned_connection(db, dest.connection_id, job.user_id)
            if connection is None or not connection.enabled:
                raise ValueError("Connection unavailable")
            allowed = connection.config.get("buckets") or []
            if allowed and dest.bucket not in allowed:
                raise ValueError("Bucket no longer allowed")
            minio = get_minio_client()
            if job.source_type == 'image' and job.minio_result_path:
                data = minio.download_file(minio.bucket_results, job.minio_result_path)
            elif dest.snapshot_path:
                data = minio.download_file(minio.bucket_results, dest.snapshot_path)
            else:
                from shared.live.lifecycle import available
                live = db.get(LiveSession, job_id) if available(db) else None
                if live is not None and live.state != "completed":
                    raise ValueError("Unpublished live result")
                data = minio.download_file(minio.bucket_audio,
                    transcript_result_object_name(job_id, live.generation if live else None))
            payload = json.loads(data)
            adapter = adapter_for(connection)
            partition = db.get(JobDatalakePartition, job_id)
            base = partition.resolved_path if partition else (f"{dest.prefix}/{job_id}" if dest.prefix else job_id)
            # The durable destination must not depend on the original job's
            # authenticated asset URLs (the source job can later be deleted).
            for asset in payload.get('assets', []):
                source_url, relative_url = asset['url'], 'assets/' + asset['name']
                if 'markdown' in payload:
                    payload['markdown'] = payload['markdown'].replace(source_url, relative_url)
                payload['exports'] = {fmt: content.replace(source_url, relative_url)
                                      for fmt, content in (payload.get('exports') or {}).items()}
                asset['url'] = relative_url
            outputs = {"result.json": (json.dumps(payload, ensure_ascii=False).encode(), "application/json")}
            if "markdown" in payload:
                outputs["result.md"] = (payload["markdown"].encode(), "text/markdown; charset=utf-8")
            outputs["metadata.json"] = (json.dumps(payload.get("metadata", {}), ensure_ascii=False).encode(), "application/json")
            for fmt, content in (payload.get("transcript") or {}).items():
                if fmt in TRANSCRIPT_CONTENT_TYPES:
                    outputs[f"transcript.{fmt}"] = (content.encode(), TRANSCRIPT_CONTENT_TYPES[fmt])
            keys = []
            for filename, (content, content_type) in outputs.items():
                key = f"{base}/{filename}"
                adapter.put(dest.bucket, key, content, content_type)
                keys.append(key)
            if partition and partition.dataset_path:
                for key, (content, content_type) in analytic_outputs(partition, payload).items():
                    adapter.put(dest.bucket, key, content, content_type)
                    keys.append(key)
            dest.objects, dest.status, dest.error = keys, "completed", None
            dest.completed_at = datetime.utcnow()
        except Exception:
            dest.status = "failed"
            dest.error = "Não foi possível entregar ao bucket. Verifique a conexão e as permissões e tente novamente."
            db.commit()
            # Persist the failure independently, then let Celery schedule a retry.
            raise RuntimeError("Datalake delivery failed") from None
        db.commit()
