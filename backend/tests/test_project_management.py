"""Maintenance preserves job data, enforces ownership and moves atomically."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import apikey_routes, project_management, projects_api
from shared.auth import get_current_active_user
from shared.config import get_settings
from shared.database import get_db
from shared.models import APIKey, Folder, Job, JobStatus, Project, User
from tests.test_projects_api import ALICE, BOB, db, folder, job, project  # noqa: F401


@pytest.fixture
def client(db):
    app = FastAPI()
    app.include_router(projects_api.router)
    app.include_router(project_management.router)
    app.include_router(apikey_routes.router, prefix='/api-keys')
    def dbdep():
        try:
            yield db
        except Exception:
            db.rollback()
            raise
    app.dependency_overrides[get_db] = dbdep
    app.dependency_overrides[get_current_active_user] = lambda: db.get(User, ALICE)
    return TestClient(app)


def test_create_get_or_add_edit_description_and_immutable_identity(client, db):
    response = client.post('/projects', json={'name': '  Reunião  Semanal '})
    assert response.status_code == 201
    p = response.json()
    again = client.post('/projects', json={'name': 'reuniao semanal'})
    assert again.status_code == 200 and again.json()['id'] == p['id']
    assert db.query(Project).count() == 1
    edited = client.patch('/projects/' + p['id'], json={'name': 'REUNIÃO SEMANAL', 'description': 'Áudios'})
    assert edited.status_code == 200
    assert edited.json()['description'] == 'Áudios'
    assert client.patch('/projects/' + p['id'], json={'name': 'Outro projeto', 'archived': True}).status_code == 422
    db.expire_all()
    assert db.get(Project, p['id']).archived_at is None
    assert client.patch('/projects/' + p['id'], json={'description': None}).json()['description'] is None


def test_folder_get_or_add_cosmetic_edit_and_invalid_names(client, db):
    p = project(db, 'A')
    response = client.post(f'/projects/{p.id}/folders', json={'name': 'Áudios'})
    assert response.status_code == 201
    f = response.json()
    assert client.post(f'/projects/{p.id}/folders', json={'name': 'audios'}).json()['id'] == f['id']
    assert client.patch(f"/folders/{f['id']}", json={'name': 'ÁUDIOS'}).status_code == 200
    assert client.patch(f"/folders/{f['id']}", json={'name': 'Vídeos'}).status_code == 422
    assert client.post(f'/projects/{p.id}/folders', json={'name': 'a/b'}).status_code == 422
    assert client.post('/projects', json={'name': '   '}).status_code == 422


def test_limits_are_reused_and_existing_names_still_resolve(client, db, monkeypatch):
    monkeypatch.setattr(get_settings(), 'max_projects_per_user', 1)
    monkeypatch.setattr(get_settings(), 'max_folders_per_project', 1)
    p = project(db, 'A')
    assert client.post('/projects', json={'name': 'a'}).status_code == 200
    assert client.post('/projects', json={'name': 'B'}).status_code == 422
    assert client.post(f'/projects/{p.id}/folders', json={'name': 'F'}).status_code == 201
    assert client.post(f'/projects/{p.id}/folders', json={'name': 'f'}).status_code == 200
    assert client.post(f'/projects/{p.id}/folders', json={'name': 'G'}).status_code == 422


def test_archive_restore_and_bound_api_key_guards(client, db):
    p = project(db, 'A')
    assert client.patch(f'/projects/{p.id}', json={'archived': True}).json()['archived'] is True
    assert client.post(f'/projects/{p.id}/folders', json={'name': 'F'}).status_code == 422
    assert client.post('/api-keys/', json={'name': 'blocked', 'project_id': p.id}).status_code == 422
    assert client.patch(f'/projects/{p.id}', json={'archived': False}).json()['archived'] is False
    key = APIKey(user_id=ALICE, key_hash='test-binding', name='Audio integration', project_id=p.id)
    db.add(key); db.commit()
    for method in ('patch', 'delete'):
        response = client.patch(f'/projects/{p.id}', json={'archived': True}) if method == 'patch' else client.delete(f'/projects/{p.id}')
        assert response.status_code == 409 and 'Audio integration' in response.json()['detail']


def test_project_delete_requires_empty_and_never_deletes_jobs(client, db):
    p = project(db, 'A'); f = folder(db, p, 'F'); j = job(db, 'one', p, f)
    assert client.delete(f'/projects/{p.id}').status_code == 409
    assert db.get(Job, j.id) is not None
    other = project(db, 'B')
    assert client.patch(f'/jobs/{j.id}/location', json={'project_id': other.id}).status_code == 200
    p_id, f_id = p.id, f.id
    assert client.delete(f'/projects/{p_id}').status_code == 204
    db.expire_all()
    assert db.get(Project, p_id) is None and db.get(Folder, f_id) is None
    assert db.get(Job, j.id).project_id == other.id


def test_folder_delete_returns_jobs_to_root_without_data_loss(client, db):
    p = project(db, 'A'); f = folder(db, p, 'F'); j = job(db, 'one', p, f, tags=['tag'])
    j.minio_upload_path = 'uploads/one/source.pdf'
    j.minio_result_path = 'results/one/result.md'
    j.has_elasticsearch_result = True
    db.commit()
    assert client.delete(f'/folders/{f.id}').status_code == 204
    db.expire_all(); moved = db.get(Job, j.id)
    assert moved.project_id == p.id and moved.folder_id is None
    assert moved.tags == ['tag'] and moved.status == JobStatus.COMPLETED
    assert moved.minio_upload_path == 'uploads/one/source.pdf' and moved.minio_result_path == 'results/one/result.md'
    assert moved.has_elasticsearch_result
    summary = client.get('/projects?include=folders').json()['projects'][0]
    assert summary['root_job_count'] == 1 and summary['folders'] == []


def test_single_and_batch_moves_preserve_tags_children_and_update_statistics(client, db):
    a = project(db, 'A'); b = project(db, 'B'); f = folder(db, b, 'F')
    one = job(db, 'one', a, tags=['one']); two = job(db, 'two', a, status=JobStatus.PROCESSING)
    child = job(db, 'child', job_type='PAGE'); child.parent_job_id = one.id
    one.file_size_bytes = 1234; two.file_size_bytes = 500; db.commit()
    response = client.post('/jobs/move', json={'job_ids': [one.id, two.id, one.id], 'project_id': b.id, 'folder_id': f.id})
    assert response.status_code == 200 and response.json()['moved'] == 2
    db.expire_all()
    assert one.tags == ['one'] and child.project_id is None and child.parent_job_id == one.id
    assert one.project_id == b.id and one.folder_id == f.id
    summaries = {p['id']: p for p in client.get('/projects?include=folders').json()['projects']}
    assert summaries[a.id]['job_count'] == 0
    assert summaries[b.id]['job_count'] == 2 and summaries[b.id]['completed_count'] == 1
    assert summaries[b.id]['active_count'] == 1 and summaries[b.id]['total_bytes'] == 1734
    assert summaries[b.id]['folders'][0]['job_count'] == 2
    assert client.patch(f'/jobs/{one.id}/location', json={'project_id': a.id}).status_code == 200
    db.expire_all(); assert one.project_id == a.id and one.folder_id is None


def test_batch_failure_is_atomic_foreign_missing_child_and_invalid_destination(client, db):
    a = project(db, 'A'); b = project(db, 'B'); foreign = project(db, 'Other', user_id=BOB)
    f = folder(db, a, 'F'); own = job(db, 'own', a); theirs = job(db, 'foreign', foreign, user_id=BOB)
    child = job(db, 'child', job_type='PAGE')
    for bad, status in ((theirs.id, 404), ('missing', 404), (child.id, 422)):
        response = client.post('/jobs/move', json={'job_ids': [own.id, bad], 'project_id': b.id})
        assert response.status_code == status
        db.expire_all(); assert own.project_id == a.id
    assert client.post('/jobs/move', json={'job_ids': [own.id], 'project_id': b.id, 'folder_id': f.id}).status_code == 422
    assert client.post('/jobs/move', json={'job_ids': [own.id], 'project_id': foreign.id}).status_code == 404
    assert client.post('/jobs/move', json={'job_ids': [], 'project_id': b.id}).status_code == 422
    assert client.post('/jobs/move', json={'job_ids': ['x'] * 101, 'project_id': b.id}).status_code == 422
    client.patch(f'/projects/{b.id}', json={'archived': True})
    assert client.patch(f'/jobs/{own.id}/location', json={'project_id': b.id}).status_code == 422
    db.expire_all(); assert own.project_id == a.id


def test_statistics_cover_every_status_and_exclude_children_and_foreign_jobs(client, db):
    p = project(db, 'Statistics')
    empty = client.get('/projects').json()['projects'][0]
    assert all(empty[key] == 0 for key in ['job_count', 'completed_count', 'cancelled_count', 'active_count', 'failed_count', 'total_bytes'])
    for size, status in enumerate(JobStatus, 1):
        item = job(db, 'stat-' + status.value, p, status=status)
        item.file_size_bytes = size
    child = job(db, 'stat-page', p, job_type='PAGE'); child.file_size_bytes = 999
    foreign = job(db, 'stat-foreign', p, user_id=BOB); foreign.file_size_bytes = 999
    db.commit()
    result = client.get('/projects').json()['projects'][0]
    assert result['job_count'] == result['root_job_count'] == 5
    assert result['completed_count'] == result['failed_count'] == result['cancelled_count'] == 1
    assert result['active_count'] == 2 and result['total_bytes'] == 15


@pytest.mark.parametrize('missing', [False, True])
def test_maintenance_has_uniform_404_for_foreign_and_unknown(client, db, missing):
    p = project(db, 'Other', user_id=BOB); f = folder(db, p, 'F')
    p_id, f_id = ('unknown', 'unknown') if missing else (p.id, f.id)
    assert client.patch('/projects/' + p_id, json={'description': 'x'}).status_code == 404
    assert client.delete('/projects/' + p_id).status_code == 404
    assert client.post(f'/projects/{p_id}/folders', json={'name': 'F'}).status_code == 404
    assert client.patch('/folders/' + f_id, json={'name': 'F'}).status_code == 404
    assert client.delete('/folders/' + f_id).status_code == 404
