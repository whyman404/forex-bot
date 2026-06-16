import type { MetadataRoute } from "next";
import { resolveBaseUrl } from "@/lib/env";

/**
 * Generates /robots.txt automatically. The (app) area is gated behind auth
 * so we forbid it for crawlers regardless. /api is server-only.
 */
export default function robots(): MetadataRoute.Robots {
  const baseUrl = resolveBaseUrl();
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: [
          "/api",
          "/api/",
          "/dashboard",
          "/dashboard/",
          "/strategies",
          "/strategies/",
          "/backtest",
          "/backtest/",
          "/billing",
          "/billing/",
          "/broker",
          "/broker/",
          "/settings",
          "/settings/",
          "/onboarding",
          "/onboarding/",
        ],
      },
    ],
    sitemap: `${baseUrl}/sitemap.xml`,
    host: baseUrl,
  };
}
