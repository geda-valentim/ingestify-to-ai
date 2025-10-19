from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from sqlalchemy.orm import Session
import secrets
import hashlib

from shared.config import get_settings
from shared.database import get_db
from shared.models import User, APIKey

settings = get_settings()

# Password hashing context (bcrypt)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Security schemes for Swagger UI
bearer_scheme = HTTPBearer(auto_error=False)
api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)


# ============================================
# Password Hashing
# ============================================

def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)


# ============================================
# JWT Token Functions
# ============================================

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create JWT access token

    Args:
        data: Dict with user data (usually {"sub": user.id})
        expires_delta: Optional expiration time delta

    Returns:
        JWT token string
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expiration_minutes)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    return encoded_jwt


def verify_token(token: str) -> Optional[str]:
    """
    Verify JWT token and extract user_id

    Args:
        token: JWT token string

    Returns:
        user_id if valid, None otherwise
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
        return user_id
    except JWTError:
        return None


# ============================================
# API Key Functions
# ============================================

def generate_api_key() -> str:
    """
    Generate a new API key

    Returns:
        API key string in format: doc2md_sk_<random>
    """
    random_part = secrets.token_urlsafe(32)
    return f"doc2md_sk_{random_part}"


def hash_api_key(api_key: str) -> str:
    """
    Hash an API key using SHA-256

    Args:
        api_key: Plain API key string

    Returns:
        Hashed API key
    """
    return hashlib.sha256(api_key.encode()).hexdigest()


def verify_api_key(plain_key: str, hashed_key: str) -> bool:
    """
    Verify an API key against its hash

    Args:
        plain_key: Plain API key
        hashed_key: Hashed API key from database

    Returns:
        True if matches, False otherwise
    """
    return hash_api_key(plain_key) == hashed_key


# ============================================
# User Authentication
# ============================================

def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    """
    Authenticate user with username and password

    Args:
        db: Database session
        username: Username or email
        password: Plain password

    Returns:
        User object if authenticated, None otherwise
    """
    # Try to find by username first
    user = db.query(User).filter(User.username == username).first()

    # If not found, try email
    if not user:
        user = db.query(User).filter(User.email == username).first()

    if not user:
        return None

    if not verify_password(password, user.hashed_password):
        return None

    return user


def get_user_by_api_key(db: Session, api_key: str) -> Optional[User]:
    """
    Get user by API key

    Args:
        db: Database session
        api_key: Plain API key

    Returns:
        User object if key is valid, None otherwise
    """
    key_hash = hash_api_key(api_key)

    # Find active API key
    api_key_obj = db.query(APIKey).filter(
        APIKey.key_hash == key_hash,
        APIKey.is_active == True
    ).first()

    if not api_key_obj:
        return None

    # Check if key has expired
    if api_key_obj.expires_at and api_key_obj.expires_at < datetime.utcnow():
        return None

    # Update last_used_at
    api_key_obj.last_used_at = datetime.utcnow()
    db.commit()

    return api_key_obj.user


# ============================================
# FastAPI Dependencies
# ============================================

async def get_current_user(
    bearer_token: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    api_key: Optional[str] = Depends(api_key_scheme),
    db: Session = Depends(get_db)
) -> User:
    """
    Get current authenticated user from JWT token or API key

    This dependency tries authentication in this order:
    1. Authorization header with Bearer token (JWT)
    2. X-API-Key header with API key

    Args:
        bearer_token: Bearer token from Authorization header
        api_key: API key from X-API-Key header
        db: Database session

    Returns:
        User object

    Raises:
        HTTPException 401: If authentication fails
    """
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Try JWT first
    if bearer_token:
        token = bearer_token.credentials
        user_id = verify_token(token)

        if user_id is None:
            raise credentials_exception

        user = db.query(User).filter(User.id == user_id).first()

        if user is None:
            raise credentials_exception

        return user

    # Try API Key
    if api_key:
        user = get_user_by_api_key(db, api_key)

        if user is None:
            raise credentials_exception

        return user

    # No auth provided
    raise credentials_exception


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Get current active user (checks is_active flag)

    Args:
        current_user: User from get_current_user dependency

    Returns:
        User object

    Raises:
        HTTPException 400: If user is inactive
    """
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    return current_user


async def get_optional_user(
    bearer_token: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    api_key: Optional[str] = Depends(api_key_scheme),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Get current user if authenticated, None otherwise.
    Useful for endpoints that can work with or without authentication.

    Args:
        bearer_token: Bearer token from Authorization header
        api_key: API key from X-API-Key header
        db: Database session

    Returns:
        User object or None
    """
    try:
        return await get_current_user(bearer_token, api_key, db)
    except HTTPException:
        return None
