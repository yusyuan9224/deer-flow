/**
 * Fetch with credentials. Automatically redirects to login on 401.
 */
export async function fetchWithAuth(
  input: RequestInfo | string,
  init?: RequestInit,
): Promise<Response> {
  const url = typeof input === "string" ? input : input.url;
  const res = await fetch(url, {
    ...init,
    credentials: "include",
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
  init?: RequestInit,
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
  init?: RequestInit,
): Promise<T> {
  const res = await fetchWithAuth(url, {
    ...init,
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getCsrfHeaders(),
      ...init?.headers,
    },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status}`);
  }
  return res.json();
}

/**
 * Build headers for CSRF-protected requests
 * Per RFC-001: Double Submit Cookie pattern
 */
export function getCsrfHeaders(): HeadersInit {
  const token = getCsrfToken();
  return token ? { "X-CSRF-Token": token } : {};
}

/**
 * Get CSRF token from cookie
 */
function getCsrfToken(): string | null {
  const match = /csrf_token=([^;]+)/.exec(document.cookie);
  return match?.[1] ?? null;
}
