# Live Trading Launch Checklist — Production Gate

> The hard gate before any real money flows. Every 🔴 item is non-negotiable.
> **Author:** Argus Hayato | **Date:** 2026-06-15
> **Owner of gate:** Argus + Zeus + Daedalus + Hestia (4-eyes minimum)
> **Run cadence:** before first live user, before each major release, quarterly re-run.

---

## How to Use

- This document supersedes `security-checklist-pre-launch.md` for Phase 2 GA — that doc is incorporated by reference (Section P1 below confirms its closure).
- An item marked 🔴 is a **blocker**. If it is not green, we do not flip the live-mode flag for anyone.
- An item marked 🟡 is a **strong should**. We may launch with documented risk acceptance signed by Argus + Zeus.
- Mark each ✓ with date + verifier initials.
- Sign-offs at bottom. All four required.

---

## Section P1 — Phase 1 Checklist Closure

🔴 **P1.1** All items in `security-checklist-pre-launch.md` (sections A–N) signed off.
- [ ] Section A (Authentication & Access)
- [ ] Section B (Authorization)
- [ ] Section C (Secrets & Crypto)
- [ ] Section D (Network / Transport)
- [ ] Section E (Headers & CSP)
- [ ] Section F (Rate Limit & Quotas)
- [ ] Section G (Input Validation)
- [ ] Section H (Dependency / Supply Chain)
- [ ] Section I (Observability / Detection)
- [ ] Section J (Backup / DR)
- [ ] Section K (Kill Switch & Safety)
- [ ] Section L (Legal / Compliance)
- [ ] Section M (Penetration Test)
- [ ] Section N (Incident Response)

---

## Section S — Stripe (Live Mode)

🔴 **S1** Webhook signature verified in code (`stripe.Webhook.construct_event`), constant-time, with explicit tolerance window.
🔴 **S2** Idempotency table (`stripe_events`) UNIQUE constraint on `event.id`; tested by replaying the same event 5 times → granted once, ignored 4 times.
🔴 **S3** Stripe restricted API key in use; verified no `refunds:write`, no `transfers:write` scope.
🔴 **S4** Card data does not transit our backend (Checkout-hosted only). Verified by:
- (a) `grep -i -E 'card_number|cardNumber|cvv|cvc' frontend/ backend/` — no input field hits.
- (b) CSP `connect-src` audit — no `https://js.stripe.com` script ever fetched from non-payment pages.
🔴 **S5** Entitlement source-of-truth function `is_premium(user_id)` returns current state from `subscriptions` table; read on every premium action (not cached past 60s).
🔴 **S6** Webhook handlers wired for: `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.payment_failed`, `charge.refunded`, `charge.dispute.created`.
🔴 **S7** Daily reconciliation cron: pull Stripe subscriptions vs local `subscriptions` table; downgrade orphans; alert on diff.
🔴 **S8** Webhook secret rotated (initial value generated, not from dev).
🟡 **S9** Stripe Sigma / dashboard alerting configured for: high refund rate, high chargeback rate, suspicious volume.

---

## Section B — mt5-bridge (Live)

🔴 **B1** Tailscale or Cloudflare Tunnel deployed; bridge has NO public listener.
🔴 **B2** Bearer token rotated (initial value generated for Phase 2, not dev token).
🔴 **B3** Token never in logs — verified by full e2e in staging + `grep` for token in all logs (Loki, Sentry, Windows event log).
🔴 **B4** Constant-time comparison (`hmac.compare_digest`) unit-tested.
🔴 **B5** Symbol allowlist enforced (rejected symbol test passes).
🔴 **B6** Side validation enforced (BUY/SELL required; no wildcard).
🔴 **B7** Per-user lot cap + per-minute order cap enforced.
🔴 **B8** Stop-loss requirement enforced (missing SL → 400) — overridable only by founder.
🔴 **B9** Magic number namespace deployed; reconciliation job running.
🔴 **B10** HMAC envelope (timestamp + nonce + body sig) enforced on every order endpoint.
🔴 **B11** HMAC replay rejected (nonce dedup tested).
🔴 **B12** Windows VPS hardening checklist (in `mt5-bridge-security.md` Section 6) fully complete.
🔴 **B13** RDP behind Tailscale/VPN only — verified no public 3389.
🔴 **B14** Token rotation runbook tested in staging mid-trade.
🔴 **B15** Kill endpoint `/admin/halt` tested → all subsequent orders rejected until re-armed.

---

## Section L — Live Gate (7-Check Logic + TV extension)

🔴 **L1** Per-trade gate verified — engine re-checks all 7 gates before EVERY order send:
- [ ] L1.1 `live_mode_enabled = true`
- [ ] L1.2 `2fa_last_verified` within step-up window (5 min for sensitive, configurable)
- [ ] L1.3 `tos_accepted_version >= current_tos_version`
- [ ] L1.4 `plan_active and plan.allows_live = true`
- [ ] L1.5 `broker_connected and broker_balance >= min_required`
- [ ] L1.6 `kyc_tier >= required_tier`
- [ ] L1.7 `jurisdiction in allowed_set`
- [ ] L1.8 (if strategy is `tv_signal` family) `tv_disclaimer_consent_signed.version >= current_tv_version` AND `tv_health_status == healthy` AND `signal_age <= 300s`
🔴 **L2** Negative tests: for each of the 7 gates, force-fail it → engine blocks the order with audit + alert.
🔴 **L3** Race test (AS-P2-8): two go-live clicks simultaneously → only one succeeds for free-tier user.
🔴 **L4** TOCTOU test (AS-P2-12): mid-trade plan downgrade → next order blocked within 30s of state change.

---

## Section K — Kill Switch Chaos Test

🔴 **K1** Kill switch while signal in-flight (signal queued in Redis but not yet placed) → signal dropped, no order placed.
🔴 **K2** Kill switch while order pending at broker (sent but no fill yet) → order cancel attempted, audit recorded.
🔴 **K3** Kill switch while position open → position state captured; subsequent signals blocked; user notified; close-or-hold decision surfaced.
🔴 **K4** Kill switch endpoint has independent rate-limit lane (verified under simulated DDoS on other endpoints).
🔴 **K5** Auto-trigger tests:
- [ ] Max DD breach → kill + alert.
- [ ] Daily loss breach → kill + alert.
- [ ] Broker disconnect > 5 min → pause + alert.
- [ ] Abnormal slippage (>X bps from quote) → pause specific strategy + alert.
- [ ] Order rejection rate spike → pause + alert.

---

## Section H — HMAC Internal API

🔴 **H1** All backend → engine messages signed with `INTERNAL_API_SECRET` (HMAC-SHA256) + nonce + timestamp.
🔴 **H2** Engine rejects unsigned requests → tested.
🔴 **H3** Engine rejects bad-signed requests → tested.
🔴 **H4** Engine rejects stale timestamp (skew > 60s) → tested.
🔴 **H5** Engine rejects replayed nonce → tested.
🔴 **H6** mTLS in place between backend ↔ engine (separate from HMAC) — both must pass.

---

## Section D — Backup + DR Drill

🔴 **D1** Postgres backup encrypted (age/gpg) to R2 with object-lock 30d minimum.
🔴 **D2** Backup restore drill executed for **last 30 days** — at least one backup from each of the last 30 days successfully restored to staging.
🔴 **D3** Full disaster recovery drill: simulate full server loss → rebuild infra from scratch → restore data → app boots → smoke test passes. **Target: under 4 hours.** Timestamp documented.
🔴 **D4** Backup verification job: nightly `pg_restore --list` on most recent backup → fail = page on-call.
🔴 **D5** Cron overlap protection (flock) → tested by forcing slow backup to overlap.
🔴 **D6** Backup KEK separate from prod KEK; recovery procedure documented and tested.

---

## Section T — Tests / Pentest / Scans

🔴 **T1** External pentest: HackerOne triage / Detectify trial / Intigriti — at minimum 1-week run completed; all High+ findings resolved.
🔴 **T2** Internal pentest with OWASP ZAP active scan against staging → 0 High+ findings.
🔴 **T3** Burp Suite manual test of authentication flows (login, signup, reset, 2FA, step-up) → clean.
🔴 **T4** SQLi / NoSQLi sweep with sqlmap on staging → clean.
🔴 **T5** OWASP API Top 10 checklist (existing doc) signed off.
🔴 **T6** BOLA/IDOR walker test → 100% endpoints pass.

---

## Section U — Dependency Scans (All Clean — No High/Critical Open)

🔴 **U1** `pip-audit` on backend + trading-engine + mt5-bridge → clean.
🔴 **U2** `npm audit --audit-level=high` on frontend → clean.
🔴 **U3** Snyk (or alternative) → clean.
🔴 **U4** `trivy image` on all container images → clean.
🔴 **U5** SBOM generated (CycloneDX) per service; archived.

---

## Section O — Observability

🔴 **O1** Sentry: backend + frontend + engine + bridge all connected; before_send scrubber unit-tested.
🔴 **O2** Sentry alerts tested by forcing an error in staging → on-call received page.
🔴 **O3** Loki ingesting JSON from all services.
🔴 **O4** Prometheus + Grafana dashboards live for: 5xx, p99, auth-fail, kill-switch, broker connection, trade exec latency, bridge HMAC failures.
🔴 **O5** Alert rules wired (see existing checklist I5 + add Phase 2 ones):
- [ ] Stripe webhook signature failures > 5/min
- [ ] Bridge token auth failures > 3/min
- [ ] Live gate denials > N/min (could indicate misconfigured user OR active attack)
- [ ] Magic number collision detected
- [ ] Reconciliation diff (broker vs us) ≥ 1

---

## Section Sec — Production Secrets (Generated, Not From Dev)

🔴 **Sec1** Every secret in `secrets-audit.md` generated fresh for production; provenance documented (who generated, on which host, when).
🔴 **Sec2** Dev / staging secrets are different from prod; CI verifies no overlap.
🔴 **Sec3** `.env` files mode 0400, owned by service user.
🔴 **Sec4** Secrets distribution to hosts via SOPS / Doppler / 1Password / Bitwarden — never plain copy-paste from chat.
🔴 **Sec5** Rotation calendar in place; first rotation drill scheduled within 30 days of launch.

---

## Section N — DNS + Cloudflare

🔴 **N1** Registrar 2FA (hardware key preferred) — verified.
🔴 **N2** Registrar transfer lock + change lock enabled.
🔴 **N3** DNSSEC enabled on zone.
🔴 **N4** CAA records published.
🔴 **N5** Certificate Transparency monitoring active (Cert Spotter / sslmate / Facebook CT) → alerts → known channel.
🔴 **N6** Cloudflare account 2FA on all members; least-privilege roles.
🔴 **N7** Cloudflare WAF: OWASP Core Rule Set ON; custom rules deployed; tested.

---

## Section X — External Ratings

🔴 **X1** SSL Labs `ssllabs.com/ssltest` → **A+** rating on `app.<domain>` and `api.<domain>`.
🔴 **X2** Mozilla Observatory `observatory.mozilla.org` → **A+** rating.
🔴 **X3** `securityheaders.com` → **A+** rating.
🟡 **X4** `dnscheck.tools` / `internet.nl` checks green.

---

## Section C — Compliance / Legal

🔴 **C1** Terms of Service + Privacy Policy + Risk Disclosure published.
🔴 **C2** ToS + Privacy reviewed by qualified lawyer (Thailand fintech + GDPR-aware).
🔴 **C3** Cookie banner live with granular controls; no tracking pre-consent.
🔴 **C4** Geo-block list active (US blocked, restricted SEA jurisdictions blocked pending review).
🔴 **C5** OFAC / sanctions check on signup.
🔴 **C6** DPAs signed with Stripe, Sentry, Cloudflare, email provider, R2.
🔴 **C7** DSAR endpoint live + tested.
🔴 **C8** Erasure endpoint live + 30-day grace tested.
🔴 **C9** PDPA/GDPR breach notification template ready; lead DPA identified.
🟡 **C10** SOC2 readiness scan (Vanta trial / Drata trial / manual) — at least gap list known.
🟡 **C11** Cyber + E&O insurance coverage check (if available; Phase 3 for many TH startups — accept residual).

---

## Section U — User Onboarding for Live

🔴 **U-Live1** Typed-confirmation phrase required to enable live ("ENABLE LIVE TRADING") — exact match.
🔴 **U-Live2** 2FA required and recently verified to enable live.
🔴 **U-Live3** Signed consent (audit-logged) acknowledging risk disclosure version.
🔴 **U-Live4** Live mode toggle requires re-auth + email confirmation code.
🔴 **U-Live5** Minimum default position size capped (e.g., 0.01 lot) for first 24h after enable; raised gradually with explicit user opt-in.

---

## Section TV — TradingView Strategy Family (Phase 3a)

> Added 2026-06-16. Applies to any user enabling a `tv_signal`-family strategy in live mode. Reads with `tradingview-integration-risk.md` + `disclaimers-v2.md`.

🔴 **TV1** `tv_disclaimer_consent_signed` v2 present in `audit_log` for the user — version 2 with TV-specific text. Verified by live-gate query before EVERY order in `tv_signal` family.
🔴 **TV2** TV health check passing — `scanner.tradingview.com` queried on stable symbol (`EURUSD`, `1h`) every 2 min; auto-halt on 3 consecutive failures wired + tested.
🔴 **TV3** `tv_strategy_min_paper_days` — strategy ran in paper mode with TV-source signals (not local-indicator signals) for at least 14 calendar days; performance baseline captured.
🔴 **TV4** Schema validation Pydantic model deployed for TV response; CI fixture test green; schema-mismatch test → engine rejects + alerts.
🔴 **TV5** Throttle deployed: 4 concurrent TV requests max, 0.8s spacing; load-tested at 100 simulated previews/min.
🔴 **TV6** Server-side cache (60s per symbol+interval) deployed; cache hit-rate visible in Grafana.
🔴 **TV7** ADR `adr-XXXX-tradingview-signal-source.md` filed with: trade-offs, ToS risk, Plan B (paid TV API or Yahoo Finance fallback).
🔴 **TV8** Privacy Policy v2026-Q3 + ToS v2026-Q3 + Risk Disclosure v2026-Q3-TV live to users; lawyer-reviewed; in-app re-consent banner for existing users on next login.
🔴 **TV9** SBOM updated (`sbom-update.md`) with `tradingview-mcp-server@0.7.x` + `tradingview-ta@3.3+`; pinned in lockfile with hashes; CycloneDX artifact archived.
🔴 **TV10** IR playbooks IR-P2-6 (TV API down) + IR-P2-7 (TV silent wrong data) signed off; tabletop run for at least IR-P2-6.
🔴 **TV11** Signal `generated_at` embedded at ingest; max-age check (5 min) wired into live-gate; halt on 3 consecutive stale ticks tested.
🔴 **TV12** TV adapter runs in isolated worker — no access to `broker_credentials`, no access to KEK; egress allowlist (scanner.tradingview.com + api.tradingview.com + internal); verified.
🔴 **TV13** Multi-TF agreement enforced in default `tv_signal` templates (e.g., 4H + 1H must both indicate same direction).
🔴 **TV14** UI labels every TV-sourced signal/order with "Source: TradingView (informational, not advice). User chose threshold."
🟡 **TV15** Cross-source verification plan documented (Phase 4 — Yahoo Finance crosscheck).
🟡 **TV16** TradingView business team contacted for licensing conversation (post-launch).

---

## Section F — First Live User

🔴 **F1** First live user is **YOU (founder)** with smallest position size (0.01 lot or equivalent).
🔴 **F2** First-user trades closely monitored: real-time dashboard, on-call Argus + Atlas + Kairos for 24h.
🔴 **F3** First-user account uses isolated MT5 broker account (low balance), NOT main brokerage.
🔴 **F4** First-user kill switch test executed before live: kill while in position → close → confirm.
🔴 **F5** First-user post-mortem within 7 days regardless of outcome (lessons learned).
🟡 **F6** Closed beta: next 5–10 users invited only; explicit "this is beta, accept" gate.

---

## Section ADMIN — Phase 3.5 Admin Privileged Access (added 2026-06-16)

🔴 **AD1** `require_admin` middleware re-fetches role from DB every request (JWT role claim ignored). Integration test in CI.
🔴 **AD2** Step-up TOTP enforced on every destructive admin op (impersonate, delete user, ban, broadcast, kill, role change, sub override). Test matrix covers each.
🔴 **AD3** Audit log table is append-only (DB role: INSERT+SELECT only for app user). Daily hash-chain integrity check job scheduled.
🔴 **AD4** First admin (seeded) has rotated password from seed value `.Master6728` (length 11, borderline weak — must be replaced).
🔴 **AD5** First admin has enrolled TOTP + downloaded backup codes (stored in password manager).
🔴 **AD6** Self-protection rules verified: cannot demote/ban/delete self, cannot disable own TOTP, cannot impersonate self, cannot approve own multi-admin request.
🔴 **AD7** Impersonation token blocks destructive ops + `/admin/*` + impersonation of admin/self. Test matrix covers each restriction.
🔴 **AD8** Multi-admin approval (n=2) implemented for: global kill switch, demote/ban/delete another admin, bulk delete > 50, mass broadcast > 10k, KEK rotation.
🟡 **AD9** At least 2 admins provisioned post-launch (avoid single-point-of-failure for multi-approval). Strongly recommended within 30 days.
🟡 **AD10** `ADMIN_IP_ALLOWLIST` configured for production (office + on-call home network CIDRs).
🟡 **AD11** Weekly audit log review process scheduled (owner: Argus + second admin). Calendar invite created.
🟡 **AD12** Quarterly admin access review process scheduled (revoke dormant, re-attest acceptable use).
🟡 **AD13** Anomaly detection (new country, UA, Tor) connected to Slack #security-incidents + email.
🟡 **AD14** Admin onboarding runbook (`/docs/security/admin-onboarding-runbook.md`) shared with all admins; signed acceptable use on file.
🟡 **AD15** Cron job revoking admin tokens > 24h scheduled and tested.
🟡 **AD16** Breakglass procedure tabletop-tested (don't activate in prod for drill; walk through).
🟡 **AD17** Threat model `/docs/security/threat-model-admin.md` reviewed by Daedalus + Atlas + Eos.
🟡 **AD18** Incident response `/docs/security/incident-response-admin.md` reviewed; on-call PagerDuty schedule populated.

---

## Section I — Insurance / Liability

🟡 **I1** Cyber insurance quote obtained (even if not bound yet).
🟡 **I2** Errors & Omissions / Professional Indemnity policy quote.
🟡 **I3** Liability cap in ToS reviewed by lawyer (enforceability in TH + EU).

---

## Sign-off

NO LIVE FLAG FLIPPED WITHOUT ALL FOUR:

```
Argus Hayato (Security):  __________  Date: __________
Daedalus Souta (Tech):    __________  Date: __________
Zeus Ryujin (PM/Legal):   __________  Date: __________
Hestia (Ops):             __________  Date: __________
```

Any 🔴 item not green → at least one signer must REJECT.
Any 🟡 item not green → documented risk acceptance attached.

---

## Post-Launch Drill Schedule

- **Day 1**: founder live with 0.01 lot.
- **Day 7**: first post-mortem regardless of outcome.
- **Day 14**: kill switch chaos drill in prod (off-hours, sandboxed user).
- **Day 30**: secret rotation drill (JWT key rotate, no impact).
- **Day 60**: backup restore drill (full).
- **Day 90**: pentest re-run; checklist re-attest.
