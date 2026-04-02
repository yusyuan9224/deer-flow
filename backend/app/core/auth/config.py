"""Authentication configuration for DeerFlow."""
import logging
import warnings

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
        _auth_config = AuthConfig()
        if _auth_config.jwt_secret == _WEAK_SECRET_DEFAULT:
            warnings.warn(
                "JWT secret is using the default value 'CHANGE_ME_IN_PRODUCTION'. "
                "Set AUTH_JWT_SECRET environment variable or configure jwt_secret explicitly. "
                "Falling back to this default is insecure in production.",
                UserWarning,
                stacklevel=2,
            )
            logger.warning(
                "Using default JWT secret. Set AUTH_JWT_SECRET for production deployments."
            )
    return _auth_config


def set_auth_config(config: AuthConfig) -> None:
    """Set the global AuthConfig instance."""
    global _auth_config
    _auth_config = config
