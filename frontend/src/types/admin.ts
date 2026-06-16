/**
 * Admin domain types — match Atlas R6 backend admin endpoints under `/admin/*`.
 * Field names mirror backend snake_case for zero-conversion fetches.
 *
 * Reference: docs/api/openapi.yaml (admin tag) + r6-notes.md.
 */

import type { SubscriptionPlan, SubscriptionStatus } from "./domain";

// -----------------------------------------------------------------------------
// Users
// -----------------------------------------------------------------------------

export type UserRole = "user" | "admin" | "support";
export type UserStatus = "active" | "banned" | "pending_deletion" | "deleted";

export interface AdminUserListItem {
  id: string;
  email: string;
  full_name?: string | null;
  display_name?: string | null;
  role: UserRole;
  status: UserStatus;
  is_email_verified: boolean;
  totp_enabled: boolean;
  subscription_plan?: SubscriptionPlan | null;
  subscription_status?: SubscriptionStatus | null;
  broker_count: number;
  instances_count: number;
  last_login_at?: string | null;
  created_at: string;
}

export interface AdminUserDetail extends AdminUserListItem {
  country?: string | null;
  notes?: string | null;
  updated_at: string;
  /** Last 10 audit log entries authored BY this user (not against them). */
  recent_actions?: AdminAuditLogEntry[];
}

export interface AdminUserUpdateRequest {
  full_name?: string | null;
  display_name?: string | null;
  country?: string | null;
  role?: UserRole;
  status?: UserStatus;
  is_email_verified?: boolean;
  notes?: string | null;
}

export interface AdminUserListQuery {
  q?: string;
  role?: UserRole;
  status?: UserStatus;
  plan?: SubscriptionPlan;
  page?: number;
  per_page?: number;
  sort?: string; // "created_at:desc"
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface AdminResetPasswordResponse {
  /** One-time display. Never stored on the client; warn the operator. */
  temp_password: string;
  expires_at: string;
}

export interface AdminImpersonateResponse {
  /** Short-lived access token issued AS that user. */
  access_token: string;
  expires_in: number;
  audit_log_id: string;
}

export interface AdminBulkBanRequest {
  user_ids: string[];
  reason: string;
}

// -----------------------------------------------------------------------------
// Audit log
// -----------------------------------------------------------------------------

export type AdminActionType =
  | "user.update"
  | "user.reset_password"
  | "user.impersonate"
  | "user.ban"
  | "user.unban"
  | "user.delete"
  | "subscription.cancel"
  | "subscription.grant"
  | "strategy.update"
  | "strategy.kill_all"
  | "broadcast.send"
  | "global_kill.engage"
  | "global_kill.disarm"
  | "login"
  | "logout"
  | string; // tolerate forward-compat actions

export type AdminTargetType =
  | "user"
  | "subscription"
  | "strategy"
  | "strategy_instance"
  | "broadcast"
  | "global_kill"
  | "system"
  | string;

export interface AdminAuditLogEntry {
  id: string;
  actor_id: string;
  actor_email: string;
  actor_role: UserRole;
  /** When admin acted while impersonating; null otherwise. */
  impersonating_user_id?: string | null;
  impersonating_user_email?: string | null;
  action: AdminActionType;
  target_type: AdminTargetType;
  target_id?: string | null;
  target_label?: string | null;
  payload?: Record<string, unknown> | null;
  ip_address?: string | null;
  user_agent?: string | null;
  created_at: string;
}

export interface AdminAuditLogQuery {
  actor?: string;
  action?: AdminActionType;
  target_type?: AdminTargetType;
  target_id?: string;
  date_from?: string;
  date_to?: string;
  page?: number;
  per_page?: number;
}

// -----------------------------------------------------------------------------
// System metrics
// -----------------------------------------------------------------------------

export interface AdminSystemMetrics {
  users_total: number;
  users_active_7d: number;
  users_new_7d: number;
  subscriptions_active: number;
  mrr_usd_cents: number;
  churn_30d_pct: number;
  today: {
    backtests: number;
    signals: number;
    trades: number;
    gross_pnl_usd: number;
  };
  live_engines_running: number;
  kill_switches_armed: number;
  queue_depth: {
    email: number;
    backtest: number;
  };
  generated_at: string;
}

export type DependencyName =
  | "postgres"
  | "redis"
  | "stripe"
  | "email"
  | "mt5_bridge"
  | "tradingview";

export type DependencyStatus = "up" | "degraded" | "down" | "unknown";

export interface AdminDependencyHealth {
  name: DependencyName;
  status: DependencyStatus;
  latency_ms?: number | null;
  last_check_at: string;
  message?: string | null;
}

export interface AdminDependencyHealthResponse {
  dependencies: AdminDependencyHealth[];
  overall: DependencyStatus;
  generated_at: string;
}

// -----------------------------------------------------------------------------
// Strategies (admin view)
// -----------------------------------------------------------------------------

export type StrategyRiskRating = "low" | "medium" | "high" | "extreme";

export interface AdminStrategy {
  id: string;
  code: string;
  name: string;
  enabled: boolean;
  risk_rating: StrategyRiskRating;
  instances_count: number;
  running_count: number;
  default_params: Record<string, number | string | boolean>;
  updated_at: string;
}

export interface AdminStrategyUpdateRequest {
  enabled?: boolean;
  risk_rating?: StrategyRiskRating;
  default_params?: Record<string, number | string | boolean>;
}

// -----------------------------------------------------------------------------
// Subscriptions (admin view)
// -----------------------------------------------------------------------------

export interface AdminSubscription {
  id: string;
  user_id: string;
  user_email: string;
  plan: SubscriptionPlan;
  status: SubscriptionStatus;
  current_period_end?: string | null;
  cancel_at_period_end: boolean;
  amount_cents: number;
  currency: string;
  created_at: string;
}

export interface AdminGrantSubscriptionRequest {
  user_id: string;
  plan: SubscriptionPlan;
  duration_days?: number | null; // null => lifetime
  reason: string;
}

// -----------------------------------------------------------------------------
// Broadcast
// -----------------------------------------------------------------------------

export type BroadcastChannel = "in_app" | "email";
export type BroadcastAudience = "all" | "active" | "role" | "plan";

export interface BroadcastEstimate {
  audience_count: number;
  estimated_cost_usd_cents: number;
}

export interface BroadcastRequest {
  audience: BroadcastAudience;
  audience_role?: UserRole;
  audience_plan?: SubscriptionPlan;
  channel: BroadcastChannel;
  title: string;
  body: string;
}

export interface BroadcastResponse {
  id: string;
  audience_count: number;
  sent_at: string;
}

// -----------------------------------------------------------------------------
// Global kill switch
// -----------------------------------------------------------------------------

export type GlobalKillState = "armed" | "disarmed";

export interface GlobalKillStatus {
  state: GlobalKillState;
  engaged_at?: string | null;
  engaged_by_id?: string | null;
  engaged_by_email?: string | null;
  reason?: string | null;
  live_engines_count: number;
  /** When multi-admin approval is enforced, list of pending approvers. */
  pending_approvals?: { admin_email: string; requested_at: string }[];
}

export interface GlobalKillRequest {
  confirmation_phrase: string; // "ENGAGE GLOBAL KILL"
  reason: string;
}

export interface GlobalKillDisarmRequest {
  confirmation_phrase: string; // "DISARM GLOBAL KILL"
  reason: string;
}

// -----------------------------------------------------------------------------
// TOTP step-up
// -----------------------------------------------------------------------------

export interface TotpStepUpRequest {
  totp_code: string;
}

export interface TotpStepUpResponse {
  /** Short-lived token (~5 min) to include in `X-Step-Up-TOTP` header. */
  step_up_token: string;
  expires_at: string;
}

// -----------------------------------------------------------------------------
// User detail tabs
// -----------------------------------------------------------------------------

export interface AdminUserBrokerAccount {
  id: string;
  broker: string;
  label: string;
  account_type: string;
  is_active: boolean;
  last_connection_check_status?: string | null;
  created_at: string;
}

export interface AdminUserInstance {
  id: string;
  strategy_code: string;
  label: string;
  status: string;
  broker_account_label: string;
  created_at: string;
}

export interface AdminUserBacktest {
  id: string;
  strategy_code: string;
  status: string;
  net_profit?: number | null;
  created_at: string;
}

export interface AdminUserConsent {
  id: string;
  type: string;
  version: string;
  acknowledged_at: string;
}
