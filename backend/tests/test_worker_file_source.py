"""The worker must only read files the API saved for the same job."""
import pytest

import workers.celery_app  # noqa: F401  (import order used by the worker; avoids a circular import)
from workers import tasks

JOB_ID = "job-1"


@pytest.fixture
def temp_root(tmp_path, monkeypatch):
    monkeypatch.setattr(tasks.settings, "temp_storage_path", str(tmp_path))
    for sub in (f"uploads/{JOB_ID}", "uploads/job-2", f"audio/{JOB_ID}"):
        (tmp_path / sub).mkdir(parents=True)
    return tmp_path


@pytest.mark.parametrize("relative", [f"uploads/{JOB_ID}/doc.pdf", f"audio/{JOB_ID}/talk.mp3"])
def test_accepts_files_saved_for_this_job(temp_root, relative):
    path = temp_root / relative
    assert tasks._resolve_uploaded_file(str(path), JOB_ID) == path.resolve()


@pytest.mark.parametrize(
    "source",
    [
        "uploads/job-2/secret.pdf",          # another job's upload
        f"uploads/{JOB_ID}/../job-2/x.pdf",  # traversal out of the job dir
        "other/doc.pdf",                     # elsewhere under temp storage
    ],
)
def test_rejects_paths_outside_this_job(temp_root, source):
    with pytest.raises(ValueError):
        tasks._resolve_uploaded_file(str(temp_root / source), JOB_ID)


@pytest.mark.parametrize("source", ["/etc/passwd", "", None])
def test_rejects_system_and_missing_paths(temp_root, source):
    with pytest.raises(ValueError):
        tasks._resolve_uploaded_file(source, JOB_ID)


def test_rejects_symlink_escaping_job_dir(temp_root, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "secret.txt"
    outside.write_text("secret")
    link = temp_root / f"uploads/{JOB_ID}/link.pdf"
    link.symlink_to(outside)
    with pytest.raises(ValueError):
        tasks._resolve_uploaded_file(str(link), JOB_ID)
