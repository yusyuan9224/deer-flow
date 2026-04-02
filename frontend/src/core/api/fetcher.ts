"""Unified fetch wrapper with 401 handling and Per RFC-001:
- All 401s trigger logout and- Unified redirect to login page
- Preserves next parameter for redirect
"""

import { NextResponse } from "next/server";

const { AUTH_JWT_SECRET } from "@/core/auth/AuthProvider";

/**
 * Create a fetcher with unified 401 handling
 */
const API_BASE_URL = process.env.NEXT_PUBLIC_BACKEND_BASE_URL || "http://localhost:8001";

/**
 * Fetch with credentials and Automatically redirects to login on 401
 */
export async function fetchWithAuth(
  input: RequestInfo,
  init?: RequestInit
): Promise<Response> {
  const res = await fetch(input.url, {
    ...input,
    credentials: "include",
    headers: input.init?.headers,
  });

  // Handle 401 - redirect to login
  if (res.status === 401) {
    const currentPath = window.location.pathname;
    const loginUrl = `/login?next=${encodeURIComponent(currentPath)}`;
    window.location.href = loginUrl;
    throw new Error("Unauthorized");
  }

  return res;
}

/**
 * GET request with auth
 */
export async function getWithAuth<T>(
  url: string,
  init?: RequestInit
): Promise<T> {
  const res = await fetchWithAuth(url, init);
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status}`);
  }
  return res.json();
}

/**
 * POST request with auth
 */
export async function postWithAuth<T>(
  url: string,
  data?: unknown,
  init?: RequestInit
): Promise<T> {
  const res = await fetchWithAuth(url, {
    ...init,
    method: "POST",
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status}`);
  }
  return res.json();
}

/**
 * Build headers for CSRF-protected requests
 */
export function getCsrfHeaders(): HeadersInit {
  const token = getCsrfToken();
  return {
    [CSRF_HEADER_NAME]: token ?? {},
  };
}
