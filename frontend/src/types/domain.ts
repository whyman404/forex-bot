/**
 * Domain types — sync'd against docs/api/openapi.yaml (Atlas Goro).
 * Naming mirrors backend response shape (snake_case) for zero-conversion fetches.
 */

// -----------------------------------------------------------------------------
// Auth
// -----------------------------------------------------------------------------

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number; // seconds
}

export interface SignupRequest {
  email: string;
  password: string;
  display_name?: string | null;
}

export interface LoginRequest {
  email: string;
  password: string;
  totp_code?: string | null;
}

export interface TotpEnrollResponse {
  secret: string;
  provisioning_uri: string;
}

// -----------------------------------------------------------------------------
// Users
// -----------------------------------------------------------------------------

export interface UserPublic {
  id: string;
  email: string;
  display_name?: string | null;
  is_email_verified: boolean;
  totp_enabled: boolean;
  is_admin: boolean;
  created_at: string;
}

// -----------------------------------------------------------------------------
// Broker
// -----------------------------------------------------------------------------

export type BrokerKind = "exness_mt5" | "binance";
export type BrokerAccountType = "demo" | "live";

export interface BrokerAccountPublic {
  id: string;
  broker: string;
  label: string;
  account_type: string;
  is_active: boolean;
  last_connection_check_status?: string | null;
  created_at: string;
}

export interface BrokerAccountCreateRequest {
  broker: BrokerKind;
  label: string;
  account_type?: BrokerAccountType;
  credentials: Record<string, string>;
}

export interface BrokerConnectionTestResponse {
  ok: boolean;
  broker: string;
  account_id: string;
  latency_ms?: number | null;
  detail?: string | null;
}

// -----------------------------------------------------------------------------
// Strategy
// -----------------------------------------------------------------------------

export interface StrategyPublic {
  id: string;
  code: string;
  name: string;
  description?: string | null;
  instrument: string;
  timeframe: string;
  default_params: Record<string, number | string | boolean>;
}

export type StrategyInstanceStatus =
  | "draft"
  | "running"
  | "paused"
  | "stopped"
  | "killed"
  | "errored";

export interface StrategyInstancePublic {
  id: string;
  strategy_id: string;
  broker_account_id: string;
  label: string;
  status: StrategyInstanceStatus;
  params: Record<string, number | string | boolean>;
  risk_config: Record<string, number | string | boolean>;
  created_at: string;
  updated_at: string;
}

export interface StrategyInstanceCreateRequest {
  strategy_code: string;
  broker_account_id: string;
  label: string;
  params?: Record<string, number | string | boolean>;
  risk_config?: Record<string, number | string | boolean>;
}

// -----------------------------------------------------------------------------
// Backtest
// -----------------------------------------------------------------------------

export type BacktestStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface BacktestPublic {
  id: string;
  strategy_id: string;
  status: BacktestStatus;
  range_start: string; // YYYY-MM-DD
  range_end: string;
  initial_balance: number;
  profit_factor?: number | null;
  max_drawdown_pct?: number | null;
  sharpe_ratio?: number | null;
  win_rate_pct?: number | null;
  total_trades?: number | null;
  net_profit?: number | null;
  error_message?: string | null;
  completed_at?: string | null;
  created_at: string;
  // Optional extended payload — provided by API once succeeded; tolerated as absent.
  equity_curve?: BacktestEquityPoint[];
  monthly_returns?: BacktestMonthlyReturn[];
  trades?: BacktestTrade[];
  metrics_extra?: {
    sortino?: number | null;
    expectancy?: number | null;
    final_balance?: number | null;
  } | null;
}

export interface BacktestEquityPoint {
  time: string; // ISO or YYYY-MM-DD
  equity: number;
  drawdown: number;
}

export interface BacktestMonthlyReturn {
  year: number;
  month: number; // 1-12
  return_percent: number;
}

export interface BacktestTrade {
  id: string;
  asset: string;
  side: "buy" | "sell";
  entry_price: number;
  exit_price?: number | null;
  volume: number;
  pnl?: number | null;
  status: "open" | "closed" | "cancelled";
  opened_at: string;
  closed_at?: string | null;
}

export interface BacktestCreateRequest {
  strategy_code: string;
  range_start: string;
  range_end: string;
  initial_balance: number;
  params?: Record<string, number | string | boolean>;
}

// -----------------------------------------------------------------------------
// Billing
// -----------------------------------------------------------------------------

export type SubscriptionPlan = "free" | "trial" | "pro" | "enterprise" | "lifetime";
export type SubscriptionStatus =
  | "inactive"
  | "trialing"
  | "active"
  | "past_due"
  | "canceled"
  | "incomplete"
  | "unpaid";

export type PlanId =
  | "trial_14d"
  | "pro_monthly"
  | "pro_yearly"
  | "lifetime";

export type PlanInterval = "trial" | "month" | "year" | "lifetime";

export interface Plan {
  id: PlanId;
  price_id: string; // Stripe price ID
  name: string;
  description: string;
  amount_cents: number; // 0 for trial
  currency: string; // "usd"
  interval: PlanInterval;
  trial_days?: number | null;
  features: string[];
  savings_label?: string | null;
  is_lifetime?: boolean;
  highlight?: boolean;
}

export interface PlansResponse {
  plans: Plan[];
}

export interface Invoice {
  id: string;
  number?: string | null;
  amount_paid_cents: number;
  currency: string;
  status: string; // "paid" | "open" | "void" | "uncollectible"
  hosted_invoice_url?: string | null;
  invoice_pdf?: string | null;
  created_at: string;
  period_start?: string | null;
  period_end?: string | null;
}

export interface SubscriptionPublic {
  id: string;
  plan: SubscriptionPlan;
  status: SubscriptionStatus;
  current_period_end?: string | null;
  cancel_at_period_end: boolean;
  // Phase 2 additions
  trial_ends_at?: string | null;
  is_lifetime?: boolean;
  invoices?: Invoice[];
}

export interface CheckoutSessionRequest {
  price_id: string;
  success_url: string;
  cancel_url: string;
}

export interface CheckoutSessionResponse {
  url: string;
  session_id: string;
}

export interface CustomerPortalResponse {
  url: string;
}

// -----------------------------------------------------------------------------
// Live Trading — Eligibility Gates
// -----------------------------------------------------------------------------

export type LiveGateId =
  | "email_verified"
  | "totp_enabled"
  | "subscription_active"
  | "backtest_quality"
  | "paper_track_record"
  | "broker_connected"
  | "broker_min_balance"
  | "kill_switch_off"
  | "live_consent_signed";

export interface LiveGateCheck {
  id: LiveGateId;
  label: string;
  passed: boolean;
  detail?: string | null;
  fix_url?: string | null;
}

export interface LiveEligibilityResponse {
  eligible: boolean;
  gates: LiveGateCheck[];
  required_consent_version: string;
  /** Latest signed consent version, if any. */
  signed_consent_version?: string | null;
}

export interface LiveConsentRequest {
  version: string;
  /** Free-form acknowledgement text the user typed (e.g. "I UNDERSTAND"). */
  acknowledgement: string;
}

export interface LiveConsentPublic {
  id: string;
  type: string; // "live_trading" | "risk_disclaimer" | "terms" | ...
  version: string;
  acknowledged_at: string;
}

export interface GoLiveRequest {
  /** Must equal "GO LIVE" exactly. */
  confirmation_phrase: string;
  consent_id: string;
}

export interface RevertToPaperRequest {
  reason?: string | null;
}

// -----------------------------------------------------------------------------
// Live Monitoring — Health / Signals / Trades
// -----------------------------------------------------------------------------

export type HealthStatus = "healthy" | "degraded" | "down" | "unknown";

export interface InstanceHealth {
  status: HealthStatus;
  last_heartbeat?: string | null;
  open_positions: number;
  today_pnl: number;
  today_trades: number;
  notes?: string | null;
}

export interface InstanceSignal {
  id: string;
  side: "buy" | "sell";
  asset: string;
  emitted_at: string;
  reason?: string | null;
  acted_on: boolean;
}

export interface InstanceTrade {
  id: string;
  asset: string;
  side: "buy" | "sell";
  entry_price: number;
  exit_price?: number | null;
  volume: number;
  pnl?: number | null;
  status: "open" | "closed" | "cancelled";
  opened_at: string;
  closed_at?: string | null;
}

// -----------------------------------------------------------------------------
// TradingView Signal Strategy (tv_signal) — Round 5
// -----------------------------------------------------------------------------

/**
 * Recommendation tier reported by TradingView's technical-analysis widget.
 * STRONG_BUY..STRONG_SELL maps to a composite score range -100..+100.
 */
export type TVRecommendation =
  | "STRONG_BUY"
  | "BUY"
  | "NEUTRAL"
  | "SELL"
  | "STRONG_SELL";

/**
 * Per-timeframe analysis row returned from /tv/preview.
 * Field names mirror backend openapi schema `TVTimeframeAnalysis`.
 */
export interface TVTimeframeAnalysis {
  interval: string; // "5m" | "15m" | "1h" | "4h" | "1d" (free-form to allow more)
  recommendation: TVRecommendation;
  buy_count: number;
  sell_count: number;
  neutral_count: number;
}

/**
 * Aggregate TV preview snapshot — multi-TF + composite score.
 * Field names mirror backend openapi schema `TVPreview`.
 */
export interface TVPreview {
  symbol: string;
  /** TradingView exchange (e.g. OANDA, BINANCE). */
  exchange: string;
  /** Normalized signal score in [-100, +100]. */
  score: number;
  /** Confidence in [0.0, 1.0] based on cross-TF agreement. */
  confidence: number;
  timeframes: TVTimeframeAnalysis[];
  /** ISO-8601 timestamp from the engine (UTC). */
  generated_at: string;
}

/** Request body for POST /tv/preview. */
export interface TVPreviewRequest {
  symbol: string;
  exchange?: string | null;
  intervals: string[];
}

/**
 * Symbol metadata from GET /tv/symbols.
 * Field names mirror backend openapi schema `TVSymbol`.
 */
export interface TVSymbol {
  /** Internal symbol code (e.g. 'XAUUSD'). */
  code: string;
  /** TV ticker — may differ from code for indices. */
  tv_symbol: string;
  /** TV exchange code (e.g. OANDA, BINANCE). */
  tv_exchange: string;
  asset_class: "gold" | "forex" | "crypto" | "index" | string;
  display_name?: string;
}

/**
 * GET /tv/health response — used by the live-trading modal as an extra gate
 * before allowing tv_signal instances to go live.
 * Field names mirror backend openapi schema `TVHealth`.
 */
export interface TVHealth {
  status: "ok" | "degraded" | "down";
  trading_engine_reachable: boolean;
  upstream_tv_reachable?: boolean | null;
  reason?: string | null;
  /** ISO-8601 UTC timestamp. */
  checked_at: string;
}

// -----------------------------------------------------------------------------
// Onboarding
// -----------------------------------------------------------------------------

export type OnboardingStep = 0 | 1 | 2 | 3 | 4;

export interface OnboardingState {
  step: OnboardingStep;
  email_verified: boolean;
  totp_enabled: boolean;
  broker_connected: boolean;
  paper_instance_created: boolean;
  completed_at?: string | null;
}

// -----------------------------------------------------------------------------
// GDPR
// -----------------------------------------------------------------------------

export interface DataExportResponse {
  message: string;
  expected_email_within_minutes?: number | null;
}

export interface DeleteAccountRequest {
  confirmation_phrase: string; // "DELETE MY ACCOUNT"
}

// -----------------------------------------------------------------------------
// Notifications
// -----------------------------------------------------------------------------

export interface NotificationPublic {
  id: string;
  kind: string;
  title: string;
  body: string;
  is_read: boolean;
  created_at: string;
}

// -----------------------------------------------------------------------------
// UI-only adapter types (legacy components depend on these)
// -----------------------------------------------------------------------------

export type Asset = "XAUUSD" | "BTCUSDT" | "EURUSD" | "GBPUSD" | string;
export type Timeframe = "M1" | "M5" | "M15" | "M30" | "H1" | "H4" | "D1" | string;

/** Used by the equity-curve chart and drawdown chart components. */
export interface EquityPoint {
  time: string;
  equity: number;
  drawdown: number;
}

/** Used by the trade-table component. */
export interface Trade {
  id: string;
  asset: string;
  side: "buy" | "sell";
  entryPrice: number;
  exitPrice?: number;
  volume: number;
  pnl?: number;
  status: "open" | "closed" | "cancelled";
  openedAt: string;
  closedAt?: string;
}

/** Used by the strategy-card component. */
export interface Strategy {
  code: string;
  name: string;
  description: string;
  asset: Asset;
  timeframe: Timeframe;
  defaultParams: Record<string, number | string | boolean>;
  metrics?: {
    winRate: number;
    profitFactor: number;
    sharpeRatio: number;
    maxDrawdown: number;
  };
}

/** Adapter: API StrategyPublic -> UI Strategy. */
export function toStrategy(s: StrategyPublic): Strategy {
  return {
    code: s.code,
    name: s.name,
    description: s.description ?? "",
    asset: s.instrument,
    timeframe: s.timeframe,
    defaultParams: s.default_params ?? {},
  };
}

/** Adapter: API BacktestTrade -> UI Trade. */
export function toTrade(t: BacktestTrade): Trade {
  return {
    id: t.id,
    asset: t.asset,
    side: t.side,
    entryPrice: t.entry_price,
    exitPrice: t.exit_price ?? undefined,
    volume: t.volume,
    pnl: t.pnl ?? undefined,
    status: t.status,
    openedAt: t.opened_at,
    closedAt: t.closed_at ?? undefined,
  };
}
