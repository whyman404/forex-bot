/**
 * Production-grade fetch wrapper for the Forex Bot API.
 *
 * Contract: docs/api/openapi.yaml (Atlas Goro).
 * All errors return the `ErrorResponse { error: { code, message, details?, traceId? } }` shape.
 *
 * Features:
 *  - Bearer token attached from NextAuth session (caller passes `token`).
 *  - 401 surfaces ApiError with code AUTH_*, callers can trigger refresh upstream.
 *  - 429 exposes Retry-After in ApiError.details.retryAfter.
 *  - 5xx is retried once with linear backoff.
 *  - Returns typed Promise<T>.
 *
 * Vercel notes:
 *  - On the server (Server Components / Route Handlers / Server Actions) we
 *    prefer `API_URL_INTERNAL` if set — useful when both frontend and API
 *    live on the same private network (not our case today, but kept flexible).
 *    Falls back to the public NEXT_PUBLIC_API_URL otherwise.
 *  - `credentials: "include"` is set globally so future cookie-based ops work
 *    cross-origin. The backend MUST respond with `Access-Control-Allow-Origin`
 *    matching the deployment URL AND `Access-Control-Allow-Credentials: true`.
 *    Otherwise the browser drops the cookies silently.
 *  - We never throw on CORS preflight failures — surface them as
 *    `NETWORK_ERROR` so the UI shows a clean "could not reach API" toast
 *    instead of an opaque exception in DevTools.
 */

import { env } from "@/lib/env";

export interface ApiErrorDetails {
  [key: string]: unknown;
  retryAfter?: number;
  traceId?: string;
}

export class ApiError extends Error {
  public readonly status: number;
  public readonly code: string;
  public readonly details?: ApiErrorDetails;

  constructor(message: string, status: number, code: string, details?: ApiErrorDetails) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  get isUnauthorized(): boolean {
    return this.status === 401;
  }
  get isForbidden(): boolean {
    return this.status === 403;
  }
  get isValidation(): boolean {
    return this.status === 422;
  }
  get isRateLimited(): boolean {
    return this.status === 429;
  }
  get isServerError(): boolean {
    return this.status >= 500;
  }
  get isPaymentRequired(): boolean {
    return this.status === 402;
  }
  get isNetworkError(): boolean {
    return this.status === 0 || this.code === "NETWORK_ERROR";
  }
}

/**
 * The request body shape — any JSON-serialisable value. We intentionally use
 * `object` instead of `Record<string, unknown>` so callers can pass strongly
 * typed request DTOs (e.g. `CheckoutSessionRequest`) without first widening
 * them via `as unknown as Record<string, unknown>`.
 */
type Json = object | unknown[] | null;

export type FetchOptions = Omit<RequestInit, "body" | "method"> & {
  body?: Json | FormData;
  token?: string | null;
  /** Disable the built-in single retry for idempotent server failures */
  noRetry?: boolean;
  /** Query string parameters, will be encoded */
  query?: Record<string, string | number | boolean | undefined | null>;
  /** Override the default base URL — useful for absolute external calls */
  baseUrl?: string;
};

/**
 * Resolve the API base URL.
 *  - Browser: always use NEXT_PUBLIC_API_URL (Railway public URL).
 *  - Server: prefer API_URL_INTERNAL when set, else NEXT_PUBLIC_API_URL.
 */
export function apiBaseUrl(): string {
  if (typeof window === "undefined" && process.env.API_URL_INTERNAL) {
    return process.env.API_URL_INTERNAL;
  }
  return env.NEXT_PUBLIC_API_URL;
}

function buildUrl(path: string, query?: FetchOptions["query"], baseUrl?: string): string {
  const base = path.startsWith("http") ? path : `${baseUrl ?? apiBaseUrl()}${path}`;
  if (!query) return base;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null) continue;
    params.append(k, String(v));
  }
  const q = params.toString();
  return q ? `${base}${base.includes("?") ? "&" : "?"}${q}` : base;
}

async function parseError(res: Response): Promise<ApiError> {
  const ct = res.headers.get("content-type") ?? "";
  let code = `HTTP_${res.status}`;
  let message = res.statusText || `Request failed with status ${res.status}`;
  let details: ApiErrorDetails | undefined;

  if (ct.includes("application/json")) {
    try {
      const body = (await res.json()) as {
        error?: { code?: string; message?: string; details?: Record<string, unknown>; traceId?: string };
      };
      if (body?.error) {
        code = body.error.code ?? code;
        message = body.error.message ?? message;
        details = { ...(body.error.details ?? {}) };
        if (body.error.traceId) details.traceId = body.error.traceId;
      }
    } catch {
      /* swallow malformed JSON */
    }
  }

  if (res.status === 429) {
    const retryAfter = Number(res.headers.get("Retry-After"));
    details = { ...(details ?? {}), retryAfter: Number.isFinite(retryAfter) ? retryAfter : 30 };
  }

  return new ApiError(message, res.status, code, details);
}

async function request<T>(
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE",
  path: string,
  opts: FetchOptions = {},
): Promise<T> {
  const { body, token, headers, query, noRetry, signal, baseUrl, credentials, ...rest } = opts;

  const finalHeaders: Record<string, string> = {
    Accept: "application/json",
    ...(headers as Record<string, string>),
  };
  if (body !== undefined && !(body instanceof FormData)) {
    finalHeaders["Content-Type"] = "application/json";
  }
  if (token) {
    finalHeaders.Authorization = `Bearer ${token}`;
  }

  const url = buildUrl(path, query, baseUrl);
  const init: RequestInit = {
    ...rest,
    method,
    headers: finalHeaders,
    signal,
    // Default to including credentials so future session-cookie ops work
    // cross-origin. Atlas's CORS must allow our deployment origin + credentials.
    credentials: credentials ?? "include",
    body:
      body === undefined
        ? undefined
        : body instanceof FormData
          ? body
          : JSON.stringify(body),
  };

  let res: Response;
  try {
    res = await fetch(url, init);
  } catch (err) {
    // CORS preflight failures and offline/DNS errors land here.
    throw new ApiError(
      err instanceof Error ? err.message : "Network error",
      0,
      "NETWORK_ERROR",
    );
  }

  // Single retry for 5xx on idempotent (or explicitly retriable) requests.
  if (res.status >= 500 && !noRetry && method !== "POST") {
    await new Promise((r) => setTimeout(r, 400));
    try {
      res = await fetch(url, init);
    } catch (err) {
      throw new ApiError(
        err instanceof Error ? err.message : "Network error",
        0,
        "NETWORK_ERROR",
      );
    }
  }

  if (res.status === 204) {
    return undefined as T;
  }

  if (!res.ok) {
    throw await parseError(res);
  }

  const ct = res.headers.get("content-type") ?? "";
  if (ct.includes("application/json")) {
    return (await res.json()) as T;
  }
  return (await res.text()) as unknown as T;
}

export const api = {
  get: <T>(path: string, opts?: FetchOptions) => request<T>("GET", path, opts),
  post: <T, B extends Json | FormData | undefined = Json>(
    path: string,
    body?: B,
    opts?: FetchOptions,
  ) => request<T>("POST", path, { ...opts, body: body as FetchOptions["body"] }),
  put: <T, B extends Json | FormData | undefined = Json>(
    path: string,
    body?: B,
    opts?: FetchOptions,
  ) => request<T>("PUT", path, { ...opts, body: body as FetchOptions["body"] }),
  patch: <T, B extends Json | FormData | undefined = Json>(
    path: string,
    body?: B,
    opts?: FetchOptions,
  ) => request<T>("PATCH", path, { ...opts, body: body as FetchOptions["body"] }),
  delete: <T>(path: string, opts?: FetchOptions) => request<T>("DELETE", path, opts),
};
