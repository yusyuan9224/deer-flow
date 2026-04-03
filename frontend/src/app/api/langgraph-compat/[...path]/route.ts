/**
 * Streaming proxy for LangGraph-compat API.
 *
 * Security policy is declarative via ProxyPolicy — no inline constants.
 * All trust decisions flow from GatewayConfig (Zod-validated).
 */

import { cookies } from "next/headers";
import { type NextRequest, NextResponse } from "next/server";

import { getGatewayConfig } from "@/core/auth/gateway-config";
import {
  LANGGRAPH_COMPAT_POLICY,
  type ProxyPolicy,
} from "@/core/auth/proxy-policy";

// ── Helpers ─────────────────────────────────────────────────────────

function normalizeOrigin(o: string): string {
  try {
    const u = new URL(o);
    const isDefaultPort =
      (u.protocol === "https:" && u.port === "443") ||
      (u.protocol === "http:" && u.port === "80");
    return `${u.protocol}//${u.hostname}${u.port && !isDefaultPort ? `:${u.port}` : ""}`;
  } catch {
    return o.toLowerCase();
  }
}

// ── Policy-driven proxy ─────────────────────────────────────────────

async function applyPolicy(
  req: NextRequest,
  path: string[],
  policy: ProxyPolicy,
) {
  const config = getGatewayConfig();
  const upstreamPath = path.join("/");

  // 1. Path allowlist
  const isAllowed = policy.allowedPaths.some(
    (prefix) =>
      upstreamPath === prefix || upstreamPath.startsWith(`${prefix}/`),
  );
  if (!isAllowed) {
    return NextResponse.json(
      { error: `Path not allowed: ${upstreamPath}` },
      { status: 403 },
    );
  }

  // 2. CSRF for mutating methods
  if (policy.csrf && req.method !== "GET" && req.method !== "HEAD") {
    const origin = req.headers.get("origin");
    if (!origin) {
      return NextResponse.json(
        { error: "CSRF validation failed: missing Origin header" },
        { status: 403 },
      );
    }
    const trustedSet = new Set(config.trustedOrigins.map(normalizeOrigin));
    if (!trustedSet.has(normalizeOrigin(origin))) {
      console.warn(
        `[CSRF] Rejected origin=${origin}, trusted=${[...trustedSet].join(",")}`,
      );
      return NextResponse.json(
        { error: "CSRF validation failed: Origin mismatch" },
        { status: 403 },
      );
    }
  }

  // 3. Reject client-supplied auth credentials (cookie-only auth)
  const hasAuthHeader = Array.from(req.headers.keys()).some((k) => {
    const lower = k.toLowerCase();
    return lower === "authorization" || lower === "x-api-key";
  });
  if (hasAuthHeader) {
    return NextResponse.json(
      {
        error:
          "This proxy does not accept Authorization or X-API-Key headers. Use session cookie auth.",
      },
      { status: 400 },
    );
  }

  // 4. Build upstream URL
  const search = req.nextUrl.search;
  const upstreamURL = `${config.internalGatewayUrl}/api/${upstreamPath}${search}`;

  // 5. Build request headers (strip per policy)
  const cookieStore = await cookies();
  const credentialCookie = cookieStore.get(policy.credential.name);

  const headers = new Headers();
  for (const [key, value] of req.headers.entries()) {
    if (!policy.strippedRequestHeaders.has(key.toLowerCase())) {
      headers.set(key, value);
    }
  }
  if (credentialCookie) {
    headers.set(
      "cookie",
      `${policy.credential.name}=${credentialCookie.value}`,
    );
  } else {
    headers.delete("cookie");
  }

  // 6. Stream body (no buffering)
  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  const body = hasBody ? req.body : undefined;
  if (hasBody) {
    headers.delete("content-length");
  }

  // 7. Fetch with timeout
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), policy.timeoutMs);

  let upstream: Response;
  try {
    upstream = await fetch(upstreamURL, {
      method: req.method,
      headers,
      body,
      signal: controller.signal,
      // @ts-expect-error - Node.js fetch supports duplex for streaming
      duplex: "half",
    });
  } catch (err) {
    clearTimeout(timeout);
    if (err instanceof DOMException && err.name === "AbortError") {
      return NextResponse.json(
        { error: "Upstream request timed out" },
        { status: 504 },
      );
    }
    return NextResponse.json(
      { error: "Upstream request failed" },
      { status: 502 },
    );
  }
  clearTimeout(timeout);

  // 8. Build response headers (strip per policy)
  const responseHeaders = new Headers();
  for (const [key, value] of upstream.headers.entries()) {
    if (!policy.strippedResponseHeaders.has(key)) {
      responseHeaders.set(key, value);
    }
  }
  responseHeaders.set("x-accel-buffering", "no");
  responseHeaders.set("cache-control", "no-cache");

  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

// ── Route handlers ──────────────────────────────────────────────────

function handler(req: NextRequest, params: Promise<{ path: string[] }>) {
  return params.then((p) => applyPolicy(req, p.path, LANGGRAPH_COMPAT_POLICY));
}

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  return handler(req, params);
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  return handler(req, params);
}

export async function PUT(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  return handler(req, params);
}

export async function DELETE(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  return handler(req, params);
}

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  return handler(req, params);
}
