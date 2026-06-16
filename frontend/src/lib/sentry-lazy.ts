/**
 * Lazy Sentry browser initialiser. We don't ship `@sentry/nextjs` by default
 * (extra ~80KB) — when SENTRY_DSN is set at build time, callers can opt in
 * by importing `initSentry()` from the providers tree.
 *
 * The function is a no-op when:
 *  - NEXT_PUBLIC_SENTRY_DSN is unset
 *  - Already initialised (idempotent)
 *  - SSR (only run in the browser)
 *
 * Tags `environment` from VERCEL_ENV so Sentry separates preview vs production.
 */

import { env, isProduction, vercelEnv } from "@/lib/env";

let initialised = false;

type SentryLike = {
  init: (options: Record<string, unknown>) => void;
  captureException?: (err: unknown) => void;
};

declare global {
  // eslint-disable-next-line no-var
  var Sentry: SentryLike | undefined;
}

export async function initSentry(): Promise<void> {
  if (initialised) return;
  if (typeof window === "undefined") return;
  if (!env.NEXT_PUBLIC_SENTRY_DSN) return;

  try {
    // Dynamic import keeps Sentry out of the main chunk.
    // Consumers must install @sentry/browser to opt-in. The string-literal
    // import below is wrapped through a computed expression so TypeScript
    // does NOT require the package to be present at compile time — we
    // gracefully no-op when it isn't installed.
    const moduleName = "@sentry/browser";
    const sentryModule = (await import(/* @vite-ignore */ /* webpackIgnore: true */ moduleName).catch(
      () => null,
    )) as { init?: SentryLike["init"]; captureException?: SentryLike["captureException"] } | null;

    if (!sentryModule || typeof sentryModule.init !== "function") {
      // Module not installed — keep the lazy hook silent in dev too.
      return;
    }

    sentryModule.init({
      dsn: env.NEXT_PUBLIC_SENTRY_DSN,
      environment: vercelEnv ?? (isProduction ? "production" : "development"),
      tracesSampleRate: isProduction ? 0.1 : 0,
      // Replay is opt-in for cost reasons.
      replaysSessionSampleRate: 0,
      replaysOnErrorSampleRate: isProduction ? 0.1 : 0,
      release: process.env.NEXT_PUBLIC_VERCEL_GIT_COMMIT_SHA ?? undefined,
    });
    globalThis.Sentry = {
      init: sentryModule.init,
      captureException: sentryModule.captureException,
    };
    initialised = true;
  } catch (err) {
    // Never let Sentry init break the app.
    // eslint-disable-next-line no-console
    console.warn("[sentry] init failed", err);
  }
}
