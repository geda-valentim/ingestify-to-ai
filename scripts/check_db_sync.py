#!/usr/bin/env python3
"""
Check database synchronization between Redis, MySQL and Elasticsearch

Usage:
    python scripts/check_db_sync.py [job_id]
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.shared.redis_client import get_redis_client
from backend.shared.elasticsearch_client import get_es_client
from backend.shared.database import SessionLocal
from backend.shared.models import Job, Page
from sqlalchemy import func


def check_job_sync(job_id: str):
    """Check synchronization for a specific job"""

    print(f"=" * 70)
    print(f"Checking synchronization for job: {job_id}")
    print(f"=" * 70)

    redis_client = get_redis_client()
    db = SessionLocal()

    try:
        # Check Redis
        print("\n📊 REDIS:")
        redis_status = redis_client.get_job_status(job_id)
        if redis_status:
            print(f"  ✓ Job found in Redis")
            print(f"    Status: {redis_status.get('status')}")
            print(f"    Progress: {redis_status.get('progress')}%")
            print(f"    Type: {redis_status.get('type')}")

            # Check pages in Redis
            total_pages = redis_client.get_job_pages_total(job_id)
            if total_pages:
                completed = redis_client.count_completed_page_jobs(job_id)
                failed = redis_client.count_failed_page_jobs(job_id)
                print(f"    Pages: {completed}/{total_pages} completed, {failed} failed")
        else:
            print(f"  ✗ Job NOT found in Redis")

        # Check MySQL
        print("\n🗄️  MYSQL:")
        mysql_job = db.query(Job).filter(Job.id == job_id).first()
        if mysql_job:
            print(f"  ✓ Job found in MySQL")
            print(f"    Status: {mysql_job.status.value if mysql_job.status else 'N/A'}")
            print(f"    Progress: {mysql_job.progress}%")
            print(f"    Type: {mysql_job.job_type}")
            print(f"    Total Pages: {mysql_job.total_pages}")
            print(f"    Pages Completed: {mysql_job.pages_completed}")
            print(f"    Pages Failed: {mysql_job.pages_failed}")
            print(f"    Created: {mysql_job.created_at}")
            print(f"    Started: {mysql_job.started_at}")
            print(f"    Completed: {mysql_job.completed_at}")

            # Check pages in MySQL
            pages = db.query(Page).filter(Page.job_id == job_id).all()
            print(f"\n  Pages in MySQL: {len(pages)}")
            if pages:
                completed_pages = [p for p in pages if p.status.value == 'completed']
                failed_pages = [p for p in pages if p.status.value == 'failed']
                processing_pages = [p for p in pages if p.status.value == 'processing']
                pending_pages = [p for p in pages if p.status.value == 'pending']

                print(f"    Completed: {len(completed_pages)}")
                print(f"    Failed: {len(failed_pages)}")
                print(f"    Processing: {len(processing_pages)}")
                print(f"    Pending: {len(pending_pages)}")
        else:
            print(f"  ✗ Job NOT found in MySQL")

        # Check Elasticsearch
        print("\n🔍 ELASTICSEARCH:")
        try:
            es_client = get_es_client()
            es_result = es_client.get_job_result(job_id)
            if es_result:
                print(f"  ✓ Job result found in Elasticsearch")
                print(f"    Markdown length: {len(es_result.get('markdown_content', ''))} chars")
                print(f"    Total pages: {es_result.get('total_pages', 'N/A')}")
            else:
                print(f"  ✗ Job result NOT found in Elasticsearch")

            # Check pages in ES
            page_results = es_client.get_all_page_results(job_id)
            print(f"  Pages in Elasticsearch: {len(page_results)}")
        except Exception as e:
            print(f"  ✗ Elasticsearch error: {e}")

        # Summary
        print("\n" + "=" * 70)
        print("SUMMARY:")

        redis_ok = redis_status is not None
        mysql_ok = mysql_job is not None

        if redis_ok and mysql_ok:
            # Compare Redis vs MySQL
            redis_completed = redis_client.count_completed_page_jobs(job_id) if total_pages else 0
            mysql_completed = mysql_job.pages_completed or 0

            if redis_completed != mysql_completed:
                print(f"⚠️  MISMATCH: Redis has {redis_completed} completed pages, MySQL has {mysql_completed}")
                print(f"   This indicates the worker is NOT syncing to MySQL")
                print(f"   Solution: Restart the worker with updated code")
            else:
                print(f"✓ Redis and MySQL are synchronized")
        elif redis_ok and not mysql_ok:
            print(f"⚠️  Job exists in Redis but NOT in MySQL")
            print(f"   This indicates the job was created before MySQL integration")
        elif not redis_ok and mysql_ok:
            print(f"⚠️  Job exists in MySQL but NOT in Redis")
            print(f"   This indicates the job has expired from Redis cache")
        else:
            print(f"✗ Job not found in any database")

    finally:
        db.close()


def list_all_jobs():
    """List all jobs in MySQL"""

    db = SessionLocal()
    try:
        jobs = db.query(Job).filter(Job.parent_job_id == None).order_by(Job.created_at.desc()).limit(10).all()

        print(f"\n📋 Latest 10 MAIN jobs in MySQL:\n")
        print(f"{'ID':<40} {'Status':<12} {'Pages':<15} {'Created':<20}")
        print(f"{'-'*40} {'-'*12} {'-'*15} {'-'*20}")

        for job in jobs:
            pages_info = f"{job.pages_completed or 0}/{job.total_pages or 0}"
            status = job.status.value if job.status else 'N/A'
            created = job.created_at.strftime('%Y-%m-%d %H:%M') if job.created_at else 'N/A'
            print(f"{job.id:<40} {status:<12} {pages_info:<15} {created:<20}")

    finally:
        db.close()


def main():
    if len(sys.argv) > 1:
        job_id = sys.argv[1]
        check_job_sync(job_id)
    else:
        list_all_jobs()
        print("\nUsage: python scripts/check_db_sync.py [job_id]")
        print("       python scripts/check_db_sync.py 69c427c9-3a82-4b29-bbd1-76014e013540")


if __name__ == "__main__":
    main()
