import { ImageResponse } from "next/og";

// Edge runtime keeps cold-start near-zero on Vercel.
export const runtime = "edge";
export const alt = "Forex Bot — Automated trading bot platform";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

/**
 * Default Open Graph image used by social cards (Twitter/X, LinkedIn,
 * Slack unfurl, iMessage preview, etc). Rendered on the edge via
 * Vercel's @vercel/og — same engine, no extra dependency.
 *
 * Sticks to system fonts so no remote font fetch (faster, more reliable).
 */
export default function OpenGraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: 80,
          background:
            "linear-gradient(135deg, #0b1220 0%, #111c33 55%, #1a2a4f 100%)",
          color: "#f8fafc",
          fontFamily:
            'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div
            style={{
              width: 56,
              height: 56,
              borderRadius: 12,
              background: "linear-gradient(135deg, #2563eb, #38bdf8)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 32,
              fontWeight: 800,
              color: "#fff",
            }}
          >
            FB
          </div>
          <span style={{ fontSize: 28, fontWeight: 600, letterSpacing: -0.5 }}>
            Forex Bot
          </span>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          <h1
            style={{
              fontSize: 80,
              fontWeight: 800,
              lineHeight: 1.05,
              letterSpacing: -2,
              margin: 0,
              maxWidth: 900,
            }}
          >
            Automated trading, without guesswork.
          </h1>
          <p
            style={{
              fontSize: 30,
              color: "#94a3b8",
              margin: 0,
              maxWidth: 880,
              lineHeight: 1.3,
            }}
          >
            Six battle-tested strategies for XAUUSD and BTC. Backtest in seconds.
          </p>
        </div>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-end",
            fontSize: 22,
            color: "#94a3b8",
          }}
        >
          <span>forex-bot.app</span>
          <span style={{ color: "#38bdf8" }}>Phase 1 — paper trading live</span>
        </div>
      </div>
    ),
    { ...size },
  );
}
