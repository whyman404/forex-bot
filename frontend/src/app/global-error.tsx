"use client";

import { useEffect } from "react";

/**
 * Last-resort error boundary that REPLACES the root layout when even the
 * root layout throws. Must include its own <html> and <body>. Renders without
 * Tailwind (no global stylesheet may have loaded) so we inline minimal styles.
 *
 * Vercel automatically forwards `error.digest` to the logs; that's the only
 * server-safe way to correlate the client error to a server trace.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // eslint-disable-next-line no-console
    console.error("[global-error]", error);
    // Forward to Sentry if loaded — best-effort, never throw from here.
    type SentryGlobal = { captureException?: (err: unknown) => void };
    const sentry = (globalThis as unknown as { Sentry?: SentryGlobal }).Sentry;
    sentry?.captureException?.(error);
  }, [error]);

  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: "100dvh",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: "1rem",
          padding: "1.5rem",
          textAlign: "center",
          background: "#0b1220",
          color: "#e5e7eb",
          fontFamily:
            'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
        }}
      >
        <h1 style={{ fontSize: "1.875rem", fontWeight: 700, margin: 0 }}>
          Something went wrong
        </h1>
        <p style={{ maxWidth: "32rem", color: "#9ca3af", margin: 0 }}>
          The app hit an unexpected error. Try again, or contact support if the
          problem persists.
        </p>
        {error.digest && (
          <p
            style={{
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, monospace',
              fontSize: "0.75rem",
              color: "#6b7280",
            }}
          >
            Ref: {error.digest}
          </p>
        )}
        <button
          type="button"
          onClick={reset}
          style={{
            background: "#2563eb",
            color: "white",
            padding: "0.5rem 1rem",
            borderRadius: "0.5rem",
            border: "none",
            cursor: "pointer",
            fontWeight: 600,
          }}
        >
          Try again
        </button>
      </body>
    </html>
  );
}
