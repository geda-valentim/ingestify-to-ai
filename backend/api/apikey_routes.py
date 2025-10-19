from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List
from uuid import UUID

from shared.database import get_db
from shared.models import User, APIKey
from shared.schemas import APIKeyCreate, APIKeyResponse, APIKeyInfo
from shared.auth import (
    generate_api_key,
    hash_api_key,
    get_current_active_user,
)

router = APIRouter()


@router.post("/", response_model=APIKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    key_data: APIKeyCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Create a new API key for the authenticated user

    ## Request Body:
    ```json
    {
      "name": "Production Server",
      "expires_in_days": 30  // optional, null = never expires
    }
    ```

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
    )


@router.get("/", response_model=List[APIKeyInfo])
async def list_api_keys(
    current_user: User = Depends(get_current_active_user),
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
    keys = db.query(APIKey).filter(APIKey.user_id == current_user.id).all()

    return [
        APIKeyInfo(
            id=UUID(key.id),
            name=key.name,
            last_used_at=key.last_used_at,
            expires_at=key.expires_at,
            is_active=key.is_active,
            created_at=key.created_at,
        )
        for key in keys
    ]


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: UUID,
    current_user: User = Depends(get_current_active_user),
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
    key = db.query(APIKey).filter(
        APIKey.id == str(key_id),
        APIKey.user_id == current_user.id
    ).first()

    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    db.delete(key)
    db.commit()

    return None
