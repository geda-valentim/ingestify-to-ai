"""Race-free get-or-add of projects and folders (spec 0003 § 4.4)."""
import threading

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import sessionmaker

from shared import projects as projects_module
from shared.database import Base
from shared.models import Folder, Project, User
from shared.projects import get_or_create_folder, get_or_create_project

ALICE = "user-alice"
BOB = "user-bob"


def _fk_on(engine):
    @event.listens_for(engine, "connect")
    def _pragma(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


@pytest.fixture
def engine(tmp_path):
    # A file database (not :memory:) so each thread gets its own connection.
    eng = create_engine(
        f"sqlite:///{tmp_path / 'projects.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    _fk_on(eng)
    Base.metadata.create_all(bind=eng)
    with sessionmaker(bind=eng)() as s:
        s.add_all([
            User(id=ALICE, email="a@example.com", username="alice", hashed_password="x"),
            User(id=BOB, email="b@example.com", username="bob", hashed_password="x"),
        ])
        s.commit()
    return eng


@pytest.fixture
def Session(engine):
    return sessionmaker(bind=engine)


@pytest.fixture
def db(Session):
    with Session() as s:
        yield s


def test_creates_then_finds_by_equivalent_spelling(db):
    project, created = get_or_create_project(db, ALICE, "Reunião Semanal")
    assert created and project.name == "Reunião Semanal" and project.name_key == "reuniao semanal"

    again, created = get_or_create_project(db, ALICE, "  reuniao   SEMANAL ")
    assert not created and again.id == project.id
    assert db.query(Project).count() == 1


def test_projects_are_per_user(db):
    a, _ = get_or_create_project(db, ALICE, "Cliente X")
    b, created = get_or_create_project(db, BOB, "cliente x")
    assert created and a.id != b.id


def test_folders_are_per_project(db):
    p1, _ = get_or_create_project(db, ALICE, "P1")
    p2, _ = get_or_create_project(db, ALICE, "P2")
    f1, c1 = get_or_create_folder(db, p1, "Áudios")
    f1b, c1b = get_or_create_folder(db, p1, "audios")
    f2, c2 = get_or_create_folder(db, p2, "Áudios")
    assert c1 and not c1b and c2
    assert f1.id == f1b.id != f2.id
    assert f1.user_id == ALICE and f1.name == "Áudios"


def _race(Session, fn, n=8):
    barrier = threading.Barrier(n)
    results, errors = [], []

    def worker(i):
        with Session() as s:
            barrier.wait()
            try:
                obj, created = fn(s, i)
                results.append((obj.id, created))
            except Exception as e:  # pragma: no cover - reported below
                errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    return results


SPELLINGS = ["Projeto Novo", "projeto novo", "PROJETO NOVO", "  projeto   novo ",
             "Projéto Novo", "projeto Novo", "Projeto novo", "projÉto NOVO"]


def test_concurrent_equivalent_spellings_make_one_project(Session):
    results = _race(Session, lambda s, i: get_or_create_project(s, ALICE, SPELLINGS[i]))
    assert len({pid for pid, _ in results}) == 1
    assert sum(created for _, created in results) == 1
    with Session() as s:
        assert s.query(Project).count() == 1


def test_concurrent_equivalent_spellings_make_one_folder(Session, db):
    project, _ = get_or_create_project(db, ALICE, "P")
    project_id = project.id

    def fn(s, i):
        return get_or_create_folder(s, s.get(Project, project_id), SPELLINGS[i])

    results = _race(Session, fn)
    assert len({fid for fid, _ in results}) == 1
    with Session() as s:
        assert s.query(Folder).count() == 1


def test_integrity_error_rolls_back_and_rereads(db, Session, monkeypatch):
    """Another request commits the same key between our SELECT and INSERT."""
    real_commit = db.commit
    calls = {"n": 0}

    def commit():
        calls["n"] += 1
        if calls["n"] == 1:
            with Session() as other:
                other.add(Project(user_id=ALICE, name="Cliente X", name_key="cliente x"))
                other.commit()
            db.rollback()  # what a real duplicate-key failure leaves us to do
            raise IntegrityError("INSERT", {}, Exception("duplicate"))
        return real_commit()

    monkeypatch.setattr(db, "commit", commit)
    project, created = get_or_create_project(db, ALICE, "cliente X")
    assert not created and project.name == "Cliente X"


def test_two_integrity_errors_in_a_row_are_a_503(db, monkeypatch):
    def commit():
        db.rollback()
        raise IntegrityError("INSERT", {}, Exception("duplicate"))

    monkeypatch.setattr(db, "commit", commit)
    with pytest.raises(HTTPException) as exc:
        get_or_create_project(db, ALICE, "Fantasma")
    assert exc.value.status_code == 503


def test_operational_error_is_a_503(db, monkeypatch):
    def broken(*args, **kwargs):
        raise OperationalError("SELECT", {}, Exception("server has gone away"))

    monkeypatch.setattr(projects_module, "find_project", broken)
    with pytest.raises(HTTPException) as exc:
        get_or_create_project(db, ALICE, "X")
    assert exc.value.status_code == 503


def test_pending_write_is_refused(db):
    db.add(Project(user_id=ALICE, name="Pendente", name_key="pendente"))
    with pytest.raises(RuntimeError):
        get_or_create_project(db, ALICE, "Outro")


def test_project_limit_is_a_422(db, monkeypatch):
    monkeypatch.setattr(projects_module.get_settings(), "max_projects_per_user", 2)
    get_or_create_project(db, ALICE, "A")
    get_or_create_project(db, ALICE, "B")
    get_or_create_project(db, ALICE, "a")  # existing: no limit applies
    with pytest.raises(HTTPException) as exc:
        get_or_create_project(db, ALICE, "C")
    assert exc.value.status_code == 422
    assert exc.value.detail == "Limite de 2 projetos atingido"


def test_folder_limit_is_a_422(db, monkeypatch):
    monkeypatch.setattr(projects_module.get_settings(), "max_folders_per_project", 1)
    project, _ = get_or_create_project(db, ALICE, "P")
    get_or_create_folder(db, project, "F1")
    with pytest.raises(HTTPException) as exc:
        get_or_create_folder(db, project, "F2")
    assert exc.value.status_code == 422
