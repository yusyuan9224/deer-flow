"""Local email/password authentication provider."""

from app.core.auth.models import User
from app.core.auth.password import hash_password, verify_password
from app.core.auth.providers import AuthProvider
from app.core.auth.repo import UserRepository


class LocalAuthProvider(AuthProvider):
    """Email/password authentication provider using local database."""

    def __init__(self, repository: UserRepository):
        """Initialize with a UserRepository.

        Args:
            repository: UserRepository implementation (SQLite, PostgreSQL, etc.)
        """
        self._repo = repository

    async def authenticate(self, credentials: dict) -> User | None:
        """Authenticate with email and password.

        Args:
            credentials: dict with 'email' and 'password' keys

        Returns:
            User if authentication succeeds, None otherwise
        """
        email = credentials.get("email")
        password = credentials.get("password")

        if not email or not password:
            return None

        user = await self._repo.get_user_by_email(email)
        if user is None:
            return None

        if user.password_hash is None:
            # OAuth user without local password
            return None

        if not verify_password(password, user.password_hash):
            return None

        return user

    async def get_user(self, user_id: str) -> User | None:
        """Get user by ID."""
        return await self._repo.get_user_by_id(user_id)

    async def create_user(self, email: str, password: str | None = None) -> User:
        """Create a new local user.

        Args:
            email: User email address
            password: Plain text password (will be hashed)

        Returns:
            Created User instance
        """
        user = User(
            email=email,
            password_hash=hash_password(password) if password else None,
        )
        return await self._repo.create_user(user)

    async def get_user_by_oauth(self, provider: str, oauth_id: str) -> User | None:
        """Get user by OAuth provider and ID."""
        return await self._repo.get_user_by_oauth(provider, oauth_id)

    async def get_user_by_email(self, email: str) -> User | None:
        """Get user by email."""
        return await self._repo.get_user_by_email(email)
