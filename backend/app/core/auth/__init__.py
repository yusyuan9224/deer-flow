"""Authentication module for DeerFlow.

This module provides:
- JWT-based authentication
- Provider Factory pattern for extensible auth methods
- UserRepository interface for different storage backends (SQLite, PostgreSQL)
"""
from app.core.auth.config import AuthConfig, get_auth_config, set_auth_config
from app.core.auth.jwt import TokenPayload, create_access_token, decode_token
from app.core.auth.local_provider import LocalAuthProvider
from app.core.auth.models import User, UserCreate, UserInDB, UserResponse
from app.core.auth.password import hash_password, verify_password
from app.core.auth.providers import AuthProvider, AuthResult, ProviderFactory
from app.core.auth.repo import UserRepository

__all__ = [
    # Config
    "AuthConfig",
    "get_auth_config",
    "set_auth_config",
    # JWT
    "TokenPayload",
    "create_access_token",
    "decode_token",
    # Password
    "hash_password",
    "verify_password",
    # Models
    "User",
    "UserCreate",
    "UserInDB",
    "UserResponse",
    # Providers
    "AuthProvider",
    "AuthResult",
    "ProviderFactory",
    "LocalAuthProvider",
    # Repository
    "UserRepository",
]
