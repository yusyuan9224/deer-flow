"""Authentication configuration for DeerFlow."""
import logging
import os
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

load_dotenv()

logger = logging.getLogger(__name__)


class AuthConfig(BaseModel):
    """JWT and auth-related configuration. Parsed once at startup."""

    jwt_secret: str = Field(
        ...,
        description="Secret key for JWT signing. MUST be set via AUTH_JWT_SECRET.",
    )
    token_expiry_days: int = Field(default=7, ge=1, le=30)
    env: Literal["development", "production"] = Field(default="production")
    cookie_secure: bool = Field(default=True)
    users_db_path: str | None = Field(
        default=None,
        description="Path to users SQLite DB. Defaults to .deer-flow/users.db",
    )
    oauth_github_client_id: str | None = Field(default=None)
    oauth_github_client_secret: str | None = Field(default=None)

    @field_validator("cookie_secure")
    @classmethod
    def enforce_secure_in_prod(cls, v: bool, info) -> bool:
        if info.data.get("env") == "production" and not v:
            raise ValueError("cookie_secure must be True in production")
        return v


_auth_config: AuthConfig | None = None


def _parse_env() -> Literal["development", "production"]:
    raw = os.environ.get("ENV", "production").lower()
    return "development" if raw in ("development", "dev", "local") else "production"


def get_auth_config() -> AuthConfig:
    """Get the global AuthConfig instance. Parses from env on first call."""
    global _auth_config
    if _auth_config is None:
        jwt_secret = os.environ.get("AUTH_JWT_SECRET")
        if not jwt_secret:
            raise ValueError(
                "AUTH_JWT_SECRET environment variable must be set. "
                'Generate a secure secret with: python -c "import secrets; print(secrets.token_urlsafe(32))"'
            )
        env = _parse_env()
        cookie_secure = os.environ.get("AUTH_COOKIE_SECURE", "true").lower() != "false"
        _auth_config = AuthConfig(
            jwt_secret=jwt_secret,
            env=env,
            cookie_secure=cookie_secure,
        )
        if not cookie_secure:
            logger.warning("AUTH_COOKIE_SECURE=false — cookies sent without Secure flag")
    return _auth_config


def set_auth_config(config: AuthConfig) -> None:
    """Set the global AuthConfig instance (for testing)."""
    global _auth_config
    _auth_config = config
