import type { NextConfig } from "next";

/**
 * CSP — keep in sync with `vercel.json` headers (vercel.json wins at the edge,
 * this is the dev-server fallback + extra defense in depth).
 *
 * Allowed origins:
 *  - 'self'                         the app itself
 *  - https://*.stripe.com           Stripe.js, Checkout, Customer Portal
 *  - https://*.stripe.network       Stripe risk telemetry
 *  - https://js.stripe.com          Stripe Elements / Checkout SDK
 *  - https://m.stripe.network       Stripe metrics
 *  - https://fonts.googleapis.com   webfont CSS (Next/Font also self-hosts)
 *  - https://fonts.gstatic.com      webfont binaries
 *  - https://*.vercel-insights.com  Vercel Web Analytics (only if enabled)
 *  - https://*.sentry.io            Sentry browser SDK (only if SENTRY_DSN set)
 *  - {NEXT_PUBLIC_API_URL host}     Railway backend (added at runtime)
 */
const apiOrigin = (() => {
  try {
    if (process.env.NEXT_PUBLIC_API_URL) return new URL(process.env.NEXT_PUBLIC_API_URL).origin;
  } catch {
    /* fall through */
  }
  return "";
})();

const wsOrigin = (() => {
  try {
    if (process.env.NEXT_PUBLIC_WS_URL) {
      const u = new URL(process.env.NEXT_PUBLIC_WS_URL);
      return `${u.protocol}//${u.host}`;
    }
  } catch {
    /* fall through */
  }
  return "";
})();

const connectSrc = [
  "'self'",
  "https://*.stripe.com",
  "https://*.stripe.network",
  "https://*.sentry.io",
  "https://*.vercel-insights.com",
  apiOrigin,
  wsOrigin,
  // WebSocket fallback to same-origin and Railway domains
  "wss:",
]
  .filter(Boolean)
  .join(" ");

const securityHeaders = [
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      // Next.js inline bootstrap + Stripe.js
      "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://js.stripe.com https://*.stripe.com",
      "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
      "img-src 'self' data: blob: https:",
      "font-src 'self' data: https://fonts.gstatic.com",
      `connect-src ${connectSrc}`,
      "frame-src https://js.stripe.com https://*.stripe.com https://hooks.stripe.com",
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self' https://*.stripe.com",
      "object-src 'none'",
      "upgrade-insecure-requests",
    ].join("; "),
  },
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), interest-cohort=()" },
  { key: "X-DNS-Prefetch-Control", value: "on" },
];

/**
 * Allowed Server Action origins:
 *  - Production custom domain(s)
 *  - Vercel preview deployments (*.vercel.app)
 *  - Local development (handled by Next automatically)
 */
const serverActionAllowedOrigins = [
  "forex-bot.app",
  "www.forex-bot.app",
  "*.vercel.app",
  process.env.VERCEL_URL,
  process.env.NEXT_PUBLIC_BASE_URL ? new URL(process.env.NEXT_PUBLIC_BASE_URL).host : undefined,
].filter((v): v is string => Boolean(v));

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // standalone keeps Vercel's auto-detection happy AND lets Docker/Railway reuse the same build.
  output: "standalone",
  poweredByHeader: false,
  compress: true,
  // Lint warnings should not fail Vercel deploy; CI lint job catches them on push.
  eslint: { ignoreDuringBuilds: true },
  // SWC minification is the default in Next 15; flag kept implicit.
  productionBrowserSourceMaps: false,
  experimental: {
    optimizePackageImports: ["lucide-react", "date-fns", "recharts"],
    serverActions: {
      allowedOrigins: serverActionAllowedOrigins,
      bodySizeLimit: "2mb",
    },
  },
  images: {
    formats: ["image/avif", "image/webp"],
    remotePatterns: [
      // Self (covers any *.forex-bot.app subdomain — marketing, app, cdn)
      { protocol: "https", hostname: "**.forex-bot.app" },
      // GitHub avatars for testimonials / OAuth profile pictures
      { protocol: "https", hostname: "avatars.githubusercontent.com" },
      // Cloudflare R2 — equity curve / report assets
      { protocol: "https", hostname: "**.r2.cloudflarestorage.com" },
      { protocol: "https", hostname: "**.r2.dev" },
      // AWS S3 — alt storage
      { protocol: "https", hostname: "**.s3.amazonaws.com" },
      { protocol: "https", hostname: "**.s3.*.amazonaws.com" },
      // Vercel-hosted assets (blob, og-images)
      { protocol: "https", hostname: "**.vercel-storage.com" },
    ],
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: securityHeaders,
      },
    ];
  },
};

export default nextConfig;
