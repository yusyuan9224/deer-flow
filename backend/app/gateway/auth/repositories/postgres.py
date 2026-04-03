"""PostgreSQL implementation of UserRepository."""

import asyncio
import atexit
import logging
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import psycopg2
from psycopg2.extensions import connection as PgConnection
from psycopg2.pool import ThreadedConnectionPool

from app.gateway.auth.config import get_auth_config
from app.gateway.auth.models import User
from app.gateway.auth.repositories.base import UserRepository

_pool: ThreadedConnectionPool | None = None


def _get_pool() -> ThreadedConnectionPool:
    """Get or create the PostgreSQL connection pool."""
    global _pool
    if _pool is None:
        # Trigger config load (may set up defaults)
        get_auth_config()
        # For now, get connection info from environment or config
        # TODO: Add proper config for PostgreSQL connection
        import os

        database_url = os.getenv("DATABASE_URL", "postgresql://localhost:5432/deerflow")
        _pool = ThreadedConnectionPool(minconn=1, maxconn=10, dsn=database_url)
    return _pool


def _init_users_table(conn: PgConnection) -> None:
    """Initialize the users table if it doesn't exist."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255),
                system_role VARCHAR(50) NOT NULL DEFAULT 'user',
                created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                oauth_provider VARCHAR(50),
                oauth_id VARCHAR(255)
            )
        """
        )
        # Add unique constraint for OAuth identity to prevent duplicate social logins
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_oauth_identity
            ON users(oauth_provider, oauth_id)
            WHERE oauth_provider IS NOT NULL AND oauth_id IS NOT NULL
        """
        )
        conn.commit()


@contextmanager
def _get_conn() -> Generator[PgConnection, None, None]:
    """Context manager for PostgreSQL connection."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        _init_users_table(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


logger = logging.getLogger(__name__)


def _close_pool() -> None:
    """Close the connection pool on app shutdown."""
    global _pool
    if _pool is not None:
        try:
            _pool.closeall()
            logger.info("PostgreSQL connection pool closed")
        except Exception as e:
            logger.warning("Error closing PostgreSQL connection pool: %s", e)
        finally:
            _pool = None


atexit.register(_close_pool)


def close_pool() -> None:
    """Close the PostgreSQL connection pool.

    Should be called during application shutdown to release all connections.
    """
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


def _init_users_table(conn: PgConnection) -> None:
    """Initialize the users table if it doesn't exist."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255),
                system_role VARCHAR(50) NOT NULL DEFAULT 'user',
                created_at TIMESTAMP NOT NULL,
                oauth_provider VARCHAR(50),
                oauth_id VARCHAR(255)
            )
        """
        )
        # Add unique constraint for OAuth identity to prevent duplicate social logins
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_oauth_identity
            ON users(oauth_provider, oauth_id)
            WHERE oauth_provider IS NOT NULL AND oauth_id IS NOT NULL
        """
        )
        conn.commit()


@contextmanager
def _get_conn() -> Generator[PgConnection, None, None]:
    """Context manager for PostgreSQL connection."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        _init_users_table(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


class PostgresUserRepository(UserRepository):
    """PostgreSQL implementation of UserRepository."""

    async def create_user(self, user: User) -> User:
        """Create a new user in PostgreSQL."""
        return await asyncio.to_thread(self._create_user_sync, user)

    def _create_user_sync(self, user: User) -> User:
        """Synchronous user creation (runs in thread pool)."""
        with _get_conn() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        """
                        INSERT INTO users (id, email, password_hash, system_role, created_at, oauth_provider, oauth_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            str(user.id),
                            user.email,
                            user.password_hash,
                            user.system_role,
                            datetime.now(UTC),
                            user.oauth_provider,
                            user.oauth_id,
                        ),
                    )
                except psycopg2.IntegrityError as e:
                    if "unique constraint" in str(e).lower() and "email" in str(e).lower():
                        raise ValueError(f"Email already registered: {user.email}") from e
                    raise
        return user

    async def get_user_by_id(self, user_id: str) -> User | None:
        """Get user by ID from PostgreSQL."""
        return await asyncio.to_thread(self._get_user_by_id_sync, user_id)

    def _get_user_by_id_sync(self, user_id: str) -> User | None:
        """Synchronous get by ID (runs in thread pool)."""
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
                row = cur.fetchone()
                if row is None:
                    return None
                return self._row_to_user(row)

    async def get_user_by_email(self, email: str) -> User | None:
        """Get user by email from PostgreSQL."""
        return await asyncio.to_thread(self._get_user_by_email_sync, email)

    def _get_user_by_email_sync(self, email: str) -> User | None:
        """Synchronous get by email (runs in thread pool)."""
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM users WHERE email = %s", (email,))
                row = cur.fetchone()
                if row is None:
                    return None
                return self._row_to_user(row)

    async def get_user_by_oauth(self, provider: str, oauth_id: str) -> User | None:
        """Get user by OAuth provider and ID from PostgreSQL."""
        return await asyncio.to_thread(self._get_user_by_oauth_sync, provider, oauth_id)

    def _get_user_by_oauth_sync(self, provider: str, oauth_id: str) -> User | None:
        """Synchronous get by OAuth (runs in thread pool)."""
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM users WHERE oauth_provider = %s AND oauth_id = %s",
                    (provider, oauth_id),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return self._row_to_user(row)

    @staticmethod
    def _row_to_user(row: tuple[Any, ...]) -> User:
        """Convert a database row to a User model."""
        return User(
            id=UUID(str(row[0])),
            email=row[1],
            password_hash=row[2],
            system_role=row[3],
            created_at=row[4] if isinstance(row[4], datetime) else datetime.fromisoformat(str(row[4])),
            oauth_provider=row[5],
            oauth_id=row[6],
        )
