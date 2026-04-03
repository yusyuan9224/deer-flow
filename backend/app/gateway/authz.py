"""Authorization decorators and context for DeerFlow.

Inspired by LangGraph Auth system: https://github.com/langchain-ai/langgraph/blob/main/libs/sdk-py/langgraph_sdk/auth/__init__.py

**Usage:**

1. Use ``@require_auth`` on routes that need authentication
2. Use ``@require_permission("resource", "action", filter_key=...)`` for permission checks
3. The decorator chain processes from bottom to top

**Example:**

    @router.get("/{thread_id}")
    @require_auth
    @require_permission("threads", "read", owner_check=True)
    async def get_thread(thread_id: str, request: Request):
        # User is authenticated and has threads:read permission
        ...

**Permission Model:**

- threads:read   - View thread
- threads:write  - Create/update thread
- threads:delete - Delete thread
- runs:create   - Run agent
- runs:read     - View run
- runs:cancel   - Cancel run
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar

from fastapi import HTTPException, Request

if TYPE_CHECKING:
    from app.gateway.auth.models import User

P = ParamSpec("P")
T = TypeVar("T")


# Permission constants
class Permissions:
    """Permission constants for resource:action format."""

    # Threads
    THREADS_READ = "threads:read"
    THREADS_WRITE = "threads:write"
    THREADS_DELETE = "threads:delete"

    # Runs
    RUNS_CREATE = "runs:create"
    RUNS_READ = "runs:read"
    RUNS_CANCEL = "runs:cancel"


# Resource-action mapping for owner_check
RESOURCE_ACTIONS: dict[str, set[str]] = {
    "threads": {"read", "write", "delete"},
    "runs": {"create", "read", "cancel"},
}


class AuthContext:
    """Authentication context for the current request.

    Stored in request.state.auth after require_auth decoration.

    Attributes:
        user: The authenticated user, or None if anonymous
        permissions: List of permission strings (e.g., "threads:read")
    """

    __slots__ = ("user", "permissions")

    def __init__(self, user: User | None = None, permissions: list[str] | None = None):
        self.user = user
        self.permissions = permissions or []

    @property
    def is_authenticated(self) -> bool:
        """Check if user is authenticated."""
        return self.user is not None

    def has_permission(self, resource: str, action: str) -> bool:
        """Check if context has permission for resource:action.

        Args:
            resource: Resource name (e.g., "threads")
            action: Action name (e.g., "read")

        Returns:
            True if user has permission
        """
        permission = f"{resource}:{action}"
        return permission in self.permissions

    def require_user(self) -> User:
        """Get user or raise 401.

        Raises:
            HTTPException 401 if not authenticated
        """
        if not self.user:
            raise HTTPException(status_code=401, detail="Authentication required")
        return self.user


def get_auth_context(request: Request) -> AuthContext | None:
    """Get AuthContext from request state."""
    return getattr(request.state, "auth", None)


async def _authenticate(request: Request) -> AuthContext:
    """Authenticate request and return AuthContext.

    Reads access_token from cookie, validates JWT, and returns user info.
    Returns AuthContext with user=None for anonymous requests.
    """
    from app.gateway.auth import decode_token
    from app.gateway.auth.errors import TokenError

    access_token = request.cookies.get("access_token")
    if not access_token:
        return AuthContext(user=None, permissions=[])

    payload = decode_token(access_token)
    if isinstance(payload, TokenError):
        return AuthContext(user=None, permissions=[])

    # Use cached provider singleton to avoid repeated instantiation
    from app.gateway.deps import _get_local_provider

    provider = _get_local_provider()
    user = await provider.get_user(payload.sub)
    if user is None:
        return AuthContext(user=None, permissions=[])

    # For now, all authenticated users get basic permissions
    # In future, permissions could be stored in user record
    permissions = [
        Permissions.THREADS_READ,
        Permissions.THREADS_WRITE,
        Permissions.THREADS_DELETE,
        Permissions.RUNS_CREATE,
        Permissions.RUNS_READ,
        Permissions.RUNS_CANCEL,
    ]

    return AuthContext(user=user, permissions=permissions)


def require_auth[**P, T](func: Callable[P, T]) -> Callable[P, T]:
    """Decorator that authenticates the request and sets AuthContext.

    Must be placed ABOVE other decorators (executes after them).

    Usage:
        @router.get("/{thread_id}")
        @require_auth  # Bottom decorator (executes first after permission check)
        @require_permission("threads", "read")
        async def get_thread(thread_id: str, request: Request):
            auth: AuthContext = request.state.auth
            ...

    Raises:
        ValueError: If 'request' parameter is missing
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        request = kwargs.get("request")
        if request is None:
            raise ValueError("require_auth decorator requires 'request' parameter")

        # Authenticate and set context
        auth_context = await _authenticate(request)
        request.state.auth = auth_context

        return await func(*args, **kwargs)

    return wrapper


def require_permission(
    resource: str,
    action: str,
    owner_check: bool = False,
    owner_filter_key: str = "user_id",
    inject_record: bool = False,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator that checks permission for resource:action.

    Must be used AFTER @require_auth.

    Args:
        resource: Resource name (e.g., "threads", "runs")
        action: Action name (e.g., "read", "write", "delete")
        owner_check: If True, validates that the current user owns the resource.
                     Requires 'thread_id' path parameter and performs ownership check.
        owner_filter_key: Field name for ownership filter (default: "user_id")
        inject_record: If True and owner_check is True, injects the thread record
                      into kwargs['thread_record'] for use in the handler.

    Usage:
        # Simple permission check
        @require_permission("threads", "read")
        async def get_thread(thread_id: str, request: Request):
            ...

        # With ownership check (for /threads/{thread_id} endpoints)
        @require_permission("threads", "delete", owner_check=True)
        async def delete_thread(thread_id: str, request: Request):
            ...

        # With ownership check and record injection
        @require_permission("threads", "delete", owner_check=True, inject_record=True)
        async def delete_thread(thread_id: str, request: Request, thread_record: dict = None):
            # thread_record is injected if found
            ...

    Raises:
        HTTPException 401: If authentication required but user is anonymous
        HTTPException 403: If user lacks permission
        HTTPException 404: If owner_check=True but user doesn't own the thread
        ValueError: If owner_check=True but 'thread_id' parameter is missing
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            request = kwargs.get("request")
            if request is None:
                raise ValueError("require_permission decorator requires 'request' parameter")

            auth: AuthContext = getattr(request.state, "auth", None)
            if auth is None:
                # Auto-authenticate if not already done
                auth = await _authenticate(request)
                request.state.auth = auth

            # Check authentication
            if not auth.is_authenticated:
                raise HTTPException(status_code=401, detail="Authentication required")

            # Check permission
            if not auth.has_permission(resource, action):
                raise HTTPException(
                    status_code=403,
                    detail=f"Permission denied: {resource}:{action}",
                )

            # Owner check for thread-specific resources
            if owner_check:
                thread_id = kwargs.get("thread_id")
                if thread_id is None:
                    raise ValueError("require_permission with owner_check=True requires 'thread_id' parameter")

                # Get thread and verify ownership
                from app.gateway.routers.threads import _store_get, get_store

                store = get_store(request)
                if store is not None:
                    record = await _store_get(store, thread_id)
                    if record:
                        owner_id = record.get("metadata", {}).get(owner_filter_key)
                        if owner_id and owner_id != str(auth.user.id):
                            raise HTTPException(
                                status_code=404,
                                detail=f"Thread {thread_id} not found",
                            )
                        # Inject record if requested
                        if inject_record:
                            kwargs["thread_record"] = record

            return await func(*args, **kwargs)

        return wrapper

    return decorator


# Convenience decorators for common permission patterns
def require_thread_owner[**P, T](func: Callable[P, T]) -> Callable[P, T]:
    """Shortcut for @require_permission("threads", "write", owner_check=True).

    Use for endpoints that modify thread state (PATCH, DELETE).
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        return await func(*args, **kwargs)

    # Apply decorators in correct order (bottom to top = inner to outer)
    # First auth (sets context), then permission check
    wrapper = require_permission("threads", "write", owner_check=True)(wrapper)
    wrapper = require_auth(wrapper)
    return wrapper


def require_thread_read[**P, T](func: Callable[P, T]) -> Callable[P, T]:
    """Shortcut for @require_permission("threads", "read", owner_check=True).

    Use for GET thread endpoints.
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        return await func(*args, **kwargs)

    wrapper = require_permission("threads", "read", owner_check=True)(wrapper)
    wrapper = require_auth(wrapper)
    return wrapper
