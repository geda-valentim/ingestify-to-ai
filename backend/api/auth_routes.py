from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import timedelta

from shared.database import get_db
from shared.models import User
from shared.schemas import UserCreate, UserLogin, UserResponse, Token
from shared.auth import (
    hash_password,
    authenticate_user,
    create_access_token,
    get_current_active_user,
)
from shared.config import get_settings

settings = get_settings()
router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """
    Register a new user

    ## Request Body:
    ```json
    {
      "email": "user@example.com",
      "username": "testuser",
      "password": "Test123"
    }
    ```

    ## Returns:
    User object with id, email, username, is_active, created_at

    ## Errors:
    - 400: Email or username already exists
    """
    # Check if email already exists
    existing_email = db.query(User).filter(User.email == user_data.email).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Check if username already exists
    existing_username = db.query(User).filter(User.username == user_data.username).first()
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )

    # Create new user
    hashed_pw = hash_password(user_data.password)
    new_user = User(
        email=user_data.email,
        username=user_data.username,
        hashed_password=hashed_pw,
        is_active=True,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


@router.post("/login", response_model=Token)
async def login(credentials: UserLogin, db: Session = Depends(get_db)):
    """
    Login with username/email and password

    ## Request Body:
    ```json
    {
      "username": "testuser",  // or email
      "password": "Test123"
    }
    ```

    ## Returns:
    ```json
    {
      "access_token": "eyJ...",
      "token_type": "bearer"
    }
    ```

    ## Usage:
    Use the access_token in subsequent requests:
    ```
    Authorization: Bearer eyJ...
    ```

    ## Errors:
    - 401: Invalid credentials
    """
    user = authenticate_user(db, credentials.username, credentials.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username/email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user account"
        )

    # Create access token
    access_token_expires = timedelta(minutes=settings.jwt_expiration_minutes)
    access_token = create_access_token(
        data={"sub": user.id},
        expires_delta=access_token_expires
    )

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    """
    Get information about the currently authenticated user

    ## Headers Required:
    ```
    Authorization: Bearer <token>
    ```
    or
    ```
    X-API-Key: <api_key>
    ```

    ## Returns:
    User object with id, email, username, is_active, created_at

    ## Errors:
    - 401: Not authenticated or invalid token/API key
    """
    return current_user
