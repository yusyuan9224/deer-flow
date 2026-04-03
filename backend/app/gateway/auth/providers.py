"""Auth provider abstraction and factory."""
from abc import ABC, abstractmethod
from typing import ClassVar

from pydantic import BaseModel


class AuthProvider(ABC):
    """Abstract base class for authentication providers."""

    @abstractmethod
    async def authenticate(self, credentials: dict) -> "User | None":
        """Authenticate user with given credentials.

        Returns User if authentication succeeds, None otherwise.
        """
        ...

    @abstractmethod
    async def get_user(self, user_id: str) -> "User | None":
        """Retrieve user by ID."""
        ...


class ProviderFactory:
    """Factory for registering and retrieving auth providers."""

    _providers: ClassVar[dict[str, type[AuthProvider]]] = {}
    _instances: ClassVar[dict[str, AuthProvider]] = {}

    @classmethod
    def register(cls, name: str, provider_cls: type[AuthProvider]) -> None:
        """Register an auth provider class."""
        cls._providers[name] = provider_cls

    @classmethod
    def get(cls, name: str) -> AuthProvider:
        """Get or create an auth provider instance."""
        if name not in cls._instances:
            if name not in cls._providers:
                raise ValueError(f"Unknown auth provider: {name}")
            cls._instances[name] = cls._providers[name]()
        return cls._instances[name]

    @classmethod
    def list_providers(cls) -> list[str]:
        """List all registered provider names."""
        return list(cls._providers.keys())


class AuthResult(BaseModel):
    """Standardized authentication result."""

    success: bool
    user: "User | None" = None
    error: str | None = None


# Import User at runtime to avoid circular imports
from app.gateway.auth.models import User  # noqa: E402
