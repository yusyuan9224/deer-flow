# RFC-001 Auth Module: Type System Hardening

**Date**: 2026-04-03
**Status**: Draft
**Branch**: `feat/rfc-001-auth-module`
**Scope**: Auth module only — no changes to agents, sandbox, tools, MCP, channels

---

## 1. Problem Statement

15 rounds of adversarial review revealed the same 4 root causes manifesting repeatedly:

| Root Cause | Symptom Count | Core Issue |
|------------|---------------|------------|
| Implicit trust boundaries | 6 findings | Trust encoded as ad-hoc `if` checks, not types |
| Untyped errors | 5 findings | `null`, `Error`, string `detail` — callers guess |
| Stringly-typed config | 4 findings | Env vars parsed at point-of-use, never validated |
| Imperative proxy policy | 3 findings | Header/body/CSRF rules scattered as procedural code |

**Single root cause**: Domain invariants exist only in programmers' heads, not in the type system.

**Analogy (category theory)**: Each layer boundary (DB → model → API → frontend) applies a "forgetful functor" — it maps structured types to `string`, discarding information. The fix is to replace forgetful functors with **faithful functors** that preserve structure.

---

## 2. Design Principles

### Parse, Don't Validate

From Alexis King: validation checks a property and discards the evidence; parsing checks a property and **produces a new type** that encodes the evidence.

```
Raw input (string)  →  parse()  →  Typed value (evidence encoded)
                        ↓ fail
                    Structured error (not string)
```

**Rule**: Every system boundary gets exactly one parse point. After parsing, all downstream code operates on the parsed type. No re-validation.

### Result as Tagged Union (Not null/throw)

Replace `T | null` + `throw` with a discriminated union where each variant has exactly one meaning:

```typescript
type Result<T, E> = { ok: true; value: T } | { ok: false; error: E }
```

**Rule**: Functions that can fail return a Result. Callers use exhaustive `switch` on error tags. The compiler enforces completeness.

### Boundary-Only Changes

**Invariant**: Internal business logic (JWT signing, password hashing, DB queries, cookie setting) does NOT change. Only function signatures, return types, and call sites change.

---

## 3. Design: Typed Errors

### 3.1 Backend Error Codes (Python)

Define a single enum of all auth error codes. Used in both HTTPException responses and internal logic.

```python
# backend/app/core/auth/errors.py

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


class AuthErrorResponse(BaseModel):
    """Structured error response — replaces bare `detail` strings."""
    code: AuthErrorCode
    message: str
```

**Usage in routes** (change: `detail=string` → `detail=AuthErrorResponse`):

```python
# Before
raise HTTPException(status_code=401, detail="Invalid or expired token")

# After
raise HTTPException(
    status_code=401,
    detail=AuthErrorResponse(
        code=AuthErrorCode.TOKEN_EXPIRED,
        message="Token has expired",
    ).model_dump(),
)
```

**What changes**: Route handler `raise` statements (~8 locations).
**What doesn't change**: JWT logic, password hashing, DB queries.

### 3.2 Backend decode_token: Typed Failure

```python
# Before
def decode_token(token: str) -> TokenPayload | None:
    try: ...
    except jwt.PyJWTError: return None  # loses all info

# After
class TokenError(str, Enum):
    EXPIRED = "expired"
    INVALID_SIGNATURE = "invalid_signature"
    MALFORMED = "malformed"

def decode_token(token: str) -> TokenPayload | TokenError:
    try: ...
    except jwt.ExpiredSignatureError: return TokenError.EXPIRED
    except jwt.InvalidSignatureError: return TokenError.INVALID_SIGNATURE
    except jwt.PyJWTError: return TokenError.MALFORMED
```

**What changes**: Return type of `decode_token`, callers check `isinstance` instead of `is None`.
**What doesn't change**: JWT signing, key management.

### 3.3 Frontend AuthResult (TypeScript)

Replace `Promise<User | null>` + `throw` with a tagged union:

```typescript
// frontend/src/core/auth/types.ts

export type AuthResult =
  | { tag: "authenticated"; user: User }
  | { tag: "unauthenticated" }
  | { tag: "gateway_unavailable" }
  | { tag: "config_error"; message: string };

// Exhaustiveness helper
export function assertNever(x: never): never {
  throw new Error(`Unexpected auth result: ${JSON.stringify(x)}`);
}
```

**Usage in server.ts**:

```typescript
// Before
export async function getServerSideUser(): Promise<User | null> { ... }
// Callers: try/catch + instanceof + gatewayError boolean

// After
export async function getServerSideUser(): Promise<AuthResult> {
  // Same internal logic, different return wrapping:
  // return { tag: "authenticated", user }
  // return { tag: "unauthenticated" }
  // return { tag: "gateway_unavailable" }
  // return { tag: "config_error", message: "..." }
}
```

**Usage in layouts**:

```typescript
// Before: 15 lines of try/catch/instanceof/boolean
const result = await getServerSideUser();
switch (result.tag) {
  case "authenticated":
    return <AuthProvider initialUser={result.user}><WorkspaceContent>{children}</WorkspaceContent></AuthProvider>;
  case "unauthenticated":
    redirect("/login");
  case "gateway_unavailable":
    return <DegradedPage />;
  case "config_error":
    throw new Error(result.message); // surfaces as 500
  default:
    assertNever(result); // compiler error if new tag added but not handled
}
```

**What changes**: Return type of `getServerSideUser`, layout call sites (~2 files).
**What doesn't change**: Fetch logic, cookie handling, timeout behavior.

### 3.4 Frontend Error Response Parsing

```typescript
// frontend/src/core/auth/types.ts

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

// Parse backend error response
export function parseAuthError(data: unknown): AuthErrorResponse {
  // validate shape, fallback to generic
}
```

**What changes**: Login page error display uses `error.code` switch instead of `data.detail` string.
**What doesn't change**: Form submission logic, redirect behavior.

---

## 4. Design: Typed Configuration

### 4.1 Backend AuthConfig

Parse all auth-related env vars once at startup into a typed config:

```python
# backend/app/core/auth/config.py (enhance existing)

from pydantic import BaseModel, field_validator
from typing import Literal


class AuthConfig(BaseModel):
    """Parsed, validated auth configuration. Created once at startup."""
    env: Literal["development", "production"]
    cookie_secure: bool
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expiry_days: int = 7

    @field_validator("cookie_secure")
    @classmethod
    def enforce_secure_in_prod(cls, v, info):
        if info.data.get("env") == "production" and not v:
            raise ValueError("cookie_secure must be True in production")
        return v

    @classmethod
    def from_env(cls) -> "AuthConfig":
        """Parse from environment. Fails fast on invalid config."""
        env = os.environ.get("ENV", "production").lower()
        if env in ("development", "dev", "local"):
            env = "development"
        else:
            env = "production"
        return cls(
            env=env,
            cookie_secure=os.environ.get("AUTH_COOKIE_SECURE", "true").lower() != "false",
            jwt_secret=get_jwt_secret(),
            # ...
        )
```

**What changes**: Auth routes read from `AuthConfig` instance instead of inline `os.environ.get()`.
**What doesn't change**: Env var names, JWT logic, cookie logic.

### 4.2 Frontend Gateway Config

Use Zod to parse at module load time:

```typescript
// frontend/src/core/auth/config.ts

import { z } from "zod";

const gatewayConfigSchema = z.object({
  internalGatewayUrl: z.string().url(),
  trustedOrigins: z.array(z.string().url()).min(1),
});

export type GatewayConfig = z.infer<typeof gatewayConfigSchema>;

export function parseGatewayConfig(): GatewayConfig {
  const isDev = process.env.NODE_ENV === "development";

  const rawUrl = process.env.DEER_FLOW_INTERNAL_GATEWAY_BASE_URL?.trim();
  const internalGatewayUrl = rawUrl || (isDev ? "http://localhost:8001" : undefined);

  const rawOrigins = process.env.DEER_FLOW_TRUSTED_ORIGINS?.trim();
  const trustedOrigins = rawOrigins
    ? rawOrigins.split(",").map(s => s.trim()).filter(Boolean)
    : isDev ? ["http://localhost:3000"] : undefined;

  return gatewayConfigSchema.parse({ internalGatewayUrl, trustedOrigins });
  // Throws ZodError with details if invalid — surfaces as startup crash
}
```

**What changes**: `getInternalGatewayURL()` → `config.internalGatewayUrl`. CSRF reads `config.trustedOrigins`.
**What doesn't change**: Fetch logic, proxy logic, rewrite rules.

---

## 5. Design: Typed Trust Boundaries

### 5.1 UserResponse Preserves Role Type

```python
# Before
class UserResponse(BaseModel):
    system_role: str  # forgetful functor: Literal → str

# After
class UserResponse(BaseModel):
    system_role: Literal["admin", "user"]  # faithful functor
```

```typescript
// Before (frontend)
interface User { system_role: string }

// After
interface User { system_role: "admin" | "user" }
```

**One-line change on each side.** Enables exhaustive switch on role.

### 5.2 Token Not Returned in Response Body

RFC-001 says: "不将 JWT 显式注入前端 state"。Current code returns token in JSON body:

```python
# Before
return TokenResponse(access_token=token, expires_in=7 * 24 * 3600)

# After — token only lives in HttpOnly cookie
class LoginResponse(BaseModel):
    expires_in: int

return LoginResponse(expires_in=7 * 24 * 3600)
```

**What changes**: Response model (1 file). Frontend login handler ignores token field.
**What doesn't change**: Cookie setting, JWT generation.

### 5.3 CSRF Middleware Registration (Release-Gating)

**Critical bug**: `CSRFMiddleware` is defined but never registered in `app.py`. Frontend proxy has ad-hoc Origin checks, but gateway endpoints (`/api/v1/*`) have **zero** CSRF protection.

```python
# backend/app/gateway/app.py — add before CORS middleware
from app.gateway.csrf_middleware import CSRFMiddleware
app.add_middleware(CSRFMiddleware)
```

Additionally, fix path matching in `csrf_middleware.py`:
- Current `is_auth_endpoint()` checks `/api/v1/auth/login` but actual route is `/api/v1/auth/login/local`
- Align exemption paths with actual router prefix definitions (single source of truth from `AuthConfig`)

**Release gate**: This must be implemented and tested before merge. Not follow-up work.

**What changes**: 1 line in `app.py`, path alignment in `csrf_middleware.py`.
**What doesn't change**: Middleware implementation logic.

### 5.4 SSR Auth Response Validation (Parse Don't Validate at Trust Boundary)

**Finding**: `getServerSideUser()` casts `res.json() as User` with no runtime validation. If gateway returns malformed data (version skew, partial deploy, error envelope with 200), auth context is silently corrupted.

```typescript
// frontend/src/core/auth/types.ts — add Zod schema for User

import { z } from "zod";

export const userSchema = z.object({
  id: z.string(),
  email: z.string().email(),
  system_role: z.enum(["admin", "user"]),
});

export type User = z.infer<typeof userSchema>;
```

```typescript
// In getServerSideUser():

// Before
return (await res.json()) as User;

// After — parse, don't validate
const parsed = userSchema.safeParse(await res.json());
if (!parsed.success) {
  console.error("[SSR auth] Malformed /auth/me response:", parsed.error);
  return { tag: "gateway_unavailable" };  // treat as degraded, not authenticated
}
return { tag: "authenticated", user: parsed.data };
```

**What changes**: One `as User` cast → Zod parse. `User` type derived from schema (single source of truth).
**What doesn't change**: Fetch logic, cookie handling.

### 5.5 Auth Layout: Non-Interactive Degraded State

**Finding**: Auth layout fail-opens to interactive login form on gateway outage. Users with valid sessions can submit credentials against degraded backend, causing state confusion.

```typescript
// Auth layout on gateway_unavailable:

// Before — shows login form (interactive, unsafe)
return <AuthProvider initialUser={null}>{children}</AuthProvider>;

// After — shows non-interactive retry page (consistent with workspace)
return (
  <div className="flex h-screen flex-col items-center justify-center gap-4">
    <p className="text-muted-foreground">Service temporarily unavailable.</p>
    <a href="/login" className="...">Retry</a>
  </div>
);
```

**Principle**: On indeterminate auth state, never present credential input. A retry link is safe; a login form is not.

**What changes**: Auth layout degraded branch (~5 lines).
**What doesn't change**: Normal login flow, AuthProvider logic.

### 5.6 Workspace Degraded Page: Deterministic Recovery Path

**Finding (R3 reliability)**: When gateway persistently returns 5xx but the `access_token` cookie hasn't expired, users loop between retry and degraded page with no escape. The cookie prevents redirect to login (since it's present), but the gateway can't validate it.

**Principle**: Every error state must have a deterministic recovery path. Never strand the user.

```typescript
// Workspace degraded page — add explicit logout action
if (gatewayError) {
  return (
    <div className="flex h-screen flex-col items-center justify-center gap-4">
      <p className="text-muted-foreground">Service temporarily unavailable.</p>
      <p className="text-muted-foreground text-xs">
        The backend may be restarting. Please wait a moment and try again.
      </p>
      <div className="flex gap-3">
        <a href="/workspace" className="...">Retry</a>
        <a href="/api/v1/auth/logout" className="...">Logout & Reset</a>
      </div>
    </div>
  );
}
```

The "Logout & Reset" link hits the backend logout endpoint (clears cookie) and redirects to `/login`. If even that fails, the user can manually clear cookies. This breaks the loop by providing a hard session reset.

**What changes**: Workspace layout degraded branch — replace "Go to Login" with "Logout & Reset" (~1 line).
**What doesn't change**: Normal workspace flow, AuthProvider logic.

---

## 6. Design: Declarative Proxy Policy

Replace scattered imperative checks with a single policy declaration:

```typescript
// frontend/src/core/auth/proxy-policy.ts

export interface ProxyPolicy {
  /** Allowed upstream path prefixes */
  allowedPaths: readonly string[];
  /** Request headers to strip before forwarding */
  strippedRequestHeaders: ReadonlySet<string>;
  /** Response headers to strip before returning */
  strippedResponseHeaders: ReadonlySet<string>;
  /** Credential mode: which cookie(s) to forward */
  credential: { type: "cookie"; name: string };
  /** Timeout in ms */
  timeoutMs: number;
  /** CSRF: required for non-GET/HEAD, validated against config.trustedOrigins */
  csrf: boolean;
}

export const LANGGRAPH_COMPAT_POLICY: ProxyPolicy = {
  allowedPaths: ["threads", "runs", "assistants", "store", "models", "mcp", "skills", "memory"],
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
};
```

**Usage**: The proxy route handler becomes a generic `applyPolicy(req, policy, config)` function. All security decisions are in the policy object, not in procedural code. Adding a new endpoint = adding a string to `allowedPaths`, not editing proxy logic.

**What changes**: Proxy route handler refactored to read from policy object.
**What doesn't change**: Actual fetch/streaming logic, Next.js route structure.

### 6.2 Eliminate Catch-All Rewrite (Deny-by-Default Routing)

**Finding**: `next.config.js` has a catch-all `/api/:path*` fallback that bypasses all frontend security policy (allowlist, header stripping, CSRF) for any API path not matched by a route handler. This creates an implicit backend exposure.

**Principle**: Deny-by-default. Every proxied API path must be explicitly declared.

```javascript
// Before — catch-all in fallback
fallback.push({
  source: "/api/:path*",
  destination: `${gatewayURL}/api/:path*`,
});

// After — explicit enumeration only
const GATEWAY_API_PREFIXES = ["agents", "models", "threads", "memory", "skills", "mcp"];
for (const prefix of GATEWAY_API_PREFIXES) {
  beforeFiles.push({
    source: `/api/${prefix}`,
    destination: `${gatewayURL}/api/${prefix}`,
  });
  beforeFiles.push({
    source: `/api/${prefix}/:path*`,
    destination: `${gatewayURL}/api/${prefix}/:path*`,
  });
}
// No catch-all. Unknown paths → 404.
```

This list can be derived from the same source as `ProxyPolicy.allowedPaths` or a shared config constant.

### 6.3 `/api/v1/:path*` Rewrite: Also Deny-by-Default

**Finding (R2 trust boundaries)**: The unconditional `/api/v1/:path*` → gateway rewrite is equally broad. Any new `v1` endpoint on the backend is automatically exposed through browser credentials without explicit review.

```javascript
// Before — blanket v1 rewrite
beforeFiles.push({
  source: "/api/v1/:path*",
  destination: `${gatewayURL}/api/v1/:path*`,
});

// After — explicit auth prefix only
const V1_API_PREFIXES = ["auth"];
for (const prefix of V1_API_PREFIXES) {
  beforeFiles.push({
    source: `/api/v1/${prefix}/:path*`,
    destination: `${gatewayURL}/api/v1/${prefix}/:path*`,
  });
}
```

Currently only `auth` lives under `/api/v1/`. If new v1 prefixes are added, they require explicit registration here — deny-by-default.

**What changes**: `next.config.js` v1 rewrite section (~5 lines).
**What doesn't change**: Auth route behavior, backend routes.

---

## 7. Migration Strategy

### Phase 1: Types (no behavior change)
1. Add `errors.py` with `AuthErrorCode` enum and `AuthErrorResponse` model
2. Add `frontend/src/core/auth/types.ts` with `AuthResult`, `AuthErrorCode`, `userSchema` (Zod)
3. Add `proxy-policy.ts` with `ProxyPolicy` type and `LANGGRAPH_COMPAT_POLICY`
4. Enhance `AuthConfig` with Pydantic validation
5. Add `GatewayConfig` with Zod schema
6. Fix `UserResponse.system_role` to `Literal["admin", "user"]` on both sides
7. Define `User` type from Zod schema (single source of truth)

### Phase 2: Wire types to boundaries (behavior improves)
8. `decode_token` returns `TokenPayload | TokenError` instead of `TokenPayload | None`
9. Auth route `HTTPException` uses `AuthErrorResponse` detail
10. `getServerSideUser` returns `AuthResult` instead of `User | null` + throw
11. SSR auth validates gateway response with `userSchema.safeParse()` (not bare `as User`)
12. Layout call sites use exhaustive `switch` on `AuthResult.tag`
13. Auth layout renders non-interactive degraded page (not login form) on `gateway_unavailable`
14. Workspace degraded page adds "Logout & Reset" action for deterministic recovery
15. Login page parses error response via `parseAuthError`
16. Proxy route handler reads from `LANGGRAPH_COMPAT_POLICY`
17. CSRF reads from `GatewayConfig.trustedOrigins`
18. Cookie security reads from `AuthConfig`
19. Replace catch-all `/api/:path*` rewrite with explicit prefix enumeration
20. Replace blanket `/api/v1/:path*` rewrite with explicit v1 prefix enumeration

### Phase 3: Activate missing protections (release-gating)
21. Register `CSRFMiddleware` in `app.py`
22. Fix CSRF middleware path matching to align with actual routes (`login/local`, not `login`)
23. Remove `access_token` from login response body
24. Add tests: CSRF coverage, Zod parse rejection, exhaustive switch compilation

### Estimated Impact
- **New files**: 3 (`errors.py`, `types.ts`, `proxy-policy.ts`)
- **Modified files**: ~12 (route handlers, layouts, server.ts, config, proxy, next.config.js, csrf_middleware)
- **Lines changed**: ~450-550
- **Lines of business logic changed**: 0

---

## 8. What This Does NOT Cover

- Agent system, middleware chain, sandbox, tools, MCP, skills, memory
- Database schema changes
- OAuth provider implementation (placeholder routes remain)
- Frontend component refactoring beyond auth boundaries
- Performance optimization
- Test infrastructure (tests should be updated to match new types)

---

## 9. Success Criteria

After implementation, a fresh adversarial review should find:
1. **No implicit trust boundaries** — all trust decisions flow from typed config
2. **No untyped errors** — all auth failures carry `AuthErrorCode`
3. **No stringly-typed config** — all env vars parsed into typed objects at startup
4. **No scattered proxy rules** — all security policy in declarative `ProxyPolicy`
5. **Exhaustive handling** — TypeScript compiler catches unhandled auth states
6. **CSRF active** — middleware registered and path-matching correct
7. **No unvalidated payloads** — SSR auth parses gateway response with Zod, rejects malformed data
8. **No interactive UI on indeterminate state** — auth layout shows retry page, not login form
9. **Deny-by-default routing** — no catch-all rewrite; every proxied API path explicitly declared
10. **Deterministic recovery** — every degraded state has an escape path (logout/reset); no user lockout loops
