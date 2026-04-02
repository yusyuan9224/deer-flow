"""Authentication configuration for DeerFlow."""
import logging
import os

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_WEAK_SECRET_DEFAULT = "CHANGE_ME_IN_PRODUCTION"


class AuthConfig(BaseModel):
    """JWT and auth-related configuration."""

    jwt_secret: str = Field(
        default=_WEAK_SECRET_DEFAULT,
        description="Secret key for JWT signing. MUST be changed in production!",
    )
    token_expiry_days: int = Field(default=7, ge=1, le=30)
    users_db_path: str | None = Field(
        default=None,
        description="Path to users SQLite DB. Defaults to .deer-flow/users.db",
    )
    # OAuth provider configs (future)
    oauth_github_client_id: str | None = Field(default=None)
    oauth_github_client_secret: str | None = Field(default=None)


_auth_config: AuthConfig | None = None


def get_auth_config() -> AuthConfig:
    """Get the global AuthConfig instance."""
    global _auth_config
    if _auth_config is None:
        # Read JWT secret from environment variable
        jwt_secret = os.environ.get("AUTH_JWT_SECRET")
        if not jwt_secret:
            # Fail fast - insecure default must not be used
            raise ValueError(
                "AUTH_JWT_SECRET environment variable must be set. "
                "Generate a secure secret with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
            )
        _auth_config = AuthConfig(jwt_secret=jwt_secret)
    return _auth_config


def set_auth_config(config: AuthConfig) -> None:
    """Set the global AuthConfig instance."""
    global _auth_config
    _auth_config = config
