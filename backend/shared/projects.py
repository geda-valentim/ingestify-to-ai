"""
Projects and folders: name normalisation and race-free get-or-add (spec 0003).

Every MAIN job belongs to exactly one project of its owner and, optionally, to
one folder of that project. Uploads may name both as free text, so the same
project must be found no matter how the name is typed: "Reunião Semanal" and
"  reuniao   SEMANAL " are one project.

Two strings per name:

- the **display name** (`clean_display_name`): NFC, trimmed, inner whitespace
  collapsed; case and accents kept. This is what the UI shows.
- the **key** (`name_key`): the identity used by the unique index. Accents are
  dropped *only over Latin letters* (Combining Diacritical Marks U+0300-U+036F
  after a Latin base), the result is recomposed to NFC and casefolded. No NFKD:
  "²" stays distinct from "2", ligatures stay, Japanese dakuten (U+3099/U+309A)
  are kept so "ハード" != "ハート", Hangul comes back composed, and Cyrillic keeps
  "й" != "и" and "ё" != "е".

The key is immutable once a project exists (renaming it would silently make
automated clients that send the old name create a new project).

The UI does not mirror this rule: it asks `GET /projects/resolve`.
"""

import logging
import re
import unicodedata
from typing import Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, InterfaceError, OperationalError
from sqlalchemy.orm import Session

from shared.config import get_settings

logger = logging.getLogger(__name__)

MAX_NAME_LENGTH = 100  # display name, in characters
MAX_KEY_LENGTH = 200   # key, after casefold ("ß" -> "ss" can grow it)

# Combining Diacritical Marks block. Written as escapes on purpose: a literal
# combining character in source code is invisible and easy to corrupt.
_COMBINING_LO, _COMBINING_HI = "̀", "ͯ"

_WHITESPACE = re.compile(r"\s+")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

DB_UNAVAILABLE_DETAIL = "Banco indisponível; tente de novo em instantes"


class InvalidNameError(ValueError):
    """The project/folder name cannot be accepted; the message is safe to show the caller."""


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def clean_display_name(raw: str) -> str:
    """NFC, trimmed, inner whitespace collapsed; case and accents preserved."""
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFC", raw or "")).strip()


def _is_latin_base(c: str) -> bool:
    o = ord(c)
    # Basic Latin .. Latin Extended-B, and Latin Extended Additional
    return 0x0041 <= o <= 0x024F or 0x1E00 <= o <= 0x1EFF


def name_key(raw: str) -> str:
    """The identity of a name: Latin accents dropped, NFC, casefolded."""
    s = unicodedata.normalize("NFD", clean_display_name(raw))
    out, base = [], ""
    for c in s:
        if _COMBINING_LO <= c <= _COMBINING_HI and _is_latin_base(base):
            continue  # accent over a Latin letter: ignored
        out.append(c)
        if not unicodedata.combining(c):
            base = c
    return unicodedata.normalize("NFC", "".join(out)).casefold()


def validate_name(raw: Optional[str], kind: str = "project") -> Tuple[str, str]:
    """
    Clean and validate a project or folder name.

    Returns:
        (display name, key)

    Raises:
        InvalidNameError: empty, too long, control characters, or '/' in a folder name.
    """
    label = "do projeto" if kind == "project" else "da pasta"
    display = clean_display_name(raw or "")
    if not display:
        raise InvalidNameError(f"Nome {label} vazio")
    if _CONTROL.search(display):
        raise InvalidNameError(f"Nome {label} contém caracteres de controle")
    if kind == "folder" and "/" in display:
        raise InvalidNameError("Nome da pasta não pode conter '/'")
    if len(display) > MAX_NAME_LENGTH:
        raise InvalidNameError(f"Nome muito longo (máximo {MAX_NAME_LENGTH} caracteres)")
    key = name_key(display)
    if len(key) > MAX_KEY_LENGTH:
        raise InvalidNameError(
            f"Nome muito longo depois de normalizado (máximo {MAX_KEY_LENGTH} caracteres)"
        )
    return display, key


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

def find_project(db: Session, user_id: str, key: str):
    from shared.models import Project

    return db.query(Project).filter(Project.user_id == user_id, Project.name_key == key).first()


def find_folder(db: Session, project_id: str, key: str):
    from shared.models import Folder

    return db.query(Folder).filter(Folder.project_id == project_id, Folder.name_key == key).first()


def _enforce_project_limit(db: Session, user_id: str) -> None:
    from shared.models import Project

    limit = get_settings().max_projects_per_user
    count = db.query(func.count(Project.id)).filter(Project.user_id == user_id).scalar() or 0
    if count >= limit:
        raise HTTPException(status_code=422, detail=f"Limite de {limit} projetos atingido")


def _enforce_folder_limit(db: Session, project_id: str) -> None:
    from shared.models import Folder

    limit = get_settings().max_folders_per_project
    count = db.query(func.count(Folder.id)).filter(Folder.project_id == project_id).scalar() or 0
    if count >= limit:
        raise HTTPException(status_code=422, detail=f"Limite de {limit} pastas atingido neste projeto")


# ---------------------------------------------------------------------------
# Get-or-add
# ---------------------------------------------------------------------------

def _get_or_create(db: Session, find, enforce_limit, build, what: str):
    """
    Shared loop of the two get-or-add functions.

    Why a full `rollback()` after an IntegrityError: in InnoDB under REPEATABLE
    READ, re-reading *in the same transaction* uses the old snapshot and would
    not see the row the concurrent request just committed. Ending the
    transaction makes the next read open a fresh one. A second consecutive
    failure only happens if the key collides without being equal (it should
    not, with utf8mb4_bin) and becomes a bounded 503, never None nor a loop.
    """
    if db.new or db.dirty:  # explicit check: an assert disappears under -O
        raise RuntimeError(f"get_or_create_{what} exige sessão sem escrita pendente")
    try:
        for _attempt in range(2):
            existing = find()
            if existing is not None:
                return existing, False
            enforce_limit()
            try:
                db.add(build())
                db.commit()
                created = find()
                if created is not None:
                    return created, True
            except IntegrityError:
                db.rollback()
    except (OperationalError, InterfaceError) as e:  # database down, connection lost, lock timeout
        db.rollback()
        logger.error(f"get_or_create_{what}: {e}")
        raise HTTPException(status_code=503, detail=DB_UNAVAILABLE_DETAIL)
    label = "o projeto" if what == "project" else "a pasta"
    raise HTTPException(status_code=503, detail=f"Não foi possível criar {label} agora; tente de novo")


def get_or_create_project(db: Session, user_id: str, raw: str, origin: str = "request"):
    """
    The user's project whose key matches `raw`, created if there is none.

    The session must have no pending writes: this commits.

    Returns:
        (Project, created)

    Raises:
        InvalidNameError: invalid name.
        HTTPException 422: project limit reached.
        HTTPException 503: database error.
    """
    from shared.models import Project

    display, key = validate_name(raw, "project")
    project, created = _get_or_create(
        db,
        find=lambda: find_project(db, user_id, key),
        enforce_limit=lambda: _enforce_project_limit(db, user_id),
        build=lambda: Project(user_id=user_id, name=display, name_key=key),
        what="project",
    )
    if created:
        logger.info(f"Project created: '{project.name}' ({project.id}) user={user_id} via={origin}")
    return project, created


def get_or_create_folder(db: Session, project, raw: str, origin: str = "request"):
    """
    The folder of `project` whose key matches `raw`, created if there is none.

    Returns:
        (Folder, created)
    """
    from shared.models import Folder

    display, key = validate_name(raw, "folder")
    project_id, user_id = project.id, project.user_id
    folder, created = _get_or_create(
        db,
        find=lambda: find_folder(db, project_id, key),
        enforce_limit=lambda: _enforce_folder_limit(db, project_id),
        build=lambda: Folder(project_id=project_id, user_id=user_id, name=display, name_key=key),
        what="folder",
    )
    if created:
        logger.info(
            f"Folder created: '{folder.name}' ({folder.id}) in project {project_id} "
            f"user={user_id} via={origin}"
        )
    return folder, created
