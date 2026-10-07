#!/usr/bin/env python3
"""Fix legacy PAGE FK and optionally restore a completed job's missing rows.

Run in the API environment: python scripts/migrate_page_jobs.py --repair-job UUID
Restores already converted pages from Redis/Elasticsearch/MinIO, without running
conversion again. Does not apply unrelated Alembic revisions or change stamps.
"""
import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "backend"))

from shared.database import engine, SessionLocal
from shared.migration_page_jobs import upgrade
from shared.models import Job, JobStatus, Page


def repair_job(job_id):
    from shared.elasticsearch_client import get_es_client
    from shared.minio_client import get_minio_client
    from shared.redis_client import get_redis_client

    redis = get_redis_client()
    es = get_es_client()
    minio = get_minio_client()
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None or job.status != JobStatus.COMPLETED or not job.total_pages:
            raise ValueError("Repair requires an existing completed multi-page job")
        page_ids = {}
        for key in redis.client.scan_iter(match="job:*:status"):
            status = json.loads(redis.client.get(key) or "{}")
            if status.get("parent_job_id") == job_id and status.get("type") == "page":
                page_ids[int(status["page_number"])] = key.split(":")[1]

        restored = []
        # Validate every source before committing: incomplete evidence leaves
        # the job unchanged, instead of creating another partially repaired job.
        for number in range(1, job.total_pages + 1):
            existing = db.query(Page).filter_by(job_id=job_id, page_number=number).first()
            if existing is not None:
                continue
            pdf_path = f"pages/{job_id}/page_{number:04d}.pdf"
            if not minio.file_exists(minio.bucket_pages, pdf_path):
                raise ValueError(f"Page {number}: split PDF missing")
            result = es.get_page_result(job_id, number)
            if result is not None:
                markdown = result["markdown_content"]
            else:
                md_path = f"results/{job_id}/page_{number:04d}.md"
                if not minio.file_exists(minio.bucket_results, md_path):
                    raise ValueError(f"Page {number}: conversion result missing")
                markdown = minio.download_file(minio.bucket_results, md_path).decode("utf-8")
            db.add(Page(id=str(uuid4()), job_id=job_id, page_number=number,
                        page_job_id=page_ids.get(number), minio_page_path=pdf_path,
                        status=JobStatus.COMPLETED, markdown_content=markdown,
                        char_count=len(markdown), has_elasticsearch_result=result is not None,
                        completed_at=job.completed_at))
            restored.append(number)
        db.flush()
        job.pages_completed = db.query(Page).filter_by(job_id=job_id, status=JobStatus.COMPLETED).count()
        job.pages_failed = db.query(Page).filter_by(job_id=job_id, status=JobStatus.FAILED).count()
        db.commit()
        return restored


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repair-job")
    args = parser.parse_args()
    print(json.dumps({"dropped_constraints": upgrade(engine)}))
    if args.repair_job:
        print(json.dumps({"job_id": args.repair_job, "restored_pages": repair_job(args.repair_job)}))
