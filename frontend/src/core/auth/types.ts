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
  | "provider_not_found"
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
    "provider_not_found",
    "not_authenticated",
  ]),
  message: z.string(),
});

export function parseAuthError(data: unknown): AuthErrorResponse {
  const parsed = authErrorSchema.safeParse(data);
  if (parsed.success) return parsed.data;
  // Fallback for legacy string-detail responses
  const detail =
    typeof data === "object" &&
    data !== null &&
    "detail" in data &&
    typeof (data as Record<string, unknown>).detail === "string"
      ? ((data as Record<string, unknown>).detail as string)
      : "Authentication failed";
  return { code: "invalid_credentials", message: detail };
}
