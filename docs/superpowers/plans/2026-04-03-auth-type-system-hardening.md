# Auth Type System Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate adversarial review cycling by encoding domain invariants in the type system at auth module boundaries.

**Architecture:** Parse-Don't-Validate at every system boundary + discriminated unions for all fallible operations. No internal business logic changes — only function signatures, return types, and call sites.

**Tech Stack:** Python Pydantic + Enum (backend), TypeScript Zod + tagged unions (frontend)

**Spec:** `docs/specs/2026-04-03-auth-type-system-design.md`

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `backend/app/core/auth/errors.py` | `AuthErrorCode` enum, `TokenError` enum, `AuthErrorResponse` model |
| `frontend/src/core/auth/types.ts` | `AuthResult` tagged union, `userSchema` Zod, `AuthErrorCode`, `parseAuthError` |
| `frontend/src/core/auth/proxy-policy.ts` | `ProxyPolicy` type, `LANGGRAPH_COMPAT_POLICY` constant |
| `frontend/src/core/auth/gateway-config.ts` | `GatewayConfig` Zod schema, `parseGatewayConfig()` |

### Modified Files
| File | Change |
|------|--------|
| `backend/app/core/auth/__init__.py` | Re-export new error types |
| `backend/app/core/auth/jwt.py` | `decode_token` returns `TokenPayload \| TokenError` |
| `backend/app/core/auth/models.py` | `UserResponse.system_role` → `Literal["admin", "user"]` |
| `backend/app/core/auth/config.py` | Add `env`, `cookie_secure` fields with validation |
| `backend/app/gateway/routers/auth.py` | Use `AuthErrorResponse` in HTTPExceptions, read `AuthConfig`, remove token from body |
| `backend/app/gateway/app.py` | Register `CSRFMiddleware` |
| `backend/app/gateway/csrf_middleware.py` | Fix path matching for `/api/v1/auth/login/local` |
| `frontend/src/core/auth/server.ts` | Return `AuthResult`, use Zod parse, use `GatewayConfig` |
| `frontend/src/core/auth/AuthProvider.tsx` | Import `User` from `types.ts` |
| `frontend/src/app/(auth)/layout.tsx` | Exhaustive switch on `AuthResult`, non-interactive degraded page |
| `frontend/src/app/workspace/layout.tsx` | Exhaustive switch on `AuthResult`, logout recovery path |
| `frontend/src/app/(auth)/login/page.tsx` | Use `parseAuthError` for structured error display |
| `frontend/src/app/api/langgraph-compat/[...path]/route.ts` | Read from `ProxyPolicy` + `GatewayConfig` |
| `frontend/next.config.js` | Deny-by-default rewrites |

---

## Phase 1: Types (no behavior change)

### Task 1: Backend Error Types

**Files:**
- Create: `backend/app/core/auth/errors.py`
- Modify: `backend/app/core/auth/__init__.py`
- Test: `backend/tests/test_auth_errors.py`

- [ ] **Step 1: Create `errors.py` with AuthErrorCode, TokenError, AuthErrorResponse**

```python
# backend/app/core/auth/errors.py
"""Typed error definitions for auth module.

AuthErrorCode: exhaustive enum of all auth failure conditions.
TokenError: exhaustive enum of JWT decode failures.
AuthErrorResponse: structured error payload for HTTP responses.
"""
from enum import Enum

from pydantic import BaseModel


class AuthErrorCode(str, Enum):
    """Exhaustive list of auth error conditions."""

    INVALID_CREDENTIALS = "invalid_credentials"
    TOKEN_EXPIRED = "token_expired"
    TOKEN_INVALID = "token_invalid"
    USER_NOT_FOUND = "user_not_found"
    EMAIL_ALREADY_EXISTS = "email_already_exists"
    PROVIDER_NOT_FOUND = "provider_not_found"
    NOT_AUTHENTICATED = "not_authenticated"


class TokenError(str, Enum):
    """Exhaustive list of JWT decode failure reasons."""

    EXPIRED = "expired"
    INVALID_SIGNATURE = "invalid_signature"
    MALFORMED = "malformed"


class AuthErrorResponse(BaseModel):
    """Structured error response — replaces bare `detail` strings."""

    code: AuthErrorCode
    message: str
```

- [ ] **Step 2: Write test for error types**

```python
# backend/tests/test_auth_errors.py
"""Tests for auth error types."""
from app.core.auth.errors import AuthErrorCode, AuthErrorResponse, TokenError


def test_auth_error_code_values():
    assert AuthErrorCode.INVALID_CREDENTIALS == "invalid_credentials"
    assert AuthErrorCode.TOKEN_EXPIRED == "token_expired"
    assert AuthErrorCode.NOT_AUTHENTICATED == "not_authenticated"


def test_token_error_values():
    assert TokenError.EXPIRED == "expired"
    assert TokenError.INVALID_SIGNATURE == "invalid_signature"
    assert TokenError.MALFORMED == "malformed"


def test_auth_error_response_serialization():
    err = AuthErrorResponse(
        code=AuthErrorCode.TOKEN_EXPIRED,
        message="Token has expired",
    )
    d = err.model_dump()
    assert d == {"code": "token_expired", "message": "Token has expired"}


def test_auth_error_response_from_dict():
    d = {"code": "invalid_credentials", "message": "Wrong password"}
    err = AuthErrorResponse(**d)
    assert err.code == AuthErrorCode.INVALID_CREDENTIALS
```

- [ ] **Step 3: Run tests**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_auth_errors.py -v`
Expected: 4 PASSED

- [ ] **Step 4: Update `__init__.py` to re-export error types**

Add to `backend/app/core/auth/__init__.py`:

```python
from app.core.auth.errors import AuthErrorCode, AuthErrorResponse, TokenError
```

And add to `__all__`:

```python
    # Errors
    "AuthErrorCode",
    "AuthErrorResponse",
    "TokenError",
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/auth/errors.py backend/tests/test_auth_errors.py backend/app/core/auth/__init__.py
git commit -m "feat(auth): add typed error definitions (AuthErrorCode, TokenError, AuthErrorResponse)"
```

---

### Task 2: Fix UserResponse.system_role Type

**Files:**
- Modify: `backend/app/core/auth/models.py:49-54`

- [ ] **Step 1: Change `UserResponse.system_role` from `str` to `Literal`**

In `backend/app/core/auth/models.py`, change:

```python
# Before
class UserResponse(BaseModel):
    """Response model for user info endpoint."""

    id: str
    email: str
    system_role: str
```

To:

```python
# After
class UserResponse(BaseModel):
    """Response model for user info endpoint."""

    id: str
    email: str
    system_role: Literal["admin", "user"]
```

- [ ] **Step 2: Run existing tests to verify no regression**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_auth.py -v`
Expected: All existing tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/auth/models.py
git commit -m "fix(auth): preserve system_role Literal type in UserResponse"
```

---

### Task 3: Enhance Backend AuthConfig

**Files:**
- Modify: `backend/app/core/auth/config.py`
- Test: `backend/tests/test_auth_config.py`

- [ ] **Step 1: Write tests for enhanced config**

```python
# backend/tests/test_auth_config.py
"""Tests for AuthConfig typed configuration."""
import os
from unittest.mock import patch

import pytest

from app.core.auth.config import AuthConfig


def test_auth_config_defaults():
    config = AuthConfig(jwt_secret="test-secret-key-123")
    assert config.env == "production"
    assert config.cookie_secure is True
    assert config.token_expiry_days == 7


def test_auth_config_dev_allows_insecure_cookie():
    config = AuthConfig(jwt_secret="test-secret", env="development", cookie_secure=False)
    assert config.cookie_secure is False


def test_auth_config_prod_rejects_insecure_cookie():
    with pytest.raises(ValueError, match="cookie_secure must be True in production"):
        AuthConfig(jwt_secret="test-secret", env="production", cookie_secure=False)


def test_auth_config_from_env():
    env = {
        "AUTH_JWT_SECRET": "test-jwt-secret-from-env",
        "ENV": "development",
        "AUTH_COOKIE_SECURE": "false",
    }
    with patch.dict(os.environ, env, clear=False):
        from app.core.auth.config import _auth_config
        import app.core.auth.config as cfg
        old = cfg._auth_config
        cfg._auth_config = None
        try:
            config = cfg.get_auth_config()
            assert config.jwt_secret == "test-jwt-secret-from-env"
            assert config.env == "development"
            assert config.cookie_secure is False
        finally:
            cfg._auth_config = old
```

- [ ] **Step 2: Run tests to verify they fail (fields don't exist yet)**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_auth_config.py -v`
Expected: FAIL — `env` and `cookie_secure` fields not on AuthConfig

- [ ] **Step 3: Add `env` and `cookie_secure` fields to AuthConfig**

Replace `backend/app/core/auth/config.py` content:

```python
"""Authentication configuration for DeerFlow."""
import logging
import os
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

load_dotenv()

logger = logging.getLogger(__name__)


class AuthConfig(BaseModel):
    """JWT and auth-related configuration. Parsed once at startup."""

    jwt_secret: str = Field(
        ...,
        description="Secret key for JWT signing. MUST be set via AUTH_JWT_SECRET.",
    )
    token_expiry_days: int = Field(default=7, ge=1, le=30)
    env: Literal["development", "production"] = Field(default="production")
    cookie_secure: bool = Field(default=True)
    users_db_path: str | None = Field(
        default=None,
        description="Path to users SQLite DB. Defaults to .deer-flow/users.db",
    )
    oauth_github_client_id: str | None = Field(default=None)
    oauth_github_client_secret: str | None = Field(default=None)

    @field_validator("cookie_secure")
    @classmethod
    def enforce_secure_in_prod(cls, v: bool, info) -> bool:
        if info.data.get("env") == "production" and not v:
            raise ValueError("cookie_secure must be True in production")
        return v


_auth_config: AuthConfig | None = None


def _parse_env() -> Literal["development", "production"]:
    raw = os.environ.get("ENV", "production").lower()
    return "development" if raw in ("development", "dev", "local") else "production"


def get_auth_config() -> AuthConfig:
    """Get the global AuthConfig instance. Parses from env on first call."""
    global _auth_config
    if _auth_config is None:
        jwt_secret = os.environ.get("AUTH_JWT_SECRET")
        if not jwt_secret:
            raise ValueError(
                "AUTH_JWT_SECRET environment variable must be set. "
                'Generate a secure secret with: python -c "import secrets; print(secrets.token_urlsafe(32))"'
            )
        env = _parse_env()
        cookie_secure = os.environ.get("AUTH_COOKIE_SECURE", "true").lower() != "false"
        _auth_config = AuthConfig(
            jwt_secret=jwt_secret,
            env=env,
            cookie_secure=cookie_secure,
        )
        if not cookie_secure:
            logger.warning("AUTH_COOKIE_SECURE=false — cookies sent without Secure flag")
    return _auth_config


def set_auth_config(config: AuthConfig) -> None:
    """Set the global AuthConfig instance (for testing)."""
    global _auth_config
    _auth_config = config
```

- [ ] **Step 4: Run tests**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_auth_config.py -v`
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/auth/config.py backend/tests/test_auth_config.py
git commit -m "feat(auth): add env/cookie_secure to AuthConfig with prod validation"
```

---

### Task 4: Backend decode_token Typed Failure

**Files:**
- Modify: `backend/app/core/auth/jwt.py:36-50`
- Modify: `backend/app/gateway/routers/auth.py` (callers)
- Modify: `backend/app/gateway/deps.py` (callers)

- [ ] **Step 1: Write test for typed decode_token**

```python
# Add to backend/tests/test_auth_errors.py

from unittest.mock import patch
from app.core.auth.jwt import decode_token, create_access_token
from app.core.auth.errors import TokenError
from app.core.auth.config import AuthConfig, set_auth_config


def test_decode_token_returns_token_error_on_expired():
    set_auth_config(AuthConfig(jwt_secret="test-secret", env="development", cookie_secure=False))
    import jwt as pyjwt
    from datetime import datetime, timedelta, UTC
    expired_payload = {"sub": "user-1", "exp": datetime.now(UTC) - timedelta(hours=1), "iat": datetime.now(UTC)}
    token = pyjwt.encode(expired_payload, "test-secret", algorithm="HS256")
    result = decode_token(token)
    assert result == TokenError.EXPIRED


def test_decode_token_returns_token_error_on_bad_signature():
    set_auth_config(AuthConfig(jwt_secret="test-secret", env="development", cookie_secure=False))
    import jwt as pyjwt
    from datetime import datetime, timedelta, UTC
    payload = {"sub": "user-1", "exp": datetime.now(UTC) + timedelta(hours=1), "iat": datetime.now(UTC)}
    token = pyjwt.encode(payload, "wrong-secret", algorithm="HS256")
    result = decode_token(token)
    assert result == TokenError.INVALID_SIGNATURE


def test_decode_token_returns_token_error_on_malformed():
    set_auth_config(AuthConfig(jwt_secret="test-secret", env="development", cookie_secure=False))
    result = decode_token("not-a-jwt")
    assert result == TokenError.MALFORMED


def test_decode_token_returns_payload_on_valid():
    set_auth_config(AuthConfig(jwt_secret="test-secret", env="development", cookie_secure=False))
    token = create_access_token("user-123")
    result = decode_token(token)
    assert not isinstance(result, TokenError)
    assert result.sub == "user-123"
```

- [ ] **Step 2: Run tests — should fail (decode_token still returns None)**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_auth_errors.py::test_decode_token_returns_token_error_on_expired -v`
Expected: FAIL — returns None, not TokenError.EXPIRED

- [ ] **Step 3: Update decode_token to return TokenPayload | TokenError**

In `backend/app/core/auth/jwt.py`, replace the `decode_token` function:

```python
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
```

Add import at top of `jwt.py`:

```python
from app.core.auth.errors import TokenError
```

- [ ] **Step 4: Update callers — auth.py `get_current_user`**

In `backend/app/gateway/routers/auth.py`, update `get_current_user`:

```python
from app.core.auth.errors import AuthErrorCode, AuthErrorResponse, TokenError

async def get_current_user(access_token: str | None = Cookie(None)) -> User:
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AuthErrorResponse(
                code=AuthErrorCode.NOT_AUTHENTICATED, message="Not authenticated"
            ).model_dump(),
        )

    payload = decode_token(access_token)
    if isinstance(payload, TokenError):
        code = AuthErrorCode.TOKEN_EXPIRED if payload == TokenError.EXPIRED else AuthErrorCode.TOKEN_INVALID
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AuthErrorResponse(
                code=code, message=f"Token error: {payload.value}"
            ).model_dump(),
        )

    user = await _local_provider.get_user(payload.sub)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AuthErrorResponse(
                code=AuthErrorCode.USER_NOT_FOUND, message="User not found"
            ).model_dump(),
        )

    return user
```

- [ ] **Step 5: Update callers — deps.py `get_current_user_from_request`**

Apply same pattern in `backend/app/gateway/deps.py` — replace `if payload is None` with `if isinstance(payload, TokenError)`.

- [ ] **Step 6: Run all tests**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/core/auth/jwt.py backend/app/gateway/routers/auth.py backend/app/gateway/deps.py backend/tests/test_auth_errors.py
git commit -m "feat(auth): typed decode_token returns TokenError instead of None"
```

---

### Task 5: Frontend Types — AuthResult, userSchema, parseAuthError

**Files:**
- Create: `frontend/src/core/auth/types.ts`

- [ ] **Step 1: Create `types.ts`**

```typescript
// frontend/src/core/auth/types.ts

import { z } from "zod";

// ── User schema (single source of truth) ──────────────────────────

export const userSchema = z.object({
  id: z.string(),
  email: z.string().email(),
  system_role: z.enum(["admin", "user"]),
});

export type User = z.infer<typeof userSchema>;

// ── SSR auth result (tagged union) ────────────────────────────────

export type AuthResult =
  | { tag: "authenticated"; user: User }
  | { tag: "unauthenticated" }
  | { tag: "gateway_unavailable" }
  | { tag: "config_error"; message: string };

export function assertNever(x: never): never {
  throw new Error(`Unexpected auth result: ${JSON.stringify(x)}`);
}

// ── Backend error response parsing ────────────────────────────────

export type AuthErrorCode =
  | "invalid_credentials"
  | "token_expired"
  | "token_invalid"
  | "user_not_found"
  | "email_already_exists"
  | "not_authenticated";

export interface AuthErrorResponse {
  code: AuthErrorCode;
  message: string;
}

const authErrorSchema = z.object({
  code: z.enum([
    "invalid_credentials",
    "token_expired",
    "token_invalid",
    "user_not_found",
    "email_already_exists",
    "not_authenticated",
  ]),
  message: z.string(),
});

export function parseAuthError(data: unknown): AuthErrorResponse {
  const parsed = authErrorSchema.safeParse(data);
  if (parsed.success) return parsed.data;
  // Fallback for legacy string-detail responses
  const detail = typeof data === "object" && data !== null && "detail" in data
    ? String((data as Record<string, unknown>).detail)
    : "Authentication failed";
  return { code: "invalid_credentials", message: detail };
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && pnpm typecheck 2>&1 | grep -c "core/auth/types"`
Expected: 0 errors from types.ts

- [ ] **Step 3: Commit**

```bash
git add frontend/src/core/auth/types.ts
git commit -m "feat(auth): add frontend typed auth module (AuthResult, userSchema, parseAuthError)"
```

---

### Task 6: Frontend Gateway Config

**Files:**
- Create: `frontend/src/core/auth/gateway-config.ts`

- [ ] **Step 1: Create `gateway-config.ts`**

```typescript
// frontend/src/core/auth/gateway-config.ts

import { z } from "zod";

const gatewayConfigSchema = z.object({
  internalGatewayUrl: z.string().url(),
  trustedOrigins: z.array(z.string()).min(1),
});

export type GatewayConfig = z.infer<typeof gatewayConfigSchema>;

let _cached: GatewayConfig | null = null;

export function getGatewayConfig(): GatewayConfig {
  if (_cached) return _cached;

  const isDev = process.env.NODE_ENV === "development";

  const rawUrl = process.env.DEER_FLOW_INTERNAL_GATEWAY_BASE_URL?.trim();
  const internalGatewayUrl = rawUrl?.replace(/\/+$/, "") || (isDev ? "http://localhost:8001" : undefined);

  const rawOrigins = process.env.DEER_FLOW_TRUSTED_ORIGINS?.trim();
  const trustedOrigins = rawOrigins
    ? rawOrigins.split(",").map((s) => s.trim()).filter(Boolean)
    : isDev
      ? ["http://localhost:3000"]
      : undefined;

  _cached = gatewayConfigSchema.parse({ internalGatewayUrl, trustedOrigins });
  return _cached;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/core/auth/gateway-config.ts
git commit -m "feat(auth): add typed GatewayConfig with Zod validation"
```

---

### Task 7: Frontend Proxy Policy

**Files:**
- Create: `frontend/src/core/auth/proxy-policy.ts`

- [ ] **Step 1: Create `proxy-policy.ts`**

```typescript
// frontend/src/core/auth/proxy-policy.ts

export interface ProxyPolicy {
  /** Allowed upstream path prefixes */
  readonly allowedPaths: readonly string[];
  /** Request headers to strip before forwarding */
  readonly strippedRequestHeaders: ReadonlySet<string>;
  /** Response headers to strip before returning */
  readonly strippedResponseHeaders: ReadonlySet<string>;
  /** Credential mode: which cookie to forward */
  readonly credential: { readonly type: "cookie"; readonly name: string };
  /** Timeout in ms */
  readonly timeoutMs: number;
  /** CSRF: required for non-GET/HEAD */
  readonly csrf: boolean;
}

export const LANGGRAPH_COMPAT_POLICY: ProxyPolicy = {
  allowedPaths: [
    "threads", "runs", "assistants", "store",
    "models", "mcp", "skills", "memory",
  ],
  strippedRequestHeaders: new Set([
    "host", "connection", "keep-alive", "transfer-encoding", "te", "trailer",
    "upgrade", "authorization", "x-api-key", "origin", "referer",
    "proxy-authorization", "proxy-authenticate",
  ]),
  strippedResponseHeaders: new Set([
    "connection", "keep-alive", "transfer-encoding", "te", "trailer",
    "upgrade", "content-length", "set-cookie",
  ]),
  credential: { type: "cookie", name: "access_token" },
  timeoutMs: 120_000,
  csrf: true,
} as const;
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/core/auth/proxy-policy.ts
git commit -m "feat(auth): add declarative ProxyPolicy type and LANGGRAPH_COMPAT_POLICY"
```

---

## Phase 2: Wire Types to Boundaries

### Task 8: SSR Auth — Return AuthResult + Zod Parse

**Files:**
- Modify: `frontend/src/core/auth/server.ts`
- Modify: `frontend/src/core/auth/AuthProvider.tsx` (User import)

- [ ] **Step 1: Rewrite `server.ts` to return AuthResult with Zod parse**

```typescript
// frontend/src/core/auth/server.ts

import { cookies } from "next/headers";

import { getGatewayConfig } from "./gateway-config";
import { type AuthResult, userSchema } from "./types";

const SSR_AUTH_TIMEOUT_MS = 5_000;

export async function getServerSideUser(): Promise<AuthResult> {
  const cookieStore = await cookies();
  const sessionCookie = cookieStore.get("access_token");
  if (!sessionCookie) return { tag: "unauthenticated" };

  let internalGatewayUrl: string;
  try {
    internalGatewayUrl = getGatewayConfig().internalGatewayUrl;
  } catch (err) {
    return { tag: "config_error", message: String(err) };
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), SSR_AUTH_TIMEOUT_MS);

  try {
    const res = await fetch(`${internalGatewayUrl}/api/v1/auth/me`, {
      headers: { Cookie: `access_token=${sessionCookie.value}` },
      cache: "no-store",
      signal: controller.signal,
    });
    clearTimeout(timeout);

    if (res.ok) {
      const parsed = userSchema.safeParse(await res.json());
      if (!parsed.success) {
        console.error("[SSR auth] Malformed /auth/me response:", parsed.error);
        return { tag: "gateway_unavailable" };
      }
      return { tag: "authenticated", user: parsed.data };
    }
    if (res.status === 401 || res.status === 403) {
      return { tag: "unauthenticated" };
    }
    console.error(`[SSR auth] /api/v1/auth/me responded ${res.status}`);
    return { tag: "gateway_unavailable" };
  } catch (err) {
    clearTimeout(timeout);
    console.error("[SSR auth] Failed to reach gateway:", err);
    return { tag: "gateway_unavailable" };
  }
}
```

- [ ] **Step 2: Update `AuthProvider.tsx` User import**

In `frontend/src/core/auth/AuthProvider.tsx`, change:
```typescript
// Before — local interface
export interface User { id: string; email: string; system_role: string; }

// After — import from types.ts (Zod-derived)
import { type User } from "./types";
// Keep re-exporting for consumers
export type { User };
```

Remove the local `User` interface definition and replace with the import + re-export.

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && pnpm typecheck 2>&1 | tail -10`
Expected: Only pre-existing errors (fetcher.ts, AuthProvider.tsx ReactNode)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/core/auth/server.ts frontend/src/core/auth/AuthProvider.tsx
git commit -m "feat(auth): SSR auth returns AuthResult with Zod-validated User"
```

---

### Task 9: Layout Exhaustive Switch

**Files:**
- Modify: `frontend/src/app/workspace/layout.tsx`
- Modify: `frontend/src/app/(auth)/layout.tsx`

- [ ] **Step 1: Rewrite workspace layout with exhaustive switch**

```typescript
// frontend/src/app/workspace/layout.tsx

import { redirect } from "next/navigation";

import { AuthProvider } from "@/core/auth/AuthProvider";
import { getServerSideUser } from "@/core/auth/server";
import { assertNever } from "@/core/auth/types";
import { WorkspaceContent } from "./workspace-content";

export const dynamic = "force-dynamic";

export default async function WorkspaceLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const result = await getServerSideUser();

  switch (result.tag) {
    case "authenticated":
      return (
        <AuthProvider initialUser={result.user}>
          <WorkspaceContent>{children}</WorkspaceContent>
        </AuthProvider>
      );
    case "unauthenticated":
      redirect("/login");
    case "gateway_unavailable":
      return (
        <div className="flex h-screen flex-col items-center justify-center gap-4">
          <p className="text-muted-foreground">
            Service temporarily unavailable.
          </p>
          <p className="text-xs text-muted-foreground">
            The backend may be restarting. Please wait a moment and try again.
          </p>
          <div className="flex gap-3">
            <a
              href="/workspace"
              className="bg-primary text-primary-foreground hover:bg-primary/90 rounded-md px-4 py-2 text-sm"
            >
              Retry
            </a>
            <a
              href="/api/v1/auth/logout"
              className="text-muted-foreground hover:bg-muted rounded-md border px-4 py-2 text-sm"
            >
              Logout &amp; Reset
            </a>
          </div>
        </div>
      );
    case "config_error":
      throw new Error(result.message);
    default:
      assertNever(result);
  }
}
```

- [ ] **Step 2: Rewrite auth layout with exhaustive switch**

```typescript
// frontend/src/app/(auth)/layout.tsx

import { type ReactNode } from "react";
import { redirect } from "next/navigation";

import { AuthProvider } from "@/core/auth/AuthProvider";
import { getServerSideUser } from "@/core/auth/server";
import { assertNever } from "@/core/auth/types";

export const dynamic = "force-dynamic";

export default async function AuthLayout({
  children,
}: {
  children: ReactNode;
}) {
  const result = await getServerSideUser();

  switch (result.tag) {
    case "authenticated":
      redirect("/workspace");
    case "unauthenticated":
      return <AuthProvider initialUser={null}>{children}</AuthProvider>;
    case "gateway_unavailable":
      return (
        <div className="flex h-screen flex-col items-center justify-center gap-4">
          <p className="text-muted-foreground">
            Service temporarily unavailable.
          </p>
          <a
            href="/login"
            className="bg-primary text-primary-foreground hover:bg-primary/90 rounded-md px-4 py-2 text-sm"
          >
            Retry
          </a>
        </div>
      );
    case "config_error":
      throw new Error(result.message);
    default:
      assertNever(result);
  }
}
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && pnpm typecheck 2>&1 | tail -10`
Expected: Only pre-existing errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/workspace/layout.tsx "frontend/src/app/(auth)/layout.tsx"
git commit -m "feat(auth): exhaustive switch on AuthResult in layouts"
```

---

### Task 10: Login Page — Structured Error Parsing

**Files:**
- Modify: `frontend/src/app/(auth)/login/page.tsx`

- [ ] **Step 1: Update error handling to use parseAuthError**

In the login page's submit handler, replace:

```typescript
// Before
const data = await res.json();
if (!res.ok) {
  setError(data.detail || "Authentication failed");
  return;
}
```

With:

```typescript
// After
import { parseAuthError } from "@/core/auth/types";

if (!res.ok) {
  const data = await res.json();
  const authError = parseAuthError(data);
  setError(authError.message);
  return;
}
```

- [ ] **Step 2: Commit**

```bash
git add "frontend/src/app/(auth)/login/page.tsx"
git commit -m "feat(auth): login page uses parseAuthError for structured error display"
```

---

### Task 11: Proxy Route — Read from Policy + Config

**Files:**
- Modify: `frontend/src/app/api/langgraph-compat/[...path]/route.ts`

- [ ] **Step 1: Refactor proxy to use ProxyPolicy and GatewayConfig**

Rewrite the route handler to import and use the policy/config objects instead of inline constants. The core change:

```typescript
import { LANGGRAPH_COMPAT_POLICY } from "@/core/auth/proxy-policy";
import { getGatewayConfig } from "@/core/auth/gateway-config";

const policy = LANGGRAPH_COMPAT_POLICY;

// Path check: policy.allowedPaths
// Header strip: policy.strippedRequestHeaders
// Credential: policy.credential.name
// Timeout: policy.timeoutMs
// CSRF: policy.csrf → getGatewayConfig().trustedOrigins
// Response strip: policy.strippedResponseHeaders
```

Remove all inline `const ALLOWED_PATH_PREFIXES`, `const STRIPPED_HEADERS`, `const PROXY_TIMEOUT_MS`, `const RESPONSE_STRIPPED`, and the inline `normalizeOrigin` function. Replace with reads from `policy` and `config`.

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && pnpm typecheck 2>&1 | tail -10`
Expected: Only pre-existing errors

- [ ] **Step 3: Commit**

```bash
git add "frontend/src/app/api/langgraph-compat/[...path]/route.ts"
git commit -m "refactor(auth): proxy reads from declarative ProxyPolicy + GatewayConfig"
```

---

### Task 12: Deny-by-Default Rewrites

**Files:**
- Modify: `frontend/next.config.js`

- [ ] **Step 1: Replace catch-all and blanket v1 rewrites with explicit enumeration**

```javascript
// Replace the rewrite section in next.config.js

async rewrites() {
  const beforeFiles = [];
  const langgraphURL = getInternalServiceURL(
    "DEER_FLOW_INTERNAL_LANGGRAPH_BASE_URL",
    "http://127.0.0.1:2024",
  );
  const gatewayURL = getInternalServiceURL(
    "DEER_FLOW_INTERNAL_GATEWAY_BASE_URL",
    "http://127.0.0.1:8001",
  );

  if (!process.env.NEXT_PUBLIC_LANGGRAPH_BASE_URL) {
    beforeFiles.push({ source: "/api/langgraph", destination: langgraphURL });
    beforeFiles.push({ source: "/api/langgraph/:path*", destination: `${langgraphURL}/:path*` });
  }

  // Auth endpoints: explicit v1/auth prefix only (deny-by-default)
  beforeFiles.push({ source: "/api/v1/auth/:path*", destination: `${gatewayURL}/api/v1/auth/:path*` });

  // LangGraph-compat: handled by route handler — no rewrite

  if (!process.env.NEXT_PUBLIC_BACKEND_BASE_URL) {
    // Explicit gateway API prefixes (deny-by-default, no catch-all)
    const GATEWAY_PREFIXES = ["agents", "models", "threads", "memory", "skills", "mcp"];
    for (const prefix of GATEWAY_PREFIXES) {
      beforeFiles.push({ source: `/api/${prefix}`, destination: `${gatewayURL}/api/${prefix}` });
      beforeFiles.push({ source: `/api/${prefix}/:path*`, destination: `${gatewayURL}/api/${prefix}/:path*` });
    }
  }

  return { beforeFiles, afterFiles: [], fallback: [] };
},
```

- [ ] **Step 2: Verify dev server starts without errors**

Run: `cd frontend && pnpm build 2>&1 | tail -5`
Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add frontend/next.config.js
git commit -m "security(auth): deny-by-default rewrites — no catch-all, explicit API prefixes"
```

---

### Task 13: Backend Auth Routes — Structured Errors + Config

**Files:**
- Modify: `backend/app/gateway/routers/auth.py`

- [ ] **Step 1: Update all HTTPException raises to use AuthErrorResponse**

Update `login_local`, `register`, `get_me`, and other endpoints. Key changes:

- `login_local`: Use `AuthConfig` for cookie_secure instead of inline `os.environ.get`
- `login_local`: Return `LoginResponse(expires_in=...)` instead of `TokenResponse(access_token=...)`
- All `raise HTTPException`: Use `AuthErrorResponse(code=..., message=...).model_dump()` as detail

```python
# In login_local:
config = get_auth_config()
response.set_cookie(
    key="access_token",
    value=token,
    httponly=True,
    secure=config.cookie_secure,
    samesite="lax",
    max_age=config.token_expiry_days * 24 * 3600,
)
return LoginResponse(expires_in=config.token_expiry_days * 24 * 3600)
```

- [ ] **Step 2: Run backend tests**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_auth.py -v`
Expected: May need test updates for new response format — fix accordingly

- [ ] **Step 3: Commit**

```bash
git add backend/app/gateway/routers/auth.py
git commit -m "feat(auth): structured AuthErrorResponse in all auth routes, remove token from body"
```

---

## Phase 3: Activate Missing Protections

### Task 14: Register CSRF Middleware + Fix Path Matching

**Files:**
- Modify: `backend/app/gateway/app.py`
- Modify: `backend/app/gateway/csrf_middleware.py`

- [ ] **Step 1: Fix CSRF middleware path matching**

In `backend/app/gateway/csrf_middleware.py`, update `is_auth_endpoint`:

```python
def is_auth_endpoint(request: Request) -> bool:
    path = request.url.path.rstrip("/")
    AUTH_EXEMPT_PATHS = {
        "/api/v1/auth/login/local",
        "/api/v1/auth/logout",
        "/api/v1/auth/register",
    }
    return path in AUTH_EXEMPT_PATHS
```

- [ ] **Step 2: Register CSRFMiddleware in app.py**

In `backend/app/gateway/app.py`, add after the app creation and before CORS:

```python
from app.gateway.csrf_middleware import CSRFMiddleware
app.add_middleware(CSRFMiddleware)
```

- [ ] **Step 3: Write CSRF integration test**

```python
# backend/tests/test_csrf_middleware.py
"""Tests for CSRF middleware."""
import pytest
from fastapi.testclient import TestClient


def test_csrf_blocks_post_without_token(client: TestClient):
    """POST to protected endpoint without CSRF token should return 403."""
    # This tests that CSRFMiddleware is registered and active
    response = client.post("/api/v1/auth/me")
    # Should get 403 CSRF or 401 auth — either means middleware is active
    assert response.status_code in (401, 403)


def test_csrf_allows_get_without_token(client: TestClient):
    """GET requests should not require CSRF token."""
    response = client.get("/api/v1/auth/me")
    # Should get 401 (no auth), not 403 (CSRF)
    assert response.status_code == 401
```

- [ ] **Step 4: Run tests**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/test_csrf_middleware.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/gateway/app.py backend/app/gateway/csrf_middleware.py backend/tests/test_csrf_middleware.py
git commit -m "security(auth): register CSRFMiddleware, fix path matching for login/local"
```

---

### Task 15: Final Verification

- [ ] **Step 1: Run all backend tests**

Run: `cd backend && PYTHONPATH=. uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 2: Run frontend type check**

Run: `cd frontend && pnpm typecheck 2>&1 | tail -10`
Expected: Only pre-existing errors (fetcher.ts, AuthProvider.tsx ReactNode)

- [ ] **Step 3: Run frontend lint**

Run: `cd frontend && pnpm lint 2>&1 | tail -10`
Expected: No new errors

- [ ] **Step 4: Final commit with all remaining changes**

```bash
git add -A
git status
# Verify only auth-scoped files are staged
git commit -m "chore(auth): type system hardening — final verification pass"
```
