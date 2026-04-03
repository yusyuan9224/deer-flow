"""JWT token creation and verification."""
from datetime import UTC, datetime, timedelta

import jwt
from pydantic import BaseModel

from app.gateway.auth.config import get_auth_config
from app.gateway.auth.errors import TokenError


class TokenPayload(BaseModel):
    """JWT token payload."""

    sub: str  # user_id
    exp: datetime
    iat: datetime | None = None


def create_access_token(user_id: str, expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token.

    Args:
        user_id: The user's UUID as string
        expires_delta: Optional custom expiry, defaults to 7 days

    Returns:
        Encoded JWT string
    """
    config = get_auth_config()
    expiry = expires_delta or timedelta(days=config.token_expiry_days)

    now = datetime.now(UTC)
    payload = {"sub": user_id, "exp": now + expiry, "iat": now}
    return jwt.encode(payload, config.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> TokenPayload | TokenError:
    """Decode and validate a JWT token.

    Returns:
        TokenPayload if valid, or a specific TokenError variant.
    """
    config = get_auth_config()
    try:
        payload = jwt.decode(token, config.jwt_secret, algorithms=["HS256"])
        return TokenPayload(**payload)
    except jwt.ExpiredSignatureError:
        return TokenError.EXPIRED
    except jwt.InvalidSignatureError:
        return TokenError.INVALID_SIGNATURE
    except jwt.PyJWTError:
        return TokenError.MALFORMED
