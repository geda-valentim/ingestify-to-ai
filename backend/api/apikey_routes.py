from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from uuid import UUID

from api.deps import owned_project_or_404
from api.iam_deps import Scope, authorized, require, visible
from shared.database import get_db
from shared.models import User, APIKey, Project
from shared.projects import InvalidNameError, get_or_create_project
from shared.schemas import APIKeyCreate, APIKeyResponse, APIKeyInfo, APIKeyProjectUpdate, ProjectRef
from shared.auth import (
    generate_api_key,
    hash_api_key,
    get_current_active_user,
)

router = APIRouter()


def _project_ref(project: Optional[Project]) -> Optional[ProjectRef]:
    return ProjectRef(id=project.id, name=project.name) if project is not None else None


def _bound_project(db: Session, key: APIKey, projects: Optional[Dict[str, Project]] = None) -> Optional[Project]:
    """The key's project if the binding is valid (exists, same owner); else None."""
    if not key.project_id:
        return None
    project = projects.get(key.project_id) if projects is not None else db.get(Project, key.project_id)
    if project is None or project.user_id != key.user_id:
        return None
    return project


def _key_info(key: APIKey, project: Optional[Project]) -> APIKeyInfo:
    return APIKeyInfo(
        id=UUID(key.id),
        name=key.name,
        last_used_at=key.last_used_at,
        expires_at=key.expires_at,
        is_active=key.is_active,
        created_at=key.created_at,
        project=_project_ref(project),
    )


@router.post("/", summary="Criar API key", response_model=APIKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    key_data: APIKeyCreate,
    current_user: User = Depends(require("api_keys.manage")),
    db: Session = Depends(get_db)
):
    """
    Create a new API key for the authenticated user

    ## Request Body:
    ```json
    {
      "name": "Production Server",
      "expires_in_days": 30,  // optional, null = never expires
      "project": "Transcrições automáticas"  // optional: name (get-or-add) or "project_id"
    }
    ```

    Uploads made with a key bound to a project, that do not name a project,
    go to that project. A request that also sends a JWT is a JWT request and
    does not use the binding.

    ## Returns:
    ```json
    {
      "id": "uuid",
      "name": "Production Server",
      "api_key": "doc2md_sk_...",  // ONLY SHOWN ONCE!
      "expires_at": "2025-11-01T00:00:00",
      "created_at": "2025-10-02T00:00:00"
    }
    ```

    ## Important:
    - The `api_key` is shown ONLY ONCE during creation
    - Save it immediately - you won't be able to see it again
    - Use it in requests with header: `X-API-Key: doc2md_sk_...`

    ## Errors:
    - 401: Not authenticated
    """
    # Bound project, resolved before anything else is written (get-or-add commits)
    project = None
    project_name = (key_data.project or "").strip() or None
    project_id = (key_data.project_id or "").strip() or None
    if project_name and project_id:
        raise HTTPException(status_code=422, detail="Envie 'project' ou 'project_id', não os dois")
    if project_id:
        project = owned_project_or_404(db, project_id, current_user)
    elif project_name:
        try:
            project, _created = get_or_create_project(db, current_user.id, project_name, origin="api_key_create")
        except InvalidNameError as e:
            raise HTTPException(status_code=422, detail=str(e))

    # Generate API key
    plain_key = generate_api_key()
    key_hash = hash_api_key(plain_key)

    # Calculate expiration
    expires_at = None
    if key_data.expires_in_days:
        expires_at = datetime.utcnow() + timedelta(days=key_data.expires_in_days)

    # Create API key record
    new_key = APIKey(
        user_id=current_user.id,
        key_hash=key_hash,
        name=key_data.name,
        expires_at=expires_at,
        is_active=True,
        project_id=project.id if project is not None else None,
    )

    db.add(new_key)
    db.commit()
    db.refresh(new_key)

    # Return response with plain key (only time it's visible)
    return APIKeyResponse(
        id=UUID(new_key.id),
        name=new_key.name,
        api_key=plain_key,  # Plain key - only shown once!
        expires_at=new_key.expires_at,
        created_at=new_key.created_at,
        project=_project_ref(_bound_project(db, new_key)),
    )


@router.get("/", summary="Listar API keys", response_model=List[APIKeyInfo])
async def list_api_keys(
    scope: Scope = Depends(visible(APIKey, "api_keys.read")),
    db: Session = Depends(get_db)
):
    """
    List all API keys for the authenticated user

    ## Returns:
    Array of API key info (without the actual key):
    ```json
    [
      {
        "id": "uuid",
        "name": "Production Server",
        "last_used_at": "2025-10-02T12:00:00",
        "expires_at": "2025-11-01T00:00:00",
        "is_active": true,
        "created_at": "2025-10-02T00:00:00"
      }
    ]
    ```

    ## Note:
    The actual API key is NOT returned (for security).
    It's only shown once during creation.

    ## Errors:
    - 401: Not authenticated
    """
    keys = db.query(APIKey).filter(scope.predicate).all()
    projects = {p.id: p for p in db.query(Project).filter(scope.of(Project))}

    return [_key_info(key, _bound_project(db, key, projects)) for key in keys]


@router.patch("/{key_id}", summary="Vincular API key a um projeto", response_model=APIKeyInfo)
async def update_api_key_project(
    key_id: UUID,
    body: APIKeyProjectUpdate,
    key: APIKey = Depends(authorized(APIKey, "api_keys.manage")),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Bind the key to a project, or unbind it (`{"project_id": null}`)

    Uploads made with this key that name no project go to the bound project.
    A key without a project must send `project` on every upload (422 otherwise).
    Re-binding changes where new uploads go; a file already processed in another
    project is processed again in the new one.

    ## Errors:
    - 404: API key or project not found (or not yours)
    """
    project_id = (body.project_id or "").strip() or None
    project = owned_project_or_404(db, project_id, current_user) if project_id else None
    key.project_id = project.id if project is not None else None
    db.commit()
    db.refresh(key)
    return _key_info(key, project)


@router.delete("/{key_id}", summary="Revogar API key", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: UUID,
    key: APIKey = Depends(authorized(APIKey, "api_keys.manage")),
    db: Session = Depends(get_db)
):
    """
    Revoke (delete) an API key

    ## Path Parameters:
    - `key_id`: UUID of the API key to revoke

    ## Returns:
    204 No Content on success

    ## Errors:
    - 401: Not authenticated
    - 404: API key not found or doesn't belong to user
    """
    db.delete(key)
    db.commit()

    return None
