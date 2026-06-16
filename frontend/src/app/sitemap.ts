import type { MetadataRoute } from "next";
import { resolveBaseUrl } from "@/lib/env";

/**
 * Sitemap covers only PUBLIC marketing routes — authenticated routes are
 * excluded since they require login and have no SEO value.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  const baseUrl = resolveBaseUrl();
  const now = new Date();

  // Public strategy codes (kept in sync with backend STRATEGY_REGISTRY).
  const strategies = [
    "london-breakout",
    "ny-killzone",
    "ema-adx-trend",
    "rsi-mean-reversion",
    "btc-grid",
    "xauusd-scalper",
  ];

  return [
    {
      url: `${baseUrl}/`,
      lastModified: now,
      changeFrequency: "weekly",
      priority: 1,
    },
    {
      url: `${baseUrl}/login`,
      lastModified: now,
      changeFrequency: "monthly",
      priority: 0.5,
    },
    {
      url: `${baseUrl}/signup`,
      lastModified: now,
      changeFrequency: "monthly",
      priority: 0.6,
    },
    ...strategies.map((code) => ({
      url: `${baseUrl}/${code}`,
      lastModified: now,
      changeFrequency: "weekly" as const,
      priority: 0.7,
    })),
  ];
}
