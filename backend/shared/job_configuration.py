"""Persist requests and compare effective options when reusing an upload."""
import hashlib
import json
from shared.models import JobConfiguration


def configuration_fingerprint(operation, options, provider=None, model=None):
    payload = dict(operation=operation, options=options, provider=provider, model=model)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def save_configuration(db, job, *, operation, options, provider=None, model=None):
    row = JobConfiguration(job=job, operation=operation, options=options, provider=provider, model=model,
                           fingerprint=configuration_fingerprint(operation, options, provider, model))
    db.add(row)
    return row


def job_configuration(job):
    row = job.configuration_row if job is not None else None
    if row is None:
        return None
    return dict(operation=row.operation, options=row.options, provider=row.provider, model=row.model)
