/**
 * API client for the Django backend.
 *
 * Everything goes through the Next rewrites proxy at /api, so the browser
 * only ever sees one origin: no CORS, and the session cookie is sent
 * normally. These helpers must run in the browser — a Server Component has
 * no access to the user's cookie.
 */

export class ApiError extends Error {
  readonly status: number;
  readonly data: unknown;

  constructor(status: number, message: string, data?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

export interface User {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  role: "manager" | "operator";
  is_manager: boolean;
}

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(^|;\\s*)${name}=([^;]*)`));
  return match ? decodeURIComponent(match[2]) : null;
}

/** Ensure the csrftoken cookie exists, and return it. */
async function ensureCsrfToken(): Promise<string> {
  const existing = readCookie("csrftoken");
  if (existing) return existing;

  await fetch("/api/auth/csrf/", { credentials: "include" });
  const token = readCookie("csrftoken");
  if (!token) {
    throw new ApiError(0, "Could not obtain a CSRF token.");
  }
  return token;
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase();
  const headers = new Headers(options.headers);

  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (UNSAFE_METHODS.has(method)) {
    // Django rejects unsafe requests without this, and the resulting 403
    // looks exactly like a login failure.
    headers.set("X-CSRFToken", await ensureCsrfToken());
  }

  const response = await fetch(path, {
    ...options,
    method,
    headers,
    // Without this the session cookie is not sent and every call 403s.
    credentials: "include",
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const isJson = response.headers
    .get("Content-Type")
    ?.includes("application/json");
  const payload = isJson ? await response.json() : await response.text();

  if (!response.ok) {
    const detail =
      (isJson && (payload as { detail?: string })?.detail) ||
      `Request failed (${response.status})`;
    throw new ApiError(response.status, detail, payload);
  }

  return payload as T;
}

export const auth = {
  login: (username: string, password: string) =>
    apiFetch<User>("/api/auth/login/", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),

  logout: () => apiFetch<void>("/api/auth/logout/", { method: "POST" }),

  me: () => apiFetch<User>("/api/auth/me/"),
};
