from fastapi import APIRouter, Depends, HTTPException, status, Form, Request
from sqlalchemy import func, or_
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
from shared import rate_limit

settings = get_settings()
router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, request: Request, db: Session = Depends(get_db)):
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
    - 429: Too many registrations from this IP
    """
    rate_limit.hit("register:ip", rate_limit.client_ip(request), settings.register_limit_per_hour, 3600)

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


def _lockout_identity(db: Session, login: str) -> str:
    """
    Stable key for the per-account failure counter.

    Login accepts a username or an email; both map to the same user ID so an
    attacker cannot get two failure budgets by alternating them. Unknown names
    fall back to the normalized string (still rate limited, no enumeration).
    """
    normalized = rate_limit.normalize_identity(login)
    user = db.query(User).filter(
        or_(func.lower(User.username) == normalized, func.lower(User.email) == normalized)
    ).first()
    return f"user:{user.id}" if user else f"name:{normalized}"


@router.post("/login", response_model=Token)
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    Login with username/email and password (OAuth2 compatible)

    ## Request Body (form-urlencoded):
    - username: testuser (or email)
    - password: Test123

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
    - 429: Too many attempts (per IP, or too many failures for this account)
    """
    account = _lockout_identity(db, username)
    rate_limit.hit("login:ip", rate_limit.client_ip(request), settings.rate_limit_per_minute, 60)
    rate_limit.check_failures("login:failed", account, settings.login_max_failed_attempts)

    user = authenticate_user(db, username, password)

    if not user:
        rate_limit.record_failure("login:failed", account, settings.login_lockout_seconds)
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

    rate_limit.reset("login:failed", account)

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
