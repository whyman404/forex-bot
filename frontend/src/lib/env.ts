import { z } from "zod";

/**
 * Type-safe env. Validated on first import — build fails loudly when required
 * vars are missing instead of crashing at runtime.
 *
 * - `NEXT_PUBLIC_*` vars are embedded at build time and accessible client-side.
 * - All other vars are server-only and read directly via `process.env.X`.
 *
 * On Vercel:
 *   - `VERCEL_URL` is auto-injected on every deployment (host without scheme).
 *   - `VERCEL_ENV` ∈ {"production","preview","development"}.
 *   - Set NEXTAUTH_URL + NEXTAUTH_SECRET manually in the Vercel dashboard.
 */

const truthy = z
  .string()
  .default("false")
  .transform((v) => v === "true" || v === "1");

const publicSchema = z.object({
  NEXT_PUBLIC_API_URL: z.string().url().default("http://localhost:8000/api/v1"),
  NEXT_PUBLIC_WS_URL: z.string().default("ws://localhost:8000/ws"),
  // Base URL is used for Stripe success/cancel and OG image absolute URLs.
  // Falls back to window.location.origin on the client.
  NEXT_PUBLIC_BASE_URL: z.string().url().optional(),
  NEXT_PUBLIC_DEV_MODE: truthy,
  NEXT_PUBLIC_ENABLE_LIVE_TRADING: truthy,
  NEXT_PUBLIC_ENABLE_BINANCE: truthy,
  NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY: z.string().optional(),
  NEXT_PUBLIC_SENTRY_DSN: z.string().optional(),
  NEXT_PUBLIC_POSTHOG_KEY: z.string().optional(),
});

const rawPublic = {
  NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  NEXT_PUBLIC_WS_URL: process.env.NEXT_PUBLIC_WS_URL,
  NEXT_PUBLIC_BASE_URL: process.env.NEXT_PUBLIC_BASE_URL,
  NEXT_PUBLIC_DEV_MODE: process.env.NEXT_PUBLIC_DEV_MODE,
  NEXT_PUBLIC_ENABLE_LIVE_TRADING: process.env.NEXT_PUBLIC_ENABLE_LIVE_TRADING,
  NEXT_PUBLIC_ENABLE_BINANCE: process.env.NEXT_PUBLIC_ENABLE_BINANCE,
  NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY: process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY,
  NEXT_PUBLIC_SENTRY_DSN: process.env.NEXT_PUBLIC_SENTRY_DSN,
  NEXT_PUBLIC_POSTHOG_KEY: process.env.NEXT_PUBLIC_POSTHOG_KEY,
};

const parsed = publicSchema.safeParse(rawPublic);
if (!parsed.success) {
  const issues = parsed.error.issues
    .map((i) => `  - ${i.path.join(".")}: ${i.message}`)
    .join("\n");
  throw new Error(`Invalid public env vars:\n${issues}`);
}
export const env = parsed.data;
export type Env = typeof env;

/**
 * Server-only env reader. Throws if accessed from the client bundle.
 * Use inside route handlers / server components / server actions only.
 */
export function serverEnv() {
  if (typeof window !== "undefined") {
    throw new Error("serverEnv() called from the browser — server-only");
  }
  const schema = z.object({
    NEXTAUTH_URL: z.string().url().optional(),
    NEXTAUTH_SECRET: z.string().min(16, "NEXTAUTH_SECRET must be set to a strong value (>=16 chars)"),
    API_URL_INTERNAL: z.string().url().optional(),
    SENTRY_DSN: z.string().optional(),
    SENTRY_ENV: z.string().optional(),
  });
  const out = schema.safeParse({
    NEXTAUTH_URL: process.env.NEXTAUTH_URL,
    NEXTAUTH_SECRET: process.env.NEXTAUTH_SECRET,
    API_URL_INTERNAL: process.env.API_URL_INTERNAL,
    SENTRY_DSN: process.env.SENTRY_DSN,
    SENTRY_ENV: process.env.SENTRY_ENV,
  });
  if (!out.success) {
    const issues = out.error.issues
      .map((i) => `  - ${i.path.join(".")}: ${i.message}`)
      .join("\n");
    throw new Error(`Invalid server env vars:\n${issues}`);
  }
  return out.data;
}

/**
 * Resolve the canonical base URL across environments.
 *  - Browser: prefer NEXT_PUBLIC_BASE_URL, else current origin.
 *  - Server: NEXT_PUBLIC_BASE_URL → NEXTAUTH_URL → https://VERCEL_URL → http://localhost:3000.
 */
export function resolveBaseUrl(): string {
  if (env.NEXT_PUBLIC_BASE_URL) return env.NEXT_PUBLIC_BASE_URL;
  if (typeof window !== "undefined") return window.location.origin;
  if (process.env.NEXTAUTH_URL) return process.env.NEXTAUTH_URL;
  if (process.env.VERCEL_URL) return `https://${process.env.VERCEL_URL}`;
  return "http://localhost:3000";
}

export const isProduction = process.env.NODE_ENV === "production";
export const isVercel = Boolean(process.env.VERCEL);
export const vercelEnv = process.env.VERCEL_ENV as "production" | "preview" | "development" | undefined;
