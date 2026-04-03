"""SQLite implementation of UserRepository."""

import asyncio
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from app.gateway.auth.config import get_auth_config
from app.gateway.auth.models import User
from app.gateway.auth.repositories.base import UserRepository


def _get_users_db_path() -> Path:
    """Get the users database path."""
    config = get_auth_config()
    if config.users_db_path:
        return Path(config.users_db_path)
    # Default path: .deer-flow/users.db
    return Path(".deer-flow/users.db")


def _get_connection() -> sqlite3.Connection:
    """Get a SQLite connection for the users database."""
    db_path = _get_users_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _init_users_table(conn: sqlite3.Connection) -> None:
    """Initialize the users table if it doesn't exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            system_role TEXT NOT NULL DEFAULT 'user',
            created_at REAL NOT NULL,
            oauth_provider TEXT,
            oauth_id TEXT
        )
    """
    )
    # Add unique constraint for OAuth identity to prevent duplicate social logins
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_oauth_identity
        ON users(oauth_provider, oauth_id)
        WHERE oauth_provider IS NOT NULL AND oauth_id IS NOT NULL
    """
    )
    conn.commit()


@contextmanager
def _get_users_conn():
    """Context manager for users database connection."""
    conn = _get_connection()
    try:
        _init_users_table(conn)
        yield conn
    finally:
        conn.close()


class SQLiteUserRepository(UserRepository):
    """SQLite implementation of UserRepository."""

    async def create_user(self, user: User) -> User:
        """Create a new user in SQLite."""
        return await asyncio.to_thread(self._create_user_sync, user)

    def _create_user_sync(self, user: User) -> User:
        """Synchronous user creation (runs in thread pool)."""
        with _get_users_conn() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO users (id, email, password_hash, system_role, created_at, oauth_provider, oauth_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(user.id),
                        user.email,
                        user.password_hash,
                        user.system_role,
                        datetime.now(UTC).timestamp(),
                        user.oauth_provider,
                        user.oauth_id,
                    ),
                )
                conn.commit()
            except sqlite3.IntegrityError as e:
                if "UNIQUE constraint failed: users.email" in str(e):
                    raise ValueError(f"Email already registered: {user.email}") from e
                raise
        return user

    async def get_user_by_id(self, user_id: str) -> User | None:
        """Get user by ID from SQLite."""
        return await asyncio.to_thread(self._get_user_by_id_sync, user_id)

    def _get_user_by_id_sync(self, user_id: str) -> User | None:
        """Synchronous get by ID (runs in thread pool)."""
        with _get_users_conn() as conn:
            cursor = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            row = cursor.fetchone()
            if row is None:
                return None
            return self._row_to_user(dict(row))

    async def get_user_by_email(self, email: str) -> User | None:
        """Get user by email from SQLite."""
        return await asyncio.to_thread(self._get_user_by_email_sync, email)

    def _get_user_by_email_sync(self, email: str) -> User | None:
        """Synchronous get by email (runs in thread pool)."""
        with _get_users_conn() as conn:
            cursor = conn.execute("SELECT * FROM users WHERE email = ?", (email,))
            row = cursor.fetchone()
            if row is None:
                return None
            return self._row_to_user(dict(row))

    async def get_user_by_oauth(self, provider: str, oauth_id: str) -> User | None:
        """Get user by OAuth provider and ID from SQLite."""
        return await asyncio.to_thread(self._get_user_by_oauth_sync, provider, oauth_id)

    def _get_user_by_oauth_sync(self, provider: str, oauth_id: str) -> User | None:
        """Synchronous get by OAuth (runs in thread pool)."""
        with _get_users_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM users WHERE oauth_provider = ? AND oauth_id = ?",
                (provider, oauth_id),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return self._row_to_user(dict(row))

    @staticmethod
    def _row_to_user(row: dict[str, Any]) -> User:
        """Convert a database row to a User model."""
        return User(
            id=UUID(row["id"]),
            email=row["email"],
            password_hash=row["password_hash"],
            system_role=row["system_role"],
            created_at=datetime.fromtimestamp(row["created_at"], tz=UTC),
            oauth_provider=row.get("oauth_provider"),
            oauth_id=row.get("oauth_id"),
        )
