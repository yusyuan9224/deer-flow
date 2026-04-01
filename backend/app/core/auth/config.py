"""Authentication configuration for DeerFlow."""
from pydantic import BaseModel, Field


class AuthConfig(BaseModel):
    """JWT and auth-related configuration."""

    jwt_secret: str = Field(
        default="CHANGE_ME_IN_PRODUCTION",
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
    return _auth_config


def set_auth_config(config: AuthConfig) -> None:
    """Set the global AuthConfig instance."""
    global _auth_config
    _auth_config = config
