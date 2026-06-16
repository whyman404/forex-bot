"use client";

/**
 * TradingView Signal — dedicated strategy detail page.
 *
 * Round 5 (Eos Hinata). Wires:
 *  - Symbol selector (GET /tv/symbols)
 *  - Multi-TF preview (POST /tv/preview, refetch 60s)
 *  - Composite score bar + per-TF table
 *  - tv_signal param form (entry/exit threshold, ATR mults, cool_down, agreement)
 *  - "Create paper instance" button → POST /strategy-instances
 *
 * The page is intentionally informational. Microcopy reminds the user that TV
 * signals are NOT financial advice — the platform forwards them per the user's
 * gate settings only.
 */

import * as React from "react";
import Link from "next/link";
import { toast } from "sonner";
import { ExternalLink, Info, ShieldAlert, RefreshCw, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { TVRecommendationBadge } from "@/components/tv-recommendation-badge";
import { TVScoreBar } from "@/components/tv-score-bar";
import { TVTimeframeTable } from "@/components/tv-timeframe-table";
import { useStrategy } from "@/hooks/use-strategies";
import { useCreateStrategyInstance } from "@/hooks/use-strategy-instance";
import { useBrokerAccounts } from "@/hooks/use-broker-accounts";
import {
  useTVHealth,
  useTVPreview,
  useTVSymbols,
} from "@/hooks/use-tradingview";
import { ApiError } from "@/lib/api";

const STRATEGY_CODE = "tv_signal";
const ALL_INTERVALS = ["5m", "15m", "1h", "4h", "1d"] as const;
const DEFAULT_INTERVALS: readonly string[] = ["15m", "1h", "4h"];

interface TVParamsState {
  entry_score_threshold: number;
  exit_score_threshold: number;
  atr_sl_mult: number;
  atr_tp_mult: number;
  cool_down_min: number;
  agreement_pct: number;
}

const DEFAULT_PARAMS: TVParamsState = {
  entry_score_threshold: 50,
  exit_score_threshold: 25,
  atr_sl_mult: 1.5,
  atr_tp_mult: 2.5,
  cool_down_min: 30,
  agreement_pct: 66,
};

/**
 * Map a composite score in [-100, +100] to the closest TradingView
 * recommendation tier. Used because the backend `TVPreview` ships a numeric
 * score, not a categorical recommendation — the badge wants the categorical.
 */
function deriveRecommendation(score: number): "STRONG_BUY" | "BUY" | "NEUTRAL" | "SELL" | "STRONG_SELL" {
  if (score >= 60) return "STRONG_BUY";
  if (score >= 20) return "BUY";
  if (score <= -60) return "STRONG_SELL";
  if (score <= -20) return "SELL";
  return "NEUTRAL";
}

function useRelativeNow(timestamp: string | null | undefined): string {
  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => {
    if (!timestamp) return;
    const id = setInterval(() => setNow(Date.now()), 1_000);
    return () => clearInterval(id);
  }, [timestamp]);
  if (!timestamp) return "—";
  const delta = Math.max(0, Math.floor((now - new Date(timestamp).getTime()) / 1000));
  if (delta < 60) return `${delta}s ago`;
  if (delta < 3600) return `${Math.floor(delta / 60)}m ago`;
  return `${Math.floor(delta / 3600)}h ago`;
}

export default function TVSignalStrategyPage(): React.ReactElement {
  const strategy = useStrategy(STRATEGY_CODE);
  const symbols = useTVSymbols();
  const health = useTVHealth();
  const brokers = useBrokerAccounts();
  const create = useCreateStrategyInstance();

  const [symbol, setSymbol] = React.useState<string | null>(null);
  const [intervals, setIntervals] = React.useState<string[]>([...DEFAULT_INTERVALS]);
  const [previewArmed, setPreviewArmed] = React.useState(false);
  const [params, setParams] = React.useState<TVParamsState>(DEFAULT_PARAMS);
  const [label, setLabel] = React.useState("TradingView Signal — paper");
  const [brokerId, setBrokerId] = React.useState<string>("");

  // First symbol becomes default selection.
  React.useEffect(() => {
    const first = symbols.data?.[0];
    if (!symbol && first) {
      setSymbol(first.code);
    }
  }, [symbols.data, symbol]);

  React.useEffect(() => {
    if (brokerId) return;
    const first = brokers.data?.[0];
    if (first) setBrokerId(first.id);
  }, [brokers.data, brokerId]);

  const preview = useTVPreview({
    symbol,
    intervals,
    enabled: previewArmed && !!symbol && intervals.length > 0,
  });

  const fetchedAgo = useRelativeNow(preview.data?.generated_at ?? null);

  function toggleInterval(iv: string): void {
    setIntervals((cur) =>
      cur.includes(iv) ? cur.filter((x) => x !== iv) : [...cur, iv],
    );
  }

  function updateParam<K extends keyof TVParamsState>(k: K, v: number): void {
    setParams((p) => ({ ...p, [k]: v }));
  }

  async function handleCreatePaper(): Promise<void> {
    if (!brokerId) {
      toast.error("Connect a broker before creating an instance");
      return;
    }
    if (!symbol) {
      toast.error("Pick a symbol first");
      return;
    }
    try {
      await create.mutateAsync({
        strategy_code: STRATEGY_CODE,
        broker_account_id: brokerId,
        label,
        params: {
          symbol,
          intervals: intervals.join(","),
          entry_score_threshold: params.entry_score_threshold,
          exit_score_threshold: params.exit_score_threshold,
          atr_sl_mult: params.atr_sl_mult,
          atr_tp_mult: params.atr_tp_mult,
          cool_down_min: params.cool_down_min,
          agreement_pct: params.agreement_pct,
        },
        risk_config: { paper: true },
      });
      toast.success("Paper instance created — open the Dashboard to start it");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not create instance");
    }
  }

  const tvDown =
    !!health.error ||
    (health.data ? health.data.status === "down" : false);

  return (
    <div className="space-y-6">
      {/* Header / info */}
      <header className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-bold tracking-tight">
            {strategy.data?.name ?? "TradingView Signal"}
          </h1>
          <Badge variant="outline">MULTI</Badge>
          <Badge variant="warn">MEDIUM</Badge>
          <Badge variant="secondary" className="gap-1">
            <Info className="h-3 w-3" aria-hidden="true" /> Informational signals — not financial advice
          </Badge>
        </div>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Multi-timeframe TradingView signals routed to MT5. We forward the consensus per your
          gate settings; we do not produce or validate the signal. Use paper mode first.
        </p>
      </header>

      {tvDown && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-md border border-warn/40 bg-warn/10 p-3 text-sm"
        >
          <ShieldAlert className="mt-0.5 h-4 w-4 text-warn" aria-hidden="true" />
          <div>
            <p className="font-medium">TradingView integration is currently unavailable.</p>
            <p className="text-xs text-muted-foreground">
              The UI is read-only until <code>TV_ENABLED=true</code> is configured on the backend.
              Live signals will resume automatically once the integration recovers.
            </p>
          </div>
        </div>
      )}

      {/* TV preview panel */}
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-brand" aria-hidden="true" />
                TradingView preview
              </CardTitle>
              <CardDescription>
                Pick a symbol and timeframes, then preview the multi-TF consensus.
                Auto-refreshes every 60 seconds while open.
              </CardDescription>
            </div>
            <a
              href="https://www.tradingview.com/"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs text-muted-foreground underline decoration-dotted underline-offset-2 hover:text-foreground"
            >
              Source: TradingView
              <ExternalLink className="h-3 w-3" aria-hidden="true" />
            </a>
          </div>
        </CardHeader>
        <CardContent className="space-y-5">
          {/* Symbol + intervals */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="tv-symbol">Symbol</Label>
              {symbols.isLoading ? (
                <Skeleton className="h-10" />
              ) : symbols.error ? (
                <p className="text-xs text-destructive">
                  {symbols.error instanceof ApiError && symbols.error.status === 503
                    ? "TradingView disabled on backend — set TV_ENABLED=true to enable."
                    : "Could not load symbols. Try again later."}
                </p>
              ) : !symbols.data || symbols.data.length === 0 ? (
                <p className="text-xs text-muted-foreground">No symbols available.</p>
              ) : (
                <select
                  id="tv-symbol"
                  value={symbol ?? ""}
                  onChange={(e) => {
                    setSymbol(e.target.value);
                    setPreviewArmed(false);
                  }}
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {symbols.data.map((s) => (
                    <option key={s.code} value={s.code}>
                      {s.display_name ?? s.code} · {s.tv_symbol}@{s.tv_exchange}
                    </option>
                  ))}
                </select>
              )}
            </div>
            <fieldset className="space-y-1.5">
              <legend className="text-sm font-medium">Intervals</legend>
              <div className="flex flex-wrap gap-2 pt-1">
                {ALL_INTERVALS.map((iv) => {
                  const checked = intervals.includes(iv);
                  const id = `tv-iv-${iv}`;
                  return (
                    <label
                      key={iv}
                      htmlFor={id}
                      className={[
                        "flex cursor-pointer items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs",
                        checked
                          ? "border-brand bg-brand/10 text-foreground"
                          : "border-input bg-background text-muted-foreground hover:text-foreground",
                      ].join(" ")}
                    >
                      <input
                        id={id}
                        type="checkbox"
                        className="h-3.5 w-3.5"
                        checked={checked}
                        onChange={() => {
                          toggleInterval(iv);
                          setPreviewArmed(false);
                        }}
                      />
                      <span className="font-mono uppercase">{iv}</span>
                    </label>
                  );
                })}
              </div>
              <p className="pt-1 text-xs text-muted-foreground">
                Default: 15m + 1h + 4h. More intervals = stricter consensus.
              </p>
            </fieldset>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="brand"
              onClick={() => setPreviewArmed(true)}
              disabled={!symbol || intervals.length === 0 || preview.isFetching}
            >
              <RefreshCw className="mr-2 h-4 w-4" aria-hidden="true" />
              {preview.isFetching ? "Loading…" : previewArmed ? "Refresh preview" : "Preview"}
            </Button>
            {previewArmed && preview.data && (
              <span
                className="inline-flex items-center gap-1 rounded-md border bg-muted/40 px-2 py-1 text-xs text-muted-foreground"
                aria-live="polite"
              >
                <span
                  className="h-1.5 w-1.5 animate-pulse rounded-full bg-profit"
                  aria-hidden="true"
                />
                Score updated: {fetchedAgo} · auto-refresh 60s
              </span>
            )}
          </div>

          {/* Preview output */}
          {!previewArmed ? (
            <p className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
              Pick a symbol and at least one interval, then press <strong>Preview</strong>.
            </p>
          ) : preview.isLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-12" />
              <Skeleton className="h-40" />
            </div>
          ) : preview.error ? (
            <div
              role="alert"
              className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm"
            >
              {preview.error instanceof ApiError && preview.error.status === 503
                ? "TradingView integration is disabled on this deployment."
                : preview.error instanceof ApiError
                  ? preview.error.message
                  : "Could not fetch preview."}
            </div>
          ) : !preview.data ? (
            <p className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
              No data returned for this symbol.
            </p>
          ) : (
            <div className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-[1fr_auto] sm:items-end">
                <TVScoreBar
                  score={preview.data.score}
                  label={`Composite (${preview.data.symbol})`}
                />
                <div className="flex items-center gap-2">
                  <TVRecommendationBadge
                    recommendation={deriveRecommendation(preview.data.score)}
                  />
                  <span className="text-xs text-muted-foreground">
                    Confidence {(preview.data.confidence * 100).toFixed(0)}%
                  </span>
                </div>
              </div>
              <TVTimeframeTable
                rows={preview.data.timeframes}
                caption={`Multi-timeframe consensus for ${preview.data.symbol} on ${preview.data.exchange}.`}
              />
            </div>
          )}
        </CardContent>
      </Card>

      {/* Params form */}
      <Card>
        <CardHeader>
          <CardTitle>Strategy parameters</CardTitle>
          <CardDescription>
            Tune thresholds before activating a paper instance. ATR multipliers size risk
            relative to recent volatility.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <fieldset className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <NumberField
              id="entry"
              label="Entry score threshold"
              help="Composite |score| required to open. Higher = fewer, stronger entries."
              value={params.entry_score_threshold}
              min={0}
              max={100}
              step={1}
              onChange={(v) => updateParam("entry_score_threshold", v)}
            />
            <NumberField
              id="exit"
              label="Exit score threshold"
              help="Composite |score| at which to exit early."
              value={params.exit_score_threshold}
              min={0}
              max={100}
              step={1}
              onChange={(v) => updateParam("exit_score_threshold", v)}
            />
            <NumberField
              id="sl"
              label="ATR Stop-Loss multiplier"
              help="SL distance = ATR × this. 1.0 ≈ tight, 2.5 ≈ wide."
              value={params.atr_sl_mult}
              min={0.1}
              max={10}
              step={0.1}
              onChange={(v) => updateParam("atr_sl_mult", v)}
            />
            <NumberField
              id="tp"
              label="ATR Take-Profit multiplier"
              help="TP distance = ATR × this. Should typically exceed SL multiplier."
              value={params.atr_tp_mult}
              min={0.1}
              max={20}
              step={0.1}
              onChange={(v) => updateParam("atr_tp_mult", v)}
            />
            <NumberField
              id="cool"
              label="Cool-down (minutes)"
              help="Minimum minutes between trades on the same symbol."
              value={params.cool_down_min}
              min={0}
              max={1440}
              step={1}
              onChange={(v) => updateParam("cool_down_min", v)}
            />
            <NumberField
              id="agreement"
              label="Agreement % required"
              help="Percentage of intervals that must agree to act."
              value={params.agreement_pct}
              min={0}
              max={100}
              step={1}
              onChange={(v) => updateParam("agreement_pct", v)}
            />
          </fieldset>
        </CardContent>
      </Card>

      {/* Activate paper */}
      <Card>
        <CardHeader>
          <CardTitle>Create paper instance</CardTitle>
          <CardDescription>
            Paper mode logs trades without sending real orders. Always start here.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="tv-label">Instance label</Label>
              <Input
                id="tv-label"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="My TV signal bot"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="tv-broker">Broker account</Label>
              {brokers.isLoading ? (
                <Skeleton className="h-10" />
              ) : brokers.data && brokers.data.length > 0 ? (
                <select
                  id="tv-broker"
                  value={brokerId}
                  onChange={(e) => setBrokerId(e.target.value)}
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {brokers.data.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.label} ({b.account_type})
                    </option>
                  ))}
                </select>
              ) : (
                <p className="text-xs text-muted-foreground">
                  No brokers yet —{" "}
                  <Link href="/broker" className="underline">
                    connect one
                  </Link>
                  .
                </p>
              )}
            </div>
          </div>
          <p className="rounded-md border border-warn/40 bg-warn/5 p-3 text-xs text-muted-foreground">
            We forward TradingView signals as-is. We do not validate signal quality, and we are not
            responsible for outcomes. Live trading also requires the standard safety gates.
          </p>
          <div className="flex flex-wrap gap-3">
            <Button
              variant="brand"
              onClick={handleCreatePaper}
              disabled={create.isPending || !brokerId || !symbol}
            >
              {create.isPending ? "Creating…" : "Create paper instance"}
            </Button>
            <Button asChild variant="outline">
              <Link href={`/backtest?strategy=${STRATEGY_CODE}`}>Run backtest</Link>
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function NumberField({
  id,
  label,
  help,
  value,
  min,
  max,
  step,
  onChange,
}: {
  id: string;
  label: string;
  help?: string;
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (v: number) => void;
}): React.ReactElement {
  const helpId = help ? `${id}-help` : undefined;
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        type="number"
        inputMode="decimal"
        value={Number.isFinite(value) ? value : ""}
        min={min}
        max={max}
        step={step}
        onChange={(e) => {
          const n = Number(e.target.value);
          if (Number.isFinite(n)) onChange(n);
        }}
        aria-describedby={helpId}
      />
      {help && (
        <p id={helpId} className="text-xs text-muted-foreground">
          {help}
        </p>
      )}
    </div>
  );
}
