import Link from "next/link";
import type { Metadata } from "next";
import { Gauge } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/theme-toggle";

/**
 * Marketing-area metadata. Inherits root layout's title.template + metadataBase,
 * so we only override the bits that differ.
 */
export const metadata: Metadata = {
  alternates: {
    canonical: "/",
  },
  openGraph: {
    title: "Forex Bot — Automated trading bot platform",
    description:
      "Six battle-tested strategies for XAUUSD and BTC. Backtest in seconds, deploy to your Exness MT5 in one click.",
    type: "website",
    locale: "en_US",
    siteName: "Forex Bot",
  },
  twitter: {
    card: "summary_large_image",
    title: "Forex Bot — Automated trading bot platform",
    description:
      "Six battle-tested strategies for XAUUSD and BTC. Transparent metrics. No hype.",
  },
};

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-30 border-b bg-background/80 backdrop-blur">
        <div className="container flex h-14 items-center justify-between">
          <Link href="/" className="flex items-center gap-2 font-semibold">
            <Gauge className="h-5 w-5 text-brand" aria-hidden="true" />
            <span>Forex Bot</span>
          </Link>
          <nav aria-label="Marketing" className="hidden gap-6 text-sm md:flex">
            <a href="#strategies" className="text-muted-foreground hover:text-foreground">
              Strategies
            </a>
            <a href="#pricing" className="text-muted-foreground hover:text-foreground">
              Pricing
            </a>
            <a href="#faq" className="text-muted-foreground hover:text-foreground">
              FAQ
            </a>
          </nav>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <Button asChild variant="ghost" size="sm">
              <Link href="/login">Sign in</Link>
            </Button>
            <Button asChild variant="brand" size="sm">
              <Link href="/signup">Get started</Link>
            </Button>
          </div>
        </div>
      </header>
      <main id="main" className="flex-1">
        {children}
      </main>
      <footer className="border-t bg-card">
        <div className="container flex flex-col items-center justify-between gap-2 py-6 text-sm text-muted-foreground sm:flex-row">
          <p>© {new Date().getFullYear()} Forex Bot. All rights reserved.</p>
          <p>Trading involves risk. Past performance is not indicative of future results.</p>
        </div>
      </footer>
    </div>
  );
}
