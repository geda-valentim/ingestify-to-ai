"""Local copies of uploads are deleted after completion; leftovers are swept after the retention period."""
import os
import time
import uuid

import pytest

import workers.celery_app  # noqa: F401  (import order used by the worker; avoids a circular import)
from workers import monitoring, tasks

DAY = 24 * 3600


def make(path, age_seconds=0, is_dir=False):
    if is_dir:
        path.mkdir(parents=True)
        (path / "file.pdf").write_bytes(b"x")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    past = time.time() - age_seconds
    os.utime(path, (past, past))
    return path


def test_remove_job_files_deletes_work_upload_and_audio_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(tasks.settings, "temp_storage_path", str(tmp_path))
    job = str(uuid.uuid4())
    other = str(uuid.uuid4())
    dirs = [tmp_path / job, tmp_path / "uploads" / job, tmp_path / "audio" / job]
    for d in dirs:
        make(d, is_dir=True)
    keep = make(tmp_path / "uploads" / other, is_dir=True)

    tasks._remove_job_files(job)

    assert not any(d.exists() for d in dirs)
    assert keep.exists()


def test_sweeper_removes_only_old_app_entries(tmp_path):
    old_job = make(tmp_path / str(uuid.uuid4()), 4 * DAY, is_dir=True)
    old_upload = make(tmp_path / "uploads" / str(uuid.uuid4()), 4 * DAY, is_dir=True)
    old_audio = make(tmp_path / "audio" / str(uuid.uuid4()), 4 * DAY, is_dir=True)
    old_staging = make(tmp_path / "uploads" / ".staging" / f"{uuid.uuid4()}.pdf", 4 * DAY)

    recent_upload = make(tmp_path / "uploads" / str(uuid.uuid4()), 3600, is_dir=True)
    recent_staging = make(tmp_path / "audio" / ".staging" / f"{uuid.uuid4()}.mp4", 60)
    foreign = make(tmp_path / "someone-elses-file.txt", 30 * DAY)  # e.g. TEMP_STORAGE_PATH=/tmp

    result = monitoring.remove_stale_temp_files(tmp_path, max_age_seconds=3 * DAY)

    assert result["removed"] == 4
    for gone in (old_job, old_upload, old_audio, old_staging):
        assert not gone.exists()
    for kept in (recent_upload, recent_staging, foreign):
        assert kept.exists()
    # container directories themselves are kept
    assert (tmp_path / "uploads" / ".staging").is_dir()
    assert (tmp_path / "audio").is_dir()


def test_sweeper_handles_missing_directories(tmp_path):
    assert monitoring.remove_stale_temp_files(tmp_path / "does-not-exist", 60) == {"removed": 0}


def test_sweeper_is_scheduled():
    schedule = workers.celery_app.celery_app.conf.beat_schedule
    assert schedule["cleanup-stale-files"]["task"] == "workers.monitoring.cleanup_stale_files"


def test_sweeper_keeps_files_of_active_jobs(tmp_path):
    active, finished = str(uuid.uuid4()), str(uuid.uuid4())
    active_upload = make(tmp_path / "uploads" / active, 10 * DAY, is_dir=True)
    active_work = make(tmp_path / active, 10 * DAY, is_dir=True)
    finished_upload = make(tmp_path / "uploads" / finished, 10 * DAY, is_dir=True)
    old_staging = make(tmp_path / "uploads" / ".staging" / f"{uuid.uuid4()}.pdf", 10 * DAY)

    result = monitoring.remove_stale_temp_files(
        tmp_path, max_age_seconds=3 * DAY, is_job_active=lambda job_id: job_id == active,
    )

    assert active_upload.exists() and active_work.exists()  # backlog: still needed by the worker
    assert not finished_upload.exists()
    assert not old_staging.exists()  # staging files have no job, age alone decides
    assert result["removed"] == 2


def test_sweeper_keeps_files_when_job_state_is_unknown(tmp_path):
    entry = make(tmp_path / "uploads" / str(uuid.uuid4()), 10 * DAY, is_dir=True)

    def db_down(job_id):
        raise ConnectionError("mysql down")

    assert monitoring.remove_stale_temp_files(tmp_path, 3 * DAY, is_job_active=db_down) == {"removed": 0}
    assert entry.exists()


def test_failed_deletions_are_not_counted_and_are_logged(tmp_path, monkeypatch, caplog):
    make(tmp_path / "uploads" / str(uuid.uuid4()), 10 * DAY, is_dir=True)

    def denied(path, *args, **kwargs):
        raise PermissionError("denied")
    monkeypatch.setattr(monitoring.shutil, "rmtree", denied)

    assert monitoring.remove_stale_temp_files(tmp_path, 3 * DAY) == {"removed": 0}
    assert "Could not remove stale file" in caplog.text


def test_remove_job_files_logs_failures(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(tasks.settings, "temp_storage_path", str(tmp_path))
    job = str(uuid.uuid4())
    make(tmp_path / "uploads" / job, is_dir=True)

    def denied(path, *args, **kwargs):
        raise PermissionError("denied")
    monkeypatch.setattr(tasks.shutil, "rmtree", denied)

    tasks._remove_job_files(job)
    assert "Could not remove" in caplog.text
