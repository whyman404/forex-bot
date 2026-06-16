import Link from "next/link";
import { ArrowRight, CheckCircle2, ShieldCheck, Sparkles, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface MarketingStrategy {
  readonly name: string;
  readonly asset: string;
  readonly edge: string;
  readonly informational?: boolean;
}

const STRATEGIES: readonly MarketingStrategy[] = [
  {
    name: "London Breakout",
    asset: "XAUUSD",
    edge: "Asian range breakout at London open",
  },
  {
    name: "NY Killzone",
    asset: "XAUUSD",
    edge: "Liquidity sweep + reversal in NY session",
  },
  { name: "EMA + ADX Trend", asset: "XAUUSD", edge: "Trend-follow on strong directional moves" },
  { name: "RSI Mean Reversion", asset: "EURUSD", edge: "Overbought/oversold fade on M15" },
  { name: "BTC Grid", asset: "BTCUSDT", edge: "Range-bound grid with dynamic exit" },
  { name: "XAUUSD Scalper", asset: "XAUUSD", edge: "M1/M5 scalp with tight risk" },
  {
    name: "TradingView Signal Follow",
    asset: "MULTI",
    edge: "Multi-timeframe TradingView consensus routed to MT5",
    informational: true,
  },
] as const;

interface MarketingPlan {
  readonly name: string;
  readonly price: string;
  readonly perPeriod: string;
  readonly blurb: string;
  readonly features: readonly string[];
  readonly featured?: boolean;
  readonly savings?: string;
}

const PLANS: readonly MarketingPlan[] = [
  {
    name: "Free Trial",
    price: "$0",
    perPeriod: " · 14 days",
    blurb: "Paper trading only",
    features: ["All 7 strategies", "Unlimited backtest", "Paper trading", "Email support"],
  },
  {
    name: "Pro Monthly",
    price: "$29",
    perPeriod: "/mo",
    blurb: "Live trading, billed monthly",
    features: [
      "Everything in Trial",
      "Live trading (1 broker)",
      "Real-time alerts",
      "Priority support",
    ],
    featured: true,
  },
  {
    name: "Pro Yearly",
    price: "$290",
    perPeriod: "/yr",
    blurb: "Save 17% paid yearly",
    features: [
      "Everything in Pro Monthly",
      "Save 17% vs monthly",
      "Up to 2 broker accounts",
    ],
    savings: "Save 17%",
  },
  {
    name: "Lifetime",
    price: "$990",
    perPeriod: " once",
    blurb: "Pay once, trade forever",
    features: [
      "Everything in Pro Yearly",
      "Up to 5 broker accounts",
      "1:1 onboarding",
      "Lifetime updates",
    ],
  },
] as const;

const TESTIMONIALS = [
  {
    quote:
      "Backtests run in seconds and the kill switch already saved me during a flash move.",
    name: "Alex K.",
    role: "Prop firm trader",
  },
  {
    quote:
      "Honest metrics. No 95% win-rate marketing nonsense.",
    name: "Priya S.",
    role: "Independent trader",
  },
  {
    quote:
      "Going from paper to live with the eligibility gates is the cleanest UX I have seen.",
    name: "Marcus L.",
    role: "Algorithmic trader",
  },
] as const;

const FAQS = [
  {
    q: "Can the bot guarantee a 95% win rate?",
    a: "No legitimate strategy can. Our strategies target a profit factor > 1.5 with controlled drawdown, which is more sustainable than chasing high win rate.",
  },
  {
    q: "Do you hold my Exness password?",
    a: "Credentials are encrypted server-side and used only to drive a dedicated MT5 terminal we host. You can disconnect at any time.",
  },
  {
    q: "What happens during a flash crash?",
    a: "Each strategy has hard stops and our kill switch can be triggered manually or auto-triggered on a drawdown threshold you configure.",
  },
  {
    q: "Can I use my own strategy?",
    a: "Custom strategies are on the roadmap. For now you can tune parameters of the 7 included strategies and backtest freely. Our TradingView Signal Follow strategy lets you route external signals as-is, with safety gates.",
  },
] as const;

export default function MarketingPage() {
  return (
    <>
      <section className="container py-16 md:py-24" aria-labelledby="hero-title">
        <div className="mx-auto max-w-3xl text-center">
          <Badge variant="warn" className="mb-4">
            Phase 1 — paper trading available now
          </Badge>
          <h1 id="hero-title" className="text-4xl font-bold tracking-tight md:text-6xl">
            Automated trading, <span className="text-brand">without guesswork</span>
          </h1>
          <p className="mt-6 text-lg text-muted-foreground">
            Seven battle-tested strategies — including TradingView signal follow — for XAUUSD, FX
            and BTC. Backtest in seconds, deploy to your Exness MT5 in one click. Transparent
            metrics, no hype.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Button asChild variant="brand" size="lg">
              <Link href="/signup">
                Start free
                <ArrowRight className="ml-2 h-4 w-4" aria-hidden="true" />
              </Link>
            </Button>
            <Button asChild variant="outline" size="lg">
              <a href="#strategies">Browse strategies</a>
            </Button>
          </div>
        </div>
      </section>

      <section
        id="strategies"
        aria-labelledby="strategies-title"
        className="container border-t py-16"
      >
        <div className="mx-auto max-w-2xl text-center">
          <h2 id="strategies-title" className="text-3xl font-bold">
            Seven strategies. One platform.
          </h2>
          <p className="mt-2 text-muted-foreground">
            Each strategy is documented with entry/exit rules, risk model, and out-of-sample
            backtest results.
          </p>
        </div>
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {STRATEGIES.map((s) => (
            <Card key={s.name} className={s.informational ? "border-brand/40" : undefined}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">{s.name}</CardTitle>
                  <Badge variant="outline">{s.asset}</Badge>
                </div>
                <CardDescription>{s.edge}</CardDescription>
                {s.informational && (
                  <span
                    role="note"
                    className="mt-2 inline-flex w-fit items-center gap-1 rounded-md border border-warn/40 bg-warn/10 px-2 py-0.5 text-[11px] text-foreground"
                  >
                    Informational signals — not financial advice
                  </span>
                )}
              </CardHeader>
            </Card>
          ))}
        </div>
      </section>

      <section className="container border-t py-16" aria-labelledby="why-title">
        <h2 id="why-title" className="text-3xl font-bold">
          Why traders pick us
        </h2>
        <div className="mt-8 grid gap-6 md:grid-cols-3">
          {[
            { icon: Sparkles, title: "Transparent metrics", body: "Profit factor, Sharpe, drawdown — never just win rate." },
            { icon: ShieldCheck, title: "Built-in kill switch", body: "Manual + auto trigger on configurable drawdown." },
            { icon: Zap, title: "Fast backtests", body: "Vectorbt-powered: a 5-year backtest finishes in seconds." },
          ].map(({ icon: Icon, title, body }) => (
            <div key={title} className="flex gap-3">
              <Icon className="mt-0.5 h-5 w-5 shrink-0 text-brand" aria-hidden="true" />
              <div>
                <h3 className="font-semibold">{title}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{body}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section id="pricing" aria-labelledby="pricing-title" className="container border-t py-16">
        <div className="mx-auto max-w-2xl text-center">
          <h2 id="pricing-title" className="text-3xl font-bold">
            Pricing
          </h2>
          <p className="mt-2 text-muted-foreground">Start free. Upgrade when you go live.</p>
        </div>
        <div className="mx-auto mt-10 grid max-w-6xl gap-6 md:grid-cols-2 lg:grid-cols-4">
          {PLANS.map((p) => {
            const featured = p.featured ?? false;
            const savings = p.savings;
            return (
              <Card
                key={p.name}
                className={`relative ${featured ? "border-brand shadow-lg" : ""}`}
              >
                {featured && (
                  <Badge variant="warn" className="absolute -top-3 right-4">
                    Most popular
                  </Badge>
                )}
                {!featured && savings && (
                  <Badge variant="profit" className="absolute -top-3 right-4">
                    {savings}
                  </Badge>
                )}
                <CardHeader>
                  <CardTitle className="text-lg">{p.name}</CardTitle>
                  <CardDescription>{p.blurb}</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold">
                    {p.price}
                    <span className="ml-1 text-sm font-normal text-muted-foreground">
                      {p.perPeriod}
                    </span>
                  </div>
                  <ul className="mt-4 space-y-2 text-sm">
                    {p.features.map((f) => (
                      <li key={f} className="flex items-start gap-2">
                        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-profit" aria-hidden="true" />
                        <span>{f}</span>
                      </li>
                    ))}
                  </ul>
                  <Button asChild className="mt-6 w-full" variant={featured ? "brand" : "outline"}>
                    <Link href="/signup">Choose {p.name}</Link>
                  </Button>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </section>

      <section
        id="testimonials"
        aria-labelledby="testimonials-title"
        className="container border-t py-16"
      >
        <div className="mx-auto max-w-2xl text-center">
          <h2 id="testimonials-title" className="text-3xl font-bold">
            Loved by serious traders
          </h2>
          <p className="mt-2 text-muted-foreground">
            Built by traders. Used by traders. Honest reviews from our community.
          </p>
        </div>
        <div className="mt-10 grid gap-6 md:grid-cols-3">
          {TESTIMONIALS.map((tst) => (
            <Card key={tst.name}>
              <CardContent className="space-y-3 p-6 text-sm">
                <p className="italic text-muted-foreground">&ldquo;{tst.quote}&rdquo;</p>
                <div>
                  <p className="font-semibold">{tst.name}</p>
                  <p className="text-xs text-muted-foreground">{tst.role}</p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <section id="faq" aria-labelledby="faq-title" className="container border-t py-16">
        <div className="mx-auto max-w-3xl">
          <h2 id="faq-title" className="text-3xl font-bold">
            Frequently asked
          </h2>
          <dl className="mt-8 space-y-6">
            {FAQS.map((f) => (
              <div key={f.q}>
                <dt className="font-semibold">{f.q}</dt>
                <dd className="mt-1 text-sm text-muted-foreground">{f.a}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      <section
        aria-labelledby="risk-title"
        className="container border-t bg-muted/30 py-10"
      >
        <div className="mx-auto max-w-4xl space-y-3 text-xs text-muted-foreground">
          <h2 id="risk-title" className="text-sm font-semibold text-foreground">
            Risk Disclosure
          </h2>
          <p>
            Trading leveraged products such as foreign exchange and crypto carries a high level of
            risk and may not be suitable for all investors. The high degree of leverage can work
            against you as well as for you. Before deciding to trade, you should carefully consider
            your investment objectives, level of experience, and risk appetite. Past performance is
            not indicative of future results. You should only trade with money you can afford to
            lose.
          </p>
          <p>
            Forex Bot is a software platform. We do not provide investment advice. All strategies are
            for informational purposes and configured at your sole discretion. By using this service
            you agree to our terms of service and acknowledge the inherent risks of automated
            trading.
          </p>
        </div>
      </section>
    </>
  );
}
