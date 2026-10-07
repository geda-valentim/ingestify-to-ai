"""
Dependências compartilhadas da camada de API (autorização de jobs e páginas).

## Regra de segurança

A autorização **sempre** é derivada do MySQL, que é a fonte da verdade.
O Redis é apenas um cache com TTL (`result_ttl_seconds`) e nunca pode ser
usado para decidir sozinho que um usuário tem acesso a um recurso.

O acesso só é concedido quando existe uma correspondência **positiva e
explícita** entre o dono do job e o usuário autenticado. Ausência de dado
(`Job.user_id` NULL por causa do `ondelete="SET NULL"`, status expirado no
Redis, job inexistente, etc.) **nunca** autoriza.

## Por que 404 e não 403

Negar com 403 revela que o job existe e pertence a outra pessoa. Todas as
negações usam 404 com a mesma mensagem de "não encontrado", de forma que um
usuário não consegue enumerar recursos de terceiros.

## Jobs filhos (SPLIT / PAGE / MERGE)

Jobs filhos **não** são persistidos como linhas em `jobs` no MySQL (os workers
só gravam registros em `pages`; ver `workers/tasks.py`). Por isso a resolução
de dono de um job filho é feita assim, em ordem:

1. Linha própria em `jobs` (caso exista, ex.: jobs MAIN) — sobe pela cadeia
   `parent_job_id` enquanto `user_id` for NULL.
2. `pages.page_job_id` -> `pages.job_id` -> job MAIN no MySQL (jobs PAGE).
3. `parent_job_id` do status no Redis, usado **apenas** para descobrir o
   vínculo pai/filho; o dono continua vindo do MySQL (jobs SPLIT/MERGE).
4. Último recurso, apenas quando o MySQL não conhece o job de forma alguma
   (falha na gravação em MySQL durante o upload): dono registrado no Redis,
   e somente com igualdade explícita `owner == user.id`.
"""

import logging
from typing import Optional

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from shared.auth import get_current_active_user
from shared.database import get_db
from shared.iam import ownership
from shared.models import APIKey, Folder, Job, Page, Project, User

logger = logging.getLogger(__name__)

# Mensagem única para "não existe" e "não é seu": evita enumeração de recursos.
JOB_NOT_FOUND_DETAIL = "Job não encontrado"
PROJECT_NOT_FOUND_DETAIL = "Projeto não encontrado"
FOLDER_NOT_FOUND_DETAIL = "Pasta não encontrada"
API_KEY_NOT_FOUND_DETAIL = "API key not found"


class LocationError(HTTPException):
    """
    HTTPException de projeto/pasta com um código legível por máquina.

    O `error_code` é usado pelas rotas de `/images/*`, cujo envelope de erro é
    `{"detail": {"error_code", "message", "job_id"}}`.
    """

    def __init__(self, status_code: int, error_code: str, detail: str):
        super().__init__(status_code=status_code, detail=detail)
        self.error_code = error_code

# Profundidade máxima ao subir a hierarquia MAIN -> SPLIT/PAGE/MERGE.
MAX_PARENT_CHAIN_DEPTH = ownership.MAX_PARENT_CHAIN_DEPTH


# ============================================
# Helpers internos
# ============================================
# A resolução de dono vive em `shared.iam.ownership` (spec 0014), que também é
# usada por `shared.iam.decide`. Os nomes abaixo continuam aqui para que a
# camada de API (e os testes, via monkeypatch) tenham um único ponto de troca.

_resolve_owner_id = ownership.resolve_owner_id


def _redis_job_status(job_id: str) -> Optional[dict]:
    """Lê o status do Redis de forma tolerante a falhas (nunca autoriza sozinho)."""
    return ownership.redis_job_status(job_id)


def _redis_owner_matches(job_id: str, user_id: str) -> bool:
    """Fallback usado só quando o MySQL não conhece o job (ver `shared.iam.ownership`)."""
    return ownership.redis_owner_matches(job_id, user_id)


def _find_parent_job_in_db(db: Session, job_id: str) -> Optional[Job]:
    """O job MAIN (no MySQL) de um job filho sem linha própria."""
    return ownership.find_parent_job_in_db(db, job_id, lambda j: _redis_job_status(j))


def job_access(db: Session, job_id: str, user_id: Optional[str]) -> ownership.JobAccess:
    """`ownership.job_access` com os fallbacks do Redis resolvidos neste módulo."""
    return ownership.job_access(
        db,
        job_id,
        user_id,
        redis_status=lambda j: _redis_job_status(j),
        owner_matches=lambda j, u: _redis_owner_matches(j, u),
    )


def resolve_owned_job(db: Session, job_id: str, user: User) -> Optional[Job]:
    """
    Resolve e autoriza o acesso de `user` ao job `job_id`.

    Returns:
        A linha `Job` do próprio `job_id` quando ela existe; a linha do job
        MAIN que autorizou o acesso quando `job_id` é um job filho (que não é
        persistido no MySQL); ou `None` quando o acesso foi autorizado pelo
        fallback do Redis e não existe nenhuma linha correspondente no MySQL.
        Endpoints que precisam do registro exato do `job_id` devem checar
        `job is not None and job.id == job_id`.

    Raises:
        HTTPException 404: job inexistente, órfão ou de outro usuário.
    """
    access = job_access(db, job_id, user.id)
    if not access.allowed:
        raise HTTPException(status_code=404, detail=JOB_NOT_FOUND_DETAIL)
    return access.job


# ============================================
# Dependências FastAPI
# ============================================

async def get_owned_job(
    job_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Optional[Job]:
    """
    Dependência de autorização para qualquer endpoint que opere sobre um job.

    Usa o MySQL como fonte da verdade e retorna 404 tanto para job inexistente
    quanto para job de outro usuário (evita vazar a existência do recurso).

    Ver `resolve_owned_job` para o significado do valor retornado.
    """
    return resolve_owned_job(db, job_id, current_user)


async def get_owned_page_or_none(
    job_id: str,
    page_number: int,
    owned_job: Optional[Job] = Depends(get_owned_job),
    db: Session = Depends(get_db),
) -> Optional[Page]:
    """
    Autoriza o job (via `get_owned_job`) e devolve a página pedida, se existir.

    Retorna `None` — em vez de 404 — quando a página não está no MySQL, porque
    os endpoints de página ainda possuem fallback para o Redis. A autorização
    já foi feita pela dependência `get_owned_job`.
    """
    return (
        db.query(Page)
        .filter(Page.job_id == job_id, Page.page_number == page_number)
        .first()
    )


# ============================================
# Projetos e pastas (spec 0004)
# ============================================

def owned_project_or_404(db: Session, project_id: Optional[str], user: User) -> Project:
    """O projeto, se for do usuário; 404 igual para inexistente e alheio."""
    project = db.get(Project, str(project_id)) if project_id else None
    if not ownership.owns(project, user.id):
        raise LocationError(404, "PROJECT_NOT_FOUND", PROJECT_NOT_FOUND_DETAIL)
    return project


def owned_folder_or_404(db: Session, folder_id: Optional[str], user: User) -> Folder:
    """A pasta, se for do usuário; 404 igual para inexistente e alheia."""
    folder = db.get(Folder, str(folder_id)) if folder_id else None
    if not ownership.owns(folder, user.id):
        raise LocationError(404, "FOLDER_NOT_FOUND", FOLDER_NOT_FOUND_DETAIL)
    return folder


async def get_owned_project(
    project_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Project:
    """Dependência de autorização para rotas `/projects/{project_id}/...`."""
    return owned_project_or_404(db, project_id, current_user)


async def get_owned_folder(
    folder_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Folder:
    """Dependência de autorização para rotas `/folders/{folder_id}/...`."""
    return owned_folder_or_404(db, folder_id, current_user)


# ============================================
# API keys
# ============================================

def owned_api_key_or_404(db: Session, key_id, user: User) -> APIKey:
    """A key, se for do usuário; 404 igual para inexistente e alheia."""
    key = db.get(APIKey, str(key_id)) if key_id else None
    if not ownership.owns(key, user.id):
        raise HTTPException(status_code=404, detail=API_KEY_NOT_FOUND_DETAIL)
    return key
