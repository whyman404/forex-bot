/**
 * i18n stub — MVP serves English only.
 * To add a language:
 *   1. Create `messages.<locale>.json` with the same keys.
 *   2. Import it here and switch on `locale` (read from cookie / `Accept-Language`).
 *   3. Replace `messages` with a runtime-resolved object.
 *   4. Wrap consumers with a React context provider exposing `t` + `locale`.
 *
 * Keys are dot-notated so future grouping (`onboarding.step1.title`) stays stable.
 */

const messages = {
  en: {
    "common.continue": "Continue",
    "common.cancel": "Cancel",
    "common.skip": "Skip",
    "common.back": "Back",
    "common.done": "Done",
    "common.loading": "Loading…",
    "common.error": "Something went wrong",

    "onboarding.title": "Welcome aboard",
    "onboarding.subtitle": "Four quick steps to start trading safely.",
    "onboarding.step1.title": "Verify your email",
    "onboarding.step1.body": "Confirm your address so we can send security and trade alerts.",
    "onboarding.step1.cta": "Resend verification email",
    "onboarding.step1.done": "Verified",
    "onboarding.step2.title": "Enable two-factor",
    "onboarding.step2.body": "Required before live trading. Use any authenticator app.",
    "onboarding.step3.title": "Connect a broker",
    "onboarding.step3.body": "Connect Exness MT5 — or skip to keep using paper mode.",
    "onboarding.step3.skip": "Skip and use paper mode",
    "onboarding.step4.title": "Pick a strategy",
    "onboarding.step4.body": "We will spin up a paper instance you can grow into live trading.",
    "onboarding.skip": "Skip onboarding",
    "onboarding.complete": "You are all set!",

    "billing.title": "Plans & billing",
    "billing.current_plan": "Current plan",
    "billing.subscribe": "Subscribe",
    "billing.manage": "Manage billing",
    "billing.invoices": "Invoices",
    "billing.return.activating": "Activating your subscription…",
    "billing.return.success": "Subscription activated",
    "billing.return.timeout": "Still processing. Refresh in a minute.",

    "live.gate.email_verified": "Email verified",
    "live.gate.totp_enabled": "Two-factor enabled",
    "live.gate.subscription_active": "Active subscription",
    "live.gate.backtest_quality": "Backtest profit factor > 1.3, drawdown < 25%",
    "live.gate.paper_track_record": "Paper trading ≥ 14 days, ≥ 10 trades",
    "live.gate.broker_connected": "Broker connected",
    "live.gate.broker_min_balance": "Minimum balance reached",
    "live.gate.kill_switch_off": "Kill switch off",
    "live.gate.live_consent_signed": "Risk disclosure signed",
    "live.modal.title": "Go Live — Trade real money",
    "live.modal.confirm_phrase": "Type GO LIVE to enable real-money trading",
    "live.modal.cta": "Enable live trading",
    "live.revert.title": "Revert to paper trading",
    "live.revert.cta": "Revert",
    "live.badge": "LIVE TRADING — REAL MONEY",
    "live.emergency_stop": "Emergency stop",

    "settings.gdpr.title": "Privacy & data",
    "settings.gdpr.export": "Export my data",
    "settings.gdpr.export.note": "We'll email you a download link within 24 hours.",
    "settings.gdpr.delete": "Delete account",
    "settings.gdpr.delete.note": "30-day grace period before permanent purge.",
    "settings.consent.title": "Consent log",

    "risk.disclaimer.title": "Risk disclosure",
    "risk.disclaimer.body":
      "Trading leveraged products carries a high level of risk. You may lose more than your deposit. Past performance does not guarantee future results. Only trade with funds you can afford to lose.",
    "risk.disclaimer.acknowledge": "I understand and accept the risks",
  },
} as const;

type Dictionary = typeof messages.en;
type MessageKey = keyof Dictionary;

export type Locale = keyof typeof messages;

let activeLocale: Locale = "en";

/** Set the active locale (for future runtime switching). */
export function setLocale(locale: Locale): void {
  activeLocale = locale;
}

export function getLocale(): Locale {
  return activeLocale;
}

/**
 * Translate a key with optional `{placeholder}` interpolation.
 * Missing keys fall back to the key itself in dev so designers spot them quickly.
 */
export function t(key: MessageKey, params?: Record<string, string | number>): string {
  const dict = messages[activeLocale] ?? messages.en;
  const raw: string = dict[key] ?? key;
  if (!params) return raw;
  return Object.entries(params).reduce<string>(
    (acc, [k, v]) => acc.replace(new RegExp(`\\{${k}\\}`, "g"), String(v)),
    raw,
  );
}
