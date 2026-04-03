"""Authentication configuration for DeerFlow."""

import os

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()


class AuthConfig(BaseModel):
    """JWT and auth-related configuration. Parsed once at startup."""

    jwt_secret: str = Field(
        ...,
        description="Secret key for JWT signing. MUST be set via AUTH_JWT_SECRET.",
    )
    token_expiry_days: int = Field(default=7, ge=1, le=30)
    users_db_path: str | None = Field(
        default=None,
        description="Path to users SQLite DB. Defaults to .deer-flow/users.db",
    )
    oauth_github_client_id: str | None = Field(default=None)
    oauth_github_client_secret: str | None = Field(default=None)


_auth_config: AuthConfig | None = None


def get_auth_config() -> AuthConfig:
    """Get the global AuthConfig instance. Parses from env on first call."""
    global _auth_config
    if _auth_config is None:
        jwt_secret = os.environ.get("AUTH_JWT_SECRET")
        if not jwt_secret:
            raise ValueError('AUTH_JWT_SECRET environment variable must be set. Generate a secure secret with: python -c "import secrets; print(secrets.token_urlsafe(32))"')
        _auth_config = AuthConfig(jwt_secret=jwt_secret)
    return _auth_config


def set_auth_config(config: AuthConfig) -> None:
    """Set the global AuthConfig instance (for testing)."""
    global _auth_config
    _auth_config = config
