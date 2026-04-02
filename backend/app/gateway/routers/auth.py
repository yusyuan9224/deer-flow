"""Authentication endpoints."""
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr

from app.core.auth import (
    TokenPayload,
    UserResponse,
    create_access_token,
    decode_token,
    hash_password,
)
from app.core.auth.local_provider import LocalAuthProvider
from app.core.auth.models import User
from app.core.auth.providers import ProviderFactory
from app.core.auth.sqlite_user_repository import SQLiteUserRepository

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Initialize LocalAuthProvider with SQLite repository
_repository = SQLiteUserRepository()
_local_provider = LocalAuthProvider(repository=_repository)
ProviderFactory.register("local", lambda: _local_provider)


# ── Request/Response Models ──────────────────────────────────────────────


class TokenResponse(BaseModel):
    """Response model for token endpoint."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RegisterRequest(BaseModel):
    """Request model for user registration."""

    email: EmailStr
    password: str


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str


# ── Dependencies ──────────────────────────────────────────────────────────


async def get_current_user(access_token: str | None = Cookie(None)) -> User:
    """FastAPI dependency to get the current authenticated user.

    Raises HTTPException 401 if not authenticated.
    """
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    payload = decode_token(access_token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user = await _local_provider.get_user(payload.sub)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user


async def get_optional_user(access_token: str | None = Cookie(None)) -> User | None:
    """Optional user dependency - returns None if not authenticated."""
    if not access_token:
        return None

    try:
        return await get_current_user(access_token)
    except HTTPException:
        return None


# ── Endpoints ─────────────────────────────────────────────────────────────


@router.post("/login/local", response_model=TokenResponse)
async def login_local(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    """Local email/password login.

    Authenticates user with username (email) and password,
    returns JWT token in response body and HttpOnly cookie.
    """
    user = await _local_provider.authenticate(
        {"email": form_data.username, "password": form_data.password}
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    token = create_access_token(str(user.id))

    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=7 * 24 * 3600,
    )

    return TokenResponse(access_token=token, expires_in=7 * 24 * 3600)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest):
    """Register a new local user account."""
    # Fast path: check if email exists first (avoids expensive hash computation on conflict)
    existing = await _local_provider.get_user_by_email(body.email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Insert is atomic at the DB layer; IntegrityError handles the race
    try:
        user = await _local_provider.create_user(email=body.email, password=body.password)
    except ValueError as e:
        # Raised by repo when UNIQUE constraint is violated (race between pre-check and insert)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return UserResponse(id=str(user.id), email=user.email, system_role=user.system_role)


@router.post("/logout", response_model=MessageResponse)
async def logout(response: Response):
    """Logout current user by clearing the cookie."""
    response.delete_cookie(key="access_token")
    return MessageResponse(message="Successfully logged out")


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    """Get current authenticated user info."""
    return UserResponse(id=str(user.id), email=user.email, system_role=user.system_role)


# ── OAuth Endpoints (Future/Placeholder) ─────────────────────────────────


@router.get("/oauth/{provider}")
async def oauth_login(provider: str):
    """Initiate OAuth login flow.

    Redirects to the OAuth provider's authorization URL.
    Currently a placeholder - requires OAuth provider implementation.
    """
    if provider not in ["github", "google"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported OAuth provider: {provider}",
        )

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="OAuth login not yet implemented",
    )


@router.get("/callback/{provider}")
async def oauth_callback(provider: str, code: str, state: str):
    """OAuth callback endpoint.

    Handles the OAuth provider's callback after user authorization.
    Currently a placeholder.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="OAuth callback not yet implemented",
    )
