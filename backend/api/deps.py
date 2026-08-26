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
from shared.models import Job, Page, User

logger = logging.getLogger(__name__)

# Mensagem única para "não existe" e "não é seu": evita enumeração de recursos.
JOB_NOT_FOUND_DETAIL = "Job não encontrado"

# Profundidade máxima ao subir a hierarquia MAIN -> SPLIT/PAGE/MERGE.
MAX_PARENT_CHAIN_DEPTH = 5


# ============================================
# Helpers internos
# ============================================

def _resolve_owner_id(db: Session, job: Optional[Job]) -> Optional[str]:
    """
    Descobre o dono autoritativo de um job no MySQL.

    Sobe pela cadeia `parent_job_id` enquanto o `user_id` for NULL.

    Returns:
        ID do usuário dono, ou None se não for possível determinar
        (job órfão, cadeia quebrada ou ciclo).
    """
    current = job
    visited = set()
    depth = 0

    while current is not None and depth < MAX_PARENT_CHAIN_DEPTH:
        owner_id = current.user_id
        if owner_id is not None:
            return owner_id

        parent_job_id = current.parent_job_id
        if not parent_job_id or parent_job_id in visited:
            return None

        visited.add(current.id)
        current = db.query(Job).filter(Job.id == parent_job_id).first()
        depth += 1

    return None


def _redis_job_status(job_id: str) -> Optional[dict]:
    """Lê o status do Redis de forma tolerante a falhas (nunca autoriza sozinho)."""
    try:
        from shared.redis_client import get_redis_client

        return get_redis_client().get_job_status(job_id)
    except Exception as e:  # pragma: no cover - Redis indisponível
        logger.warning(f"Não foi possível consultar status do job {job_id} no Redis: {e}")
        return None


def _find_parent_job_in_db(db: Session, job_id: str) -> Optional[Job]:
    """
    Encontra o job MAIN (no MySQL) de um job filho que não possui linha própria.

    O vínculo pai/filho pode vir da tabela `pages` (jobs PAGE) ou do status no
    Redis (jobs SPLIT/MERGE). Em ambos os casos o **dono** vem do MySQL.
    """
    page = db.query(Page).filter(Page.page_job_id == job_id).first()
    if page is not None and page.job_id:
        parent = db.query(Job).filter(Job.id == page.job_id).first()
        if parent is not None:
            return parent

    status_data = _redis_job_status(job_id)
    parent_job_id = status_data.get("parent_job_id") if status_data else None
    if parent_job_id:
        return db.query(Job).filter(Job.id == parent_job_id).first()

    return None


def _redis_owner_matches(job_id: str, user_id: str) -> bool:
    """
    Fallback usado só quando o MySQL não conhece o job.

    Exige igualdade explícita entre o dono registrado no Redis e o usuário
    autenticado — a ausência do registro nunca autoriza.
    """
    try:
        from shared.redis_client import get_redis_client

        owner_id = get_redis_client().get_job_owner(job_id)
    except Exception as e:  # pragma: no cover - Redis indisponível
        logger.warning(f"Não foi possível consultar o dono do job {job_id} no Redis: {e}")
        return False

    return bool(owner_id) and bool(user_id) and owner_id == user_id


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
    not_found = HTTPException(status_code=404, detail=JOB_NOT_FOUND_DETAIL)

    db_job = db.query(Job).filter(Job.id == job_id).first()

    if db_job is not None:
        owner_id = _resolve_owner_id(db, db_job)
        # `owner_id is None` (job órfão) NUNCA autoriza.
        if owner_id is not None and owner_id == user.id:
            return db_job
        logger.warning(
            f"Acesso negado ao job {job_id} para o usuário {user.id} "
            f"(dono resolvido: {owner_id})"
        )
        raise not_found

    # Job filho: sem linha própria no MySQL, o dono vem do job MAIN.
    parent_job = _find_parent_job_in_db(db, job_id)
    if parent_job is not None:
        owner_id = _resolve_owner_id(db, parent_job)
        if owner_id is not None and owner_id == user.id:
            return parent_job
        logger.warning(
            f"Acesso negado ao job filho {job_id} para o usuário {user.id} "
            f"(dono do job pai {parent_job.id}: {owner_id})"
        )
        raise not_found

    # MySQL não conhece o job: só um match positivo no Redis autoriza.
    if _redis_owner_matches(job_id, user.id):
        logger.info(
            f"Job {job_id} não existe no MySQL; acesso autorizado pelo dono registrado no Redis"
        )
        # Autorizado, porém sem nenhuma linha correspondente no MySQL.
        return None

    raise not_found


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
