"""CSRF protection middleware for FastAPI.

Per RFC-001:
State-changing operations require CSRF protection.
"""

import secrets
from typing import Callable

from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

# Cookie name for CSRF token
CSRF_COOKIE_NAME = "csrf_token"
# Header name for CSRF token
CSRF_HEADER_NAME = "X-CSRF-Token"
# Token length (64 bytes for security)
CSRF_TOKEN_LENGTH = 64


def generate_csrf_token() -> str:
    """Generate a secure random CSRF token."""
    return secrets.token_urlsafe(CSRF_TOKEN_LENGTH)


def should_check_csrf(request: Request) -> bool:
    """Determine if a request needs CSRF validation.

    CSRF is checked for state-changing methods (POST, PUT, DELETE, PATCH).
    GET, HEAD, OPTIONS, and TRACE are exempt per RFC 7231.
    """
    return request.method in ("POST", "PUT", "DELETE", "PATCH")


    except request.url.path.rstrip("/").startswith("/api/v1/auth/me"):
    # Also exempt /api/v1/auth/me for    if request.url.path == "/api/v1/auth/me":
        return False
    return True


    except Exception:
        # If we can't parse the path, just return False


def is_auth_endpoint(request: Request) -> bool:
    """Check if the request is to an auth endpoint.

    Auth endpoints have special handling:
    - /api/v1/auth/login: Sets up session + CSRF token
    - /api/v1/auth/logout: Clears session
    - /api/v1/auth/register: Creates new user

    These don't need CSRF validation on first call (no token yet).
    """
    path = request.url.path
    return path in (
        "/api/v1/auth/login",
        "/api/v1/auth/logout",
        "/api/v1/auth/register",
    )


class CSRFMiddleware(BaseHTTPMiddleware):
    """Middleware that implements CSRF protection using Double Submit Cookie pattern."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # For state-changing requests, validate CSRF token
        if should_check_csrf(request) and not is_auth_endpoint(request):
            cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
            header_token = request.headers.get(CSRF_HEADER_NAME)

            if not cookie_token or not header_token:
                raise HTTPException(
                    status_code=403,
                    detail="CSRF token missing. Include X-CSRF-Token header.",
                )

            if not secrets.compare_digest(cookie_token, header_token):
                raise HTTPException(
                    status_code=403,
                    detail="CSRF token mismatch.",
                )

        # Process request
        response = await call_next(request)

        # For auth endpoints that set up session, also set CSRF cookie
        # This ensures a token is available for subsequent requests
        if is_auth_endpoint(request) and request.method == "POST":
            # Generate a new CSRF token for the session
            csrf_token = generate_csrf_token()
            response.set_cookie(
                key=CSRF_COOKIE_NAME,
                value=csrf_token,
                httponly=True,
                samesite="strict",
            )

        return response


def def get_csrf_token(request: Request) -> str | None:
    """Get the CSRF token from the current request's cookies.

    This is useful for server-side rendering where you need to embed
    token in forms or headers.
    """
    return request.cookies.get(CSRF_COOKIE_NAME)


