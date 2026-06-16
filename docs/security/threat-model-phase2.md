# Threat Model — Phase 2 (Live Trading) Additions

> Real money. Real Stripe. Real MT5 orders. Real PII flowing through email.
> **Author:** Argus Hayato | **Date:** 2026-06-15 | **Status:** v2.0 (Phase 2 pre-launch)
> **Reads with:** `threat-model.md` (Phase 1, v1.0) — this file extends, does not replace.

---

## 0. Executive Summary — What Changed Since Phase 1

Phase 1 was scaffolding: mocked broker, mocked payments, paper trading only. Phase 2 lights up the surfaces we were modeling. Every "we'll handle that later" item is now a live target.

**New surface this round (and why each matters):**

| # | New component | Why it changes the threat picture |
|---|---|---|
| N1 | **Stripe** (live mode) | Real money flows. Webhook now grants paid features → spoof = free premium. Refund flow = financial loss. |
| N2 | **Email service** (Resend/Postmark/SES) | Password reset = account takeover vector. SPF/DKIM/DMARC mis-config = phishing. Provider compromise = mass impersonation. |
| N3 | **mt5-bridge** (Windows VPS, FastAPI on `mt5-bridge/`) | Token-authenticated HTTP gateway placing **real orders**. Token leak = drain user accounts. Symbol/side spoofing risk. |
| N4 | **Live trading engine** | Paper → real. Bad signal = real loss. Insider strategy push = adversarial trading. |
| N5 | **Caddy edge** | New edge proxy in front of API. Misconfig = internal services exposed. |
| N6 | **Production secrets** generated for the first time | Not dev secrets carried forward. Distribution path = blast radius. |

**Crown jewels (Phase 2, updated rank):**

1. **mt5-bridge bearer token** — leak = real-time order injection on every connected user. **NEW #1 jewel.**
2. **MT5 broker credentials** (per user, AES-256-GCM) — unchanged from Phase 1.
3. **JWT signing key** — unchanged.
4. **Stripe webhook secret** + **Stripe restricted key** — controls subscription entitlement + refund flows.
5. **Email provider API token** — password reset hijack + brand impersonation.
6. **KEK** (envelope encryption key for credentials).
7. **INTERNAL_API_SECRET** (HMAC for backend → engine signed messages).

**Highest residual risk after Phase 2 mitigations:**

- **R-P2-1.** mt5-bridge token in environment file on Windows VPS — RDP compromise = token theft. Mitigated by Tailscale/CF Tunnel + rotation + symbol/side allowlist; residual relies on Windows hardening.
- **R-P2-2.** Email provider compromise as supply chain — out of our direct control. Mitigated by SPF/DKIM/DMARC, dual-channel verify on sensitive ops, monitoring.
- **R-P2-3.** Stripe event replay / out-of-order processing — mitigated by idempotency table + signature + tolerance; residual relies on key rotation hygiene.
- **R-P2-4.** Insider with merge rights pushing adversarial strategy — mitigated by CODEOWNERS + 2-approver + cosign + canary, but human process risk remains.

---

## 1. New Components — STRIDE

### N1. Stripe (live)

| STRIDE | Threat | Mitigation | Residual |
|---|---|---|---|
| S | Webhook spoof (`POST /webhooks/stripe` from attacker IP) | Verify `Stripe-Signature` with `STRIPE_WEBHOOK_SECRET`, constant-time compare, 5-min tolerance window | L |
| S | Forged customer in `customer.subscription.created` | Resolve customer from Stripe API by ID before granting entitlement (don't trust event payload alone) | L |
| T | Replay of `payment_intent.succeeded` to repeatedly extend subscription | Idempotency table keyed on `event.id` UNIQUE constraint; reject duplicates | L |
| T | Tampered metadata (`metadata.user_id` swapped to attacker) | Always resolve user via `customer.id` mapped in our DB, never trust metadata client-controllable fields | M |
| R | "I cancelled, you charged me again" disputes | Persist full event JSON + decision + actor; surface to user in billing history | L |
| I | Cardholder data in our logs | NEVER receive PAN — Stripe Checkout (hosted) only, webhooks carry metadata only. See `stripe-pci-scope.md` | L |
| I | Restricted key leaked from CI | Stripe restricted key (read+subscription mgmt, NO refund/transfer) + secret rotation 90d + GitHub OIDC + Sentry scrubber | M |
| D | Webhook flood (e.g., during Stripe outage retries) | Queue webhook to background worker (Redis), respond 200 quickly, dedup by event.id | L |
| E | Stripe key leak grants refund power | Use restricted key without refund scope; refunds via dashboard manual + dual-approval | M |

### N2. Email Service (Resend / Postmark / SES — provider TBD)

| STRIDE | Threat | Mitigation | Residual |
|---|---|---|---|
| S | Phisher sends email from `support@<our-domain>` | SPF + DKIM + DMARC `p=reject` (`v=DMARC1; p=reject; rua=...`), verified domain in provider | L |
| S | Phisher sends from look-alike domain (`our-c0mpany.com`) | Register typo-squat domains; brand monitoring (Phase 3 paid service) | M |
| T | Reset link tampering (token swapped to attacker's account) | Token signed (HMAC or random + DB hash lookup), single-use, 15-min TTL, bind to email | L |
| R | "I never asked to reset" disputes | Audit log every reset request + IP + UA; show user a "recent activity" view | L |
| I | Reset link in email body searchable in cloud mailbox if attacker compromises mailbox | Two-channel for high-value: confirm via in-app + email; tokens short TTL; one-time-use | M |
| I | Provider stores message body indefinitely with our subject line "Reset password for jane@x.com" | Provider DPA; minimize PII in subject; use generic "Action required on your account" | M |
| D | Email provider rate-limits us during incident | Backup secondary provider for password reset (Phase 3); allow login via 2FA bypass code as fallback | M |
| E | Provider API token compromise = send-as-us platform-wide | Rotation, IP allowlist, restricted scope (transactional only), alert on send anomaly | **H** |

### N3. mt5-bridge (Windows VPS)

| STRIDE | Threat | Mitigation | Residual |
|---|---|---|---|
| S | Anyone hitting bridge port with no auth | Bearer token required on every endpoint, constant-time compare | L |
| S | Stolen token used from internet | Tailscale / CF Tunnel preferred (no public port); else UFW+token; IP allowlist | M |
| T | Order body tampered ("change side BUY→SELL on user X") | Order envelope HMAC with `INTERNAL_API_SECRET`, includes nonce+timestamp; bridge verifies | L |
| T | Strategy/magic-number collision lets cross-user signal land on wrong account | Magic number namespace per (user_id, strategy_id) hashed → unique; per-account binding enforced | L |
| R | "Bridge placed wrong trade" no log | Per-order trace ID; broker ticket ID returned + stored; pre/post snapshot | L |
| I | Token logged in access log | Token never logged — derive `audit_id = sha256(token)[:16]`, log `audit_id` only | L |
| I | MT5 credential read from VPS memory | Decrypt-just-in-time, zero buffers; no swap on Windows (accept residual); BitLocker FDE on VPS | **H** |
| D | Bridge OOM / hang stalls all live trading | Health endpoint, watchdog, auto-restart, alert on >30s unresponsive | M |
| E | Bridge process exec'd by attacker → RCE | No `eval`/`exec` on input; `pickle.loads` banned; deps hash-pinned; Windows Defender; AppLocker | **H** |

### N4. Live Trading Engine (was Paper in Phase 1)

| STRIDE | Threat | Mitigation | Residual |
|---|---|---|---|
| S | Spoofed signal from "backend" to engine | mTLS + HMAC envelope on every signal (already from Phase 1; now must be verified in code path) | L |
| T | Adversarial strategy push by insider | Cosign-signed strategy bundle; engine verifies signature on load; CODEOWNERS 2-approve; canary in paper N days | M |
| T | Strategy params tampered via DB | Params signed at write time (HMAC), engine verifies on load; or move params to signed config bundle | M |
| R | "Engine placed wrong trade" — no audit | Per-signal trace_id, broker ticket ID, snapshot of inputs and outputs to `audit_log` | L |
| I | Strategy alpha leak (params readable to all admins) | RBAC on `strategies` table — only owner + designated reviewer; encrypt params at rest | M |
| D | Strategy infinite loop / leak | Process-per-strategy with watchdog + memory cap; kill on timeout | M |
| E | RCE via params JSONB (eval-like patterns in strategy code) | NEVER `eval`/`exec` on params; strict schema for params (Pydantic); whitelist param keys per strategy_code | **H** (until covered by AS-13) |

### N5. Caddy Edge

| STRIDE | Threat | Mitigation | Residual |
|---|---|---|---|
| S | Origin pulled from `Host` header to attacker domain | Strict Caddyfile with explicit `bind` per host, no wildcard origin reflection | L |
| T | Caddy auto-TLS storage tampered | `/data/caddy` mode 0700, owned by `caddy` user only, backed up encrypted | L |
| R | Missing access log | `log` directive on every site block, ship to Loki | L |
| I | Backend headers (`Server`, stack traces) reach client | Strip `Server` header; `header_down -Server`; sanitize error pages | L |
| I | Internal service exposed via misconfig (admin panel reachable from internet) | Default-deny upstream; explicit `reverse_proxy` per path; path-prefix lockdown; verify with `curl` from public IP | **H** (config drift risk) |
| D | Caddy itself overwhelmed | Place behind Cloudflare; rate-limit at Caddy too; concurrent stream cap | M |
| E | Caddy admin API on `:2019` accessible | Disable admin API in prod (`admin off`) or bind to `127.0.0.1` with firewall | L |

---

## 2. Fifteen New End-to-End Attack Scenarios

Each scenario tagged: **STRIDE class**, mitigation, residual risk, owner.

### AS-P2-1. Stripe Webhook Spoof + Replay
**STRIDE:** S+T
**Attack path:** Attacker scrapes our webhook endpoint URL (publicly known by virtue of Stripe's "test webhook" or by guessing `/webhooks/stripe`). Crafts a fake `checkout.session.completed` event referencing victim user. POSTs to endpoint. If signature not verified → grant. If signature verified but no idempotency → captured legitimate event replayed N times → repeated subscription extensions.
**Mitigation:**
- `stripe.Webhook.construct_event(payload, sig_header, secret)` — library handles signature + tolerance.
- `event.id` UNIQUE constraint in `stripe_events` table; INSERT before processing; on conflict do nothing.
- Webhook secret distinct from API key; rotated quarterly.
- Cross-check: resolve `customer.id` via Stripe API; ignore client-controllable metadata for entitlement decisions.
**Residual:** Low.
**Owner:** Argus + Atlas. **Gate:** F1 webhook idempotency test in pre-launch checklist.

### AS-P2-2. Email Account Takeover via Password Reset Token Leak
**STRIDE:** S+I+E
**Attack path:** Reset token transmitted in email URL ends up in (a) referrer header to third-party tracker on landing page, (b) browser history on shared machine, (c) provider mailbox compromise. Attacker uses token within TTL → takes over account.
**Mitigation:**
- Token: 32 bytes from `secrets.token_urlsafe(32)`; **store SHA-256 hash** in DB, never plaintext.
- TTL: 15 min for password reset, 1 hour for email verify.
- Single-use: invalidate on first use; invalidate all outstanding tokens on successful reset.
- Reset page sets `Referrer-Policy: no-referrer` and `Cache-Control: no-store`.
- Reset confirmation **also requires** current 2FA code if 2FA is enabled (don't let reset bypass 2FA).
- Rate-limit reset request: 3 per hour per email; non-disclosing response ("if account exists, link sent").
- Email provider DPA + minimize PII in subject line.
**Residual:** Medium — provider mailbox compromise still possible.
**Owner:** Argus + Atlas. **Gate:** A3 + A4 in pre-launch checklist + new "reset token" test.

### AS-P2-3. mt5-bridge Token Exfiltration → Unauthorized Live Orders
**STRIDE:** S+T+E
**Attack path:** Attacker compromises Windows VPS (RDP brute force, malicious browser plugin used during admin session, leaked token in screenshot) → reads `BRIDGE_TOKEN` from environment / config → calls bridge directly placing arbitrary orders on every user account currently connected.
**Mitigation:**
- **Network**: Tailscale or Cloudflare Tunnel (preferred) so bridge has NO public listener. Acceptable alternative: public + UFW IP allowlist of backend VPS only. Not recommended: public + token only.
- **Token**: stored in Windows DPAPI-protected file or `secret.json` mode-locked; never in screenshots; not in `set` output (clear env after spawn).
- **Token rotation**: quarterly + immediately on RDP login from unexpected IP.
- **Symbol + side allowlist**: bridge validates symbol against per-user allowlist; rejects unknown.
- **Magic number namespace**: bridge tags every order with `magic = hash(user_id, strategy_id) % 2^31`; cross-namespace order = reject.
- **Max lot per order + max orders per minute** server-side.
- **Audit**: every order → trace_id → broker ticket ID; daily reconcile with backend; diff alert.
**Residual:** Medium-High — VPS hardening is the residual control.
**Owner:** Argus + Hestia + Daedalus. **Gate:** see `mt5-bridge-security.md`.

### AS-P2-4. Insider Modifies Strategy Params for Adversarial Trades
**STRIDE:** T+E
**Attack path:** Engineer with DB write access UPDATEs `strategies.params` JSONB to set extreme leverage, inverted entry logic, or martingale doubling on a target user's strategy. Engine reloads → adversarial trades execute → user loss benefits attacker (or just sabotage).
**Mitigation:**
- **Params signed** at write time (HMAC of canonical JSON with `INTERNAL_API_SECRET`); engine refuses unsigned/mismatched params.
- **All DB writes to `strategies`** flagged in audit log with actor + before/after diff; Slack alert.
- **2-person rule** for `INTERNAL_API_SECRET` access (split-knowledge / 4-eyes if practical).
- **Canary**: any params change goes paper-mode for N hours on canary account before live propagation.
- **Param schema enforcement**: per `strategy_code`, only whitelisted keys + bounded ranges; engine rejects out-of-range on load.
**Residual:** Medium — human process risk.
**Owner:** Argus + Kairos + Daedalus.

### AS-P2-5. Live Engine Signal Injection from Compromised INTERNAL_API_SECRET
**STRIDE:** S+E
**Attack path:** Attacker exfiltrates `INTERNAL_API_SECRET` from backend VPS env → crafts a valid signed signal as if from backend → engine accepts → places orders.
**Mitigation:**
- Mutual TLS between backend ↔ engine (cert-based, not just shared secret) → makes shared-secret leak alone insufficient.
- HMAC envelope adds `nonce` (replay protection) + `timestamp` (5-min skew window).
- Engine **per-user gates**: live mode ON? Within trade window? Within risk budget? Symbol allowlisted? Rejects regardless of valid HMAC if gates fail.
- Engine logs every accepted signal with source IP + cert fingerprint; alert on cert mismatch.
- Secret rotation quarterly; rotation drill in runbook.
**Residual:** Low (with mTLS) — Medium (HMAC alone).
**Owner:** Argus + Atlas + Kairos.

### AS-P2-6. DNS Hijack → Fake Login Page → Credential Theft
**STRIDE:** S+I
**Attack path:** Attacker compromises our registrar account (credential reuse, SIM swap on owner phone) → repoints `app.<our-domain>` to attacker-controlled IP serving a clone → users enter creds → forwarded to real backend (or just stolen).
**Mitigation:**
- **Registrar 2FA mandatory** (hardware key preferred) — separate from any team password manager.
- **Registry lock** at registrar (transfer lock + change lock requires manual verification).
- **DNSSEC** on the zone.
- **HSTS preload** so browsers refuse non-HTTPS for our domain.
- **Certificate Transparency monitoring**: alert on new cert issued for our domain (could detect attacker getting LE cert) — Cert Spotter / Facebook CT API.
- **CAA records**: `0 issue "letsencrypt.org"` + `0 issuewild ";"` (no wildcard from anyone).
- **Email** in login flow: post-login alert "new device" → user sees notification on real channel.
**Residual:** Medium — depends on registrar account hygiene.
**Owner:** Argus + Zeus.

### AS-P2-7. Caddy Misconfig Exposing Internal Services
**STRIDE:** I+E
**Attack path:** A new internal route (`/_internal/metrics` or `/admin`) added to backend. Caddyfile path prefix matched too broadly. Endpoint becomes reachable from internet → metrics scraped / admin probed.
**Mitigation:**
- **Default-deny** in Caddy: explicit `handle_path /api/v1/*` block; `handle` catch-all returns 404.
- **Path allowlist test**: CI runs `curl` against staging Caddy from external IP for a known list of internal paths and asserts 404.
- **Admin endpoints** require not just auth but also network ACL (e.g., on private link + auth) — defense in depth.
- **Internal services** bind to `127.0.0.1` so even if Caddy mis-routes, the upstream isn't externally reachable.
- **`admin off`** in Caddy global options (no `:2019` admin API in prod).
**Residual:** Medium — config drift over time.
**Owner:** Argus + Hestia.

### AS-P2-8. Race Condition on Go-Live (Double-Spend of Subscription Quota)
**STRIDE:** T+E
**Attack path:** User on free tier (limited to 1 live strategy) clicks "Go Live" twice on different strategies within milliseconds → both pass the "count active < 1" check before either inserts → both go live.
**Mitigation:**
- **DB-level uniqueness**: partial unique index `WHERE is_live=true` on `(user_id)` for plan tier 'free' OR row-level `FOR UPDATE` lock on `users.row` during go-live transaction.
- **Application-level check + insert in single transaction** with `SELECT … FOR UPDATE` on the quota row.
- **Idempotency token** on go-live request (client-supplied UUID) — second click within X seconds returns the first result.
**Residual:** Low.
**Owner:** Argus + Atlas + Mnemosyne.

### AS-P2-9. Refund-Then-Keep-Using Attack (Cancel + Active Subscription Handling)
**STRIDE:** R+E
**Attack path:** User pays for premium → uses 30 days → requests Stripe chargeback → Stripe refunds → our system never receives `charge.refunded` (webhook misfire) or processes it incorrectly → user continues using premium.
**Mitigation:**
- **Webhook listeners** for: `charge.refunded`, `charge.dispute.created`, `customer.subscription.deleted`, `customer.subscription.updated` (status change). Each downgrades entitlement immediately.
- **Daily reconciliation job**: fetch active Stripe subscriptions, compare to `subscriptions` table; downgrade orphans.
- **Chargeback policy**: chargeback = immediate downgrade + audit; if abuse pattern, ban + log.
- **Entitlement check on every premium action** (not just on login) — single source of truth `is_premium(user_id)` reading current state.
**Residual:** Low.
**Owner:** Argus + Atlas + Zeus.

### AS-P2-10. GDPR Data Export Endpoint → Mass Scraping
**STRIDE:** I+D
**Attack path:** `/users/me/export` returns full user data (trades, strategies, params). Attacker creates many free accounts + populates with bait data + scrapes via this endpoint as a "data dump leakage map".
**Mitigation:**
- **Rate-limit aggressively**: 1 export per user per 24h.
- **Throttle by IP**: 3 exports per IP per 24h.
- **Async delivery**: enqueue request; email signed link valid 1 hour; one download allowed.
- **Scope minimization**: export contains the user's own data only — never includes "what we ranked them against," strategy templates we own, or other users' aggregate stats.
- **Account age gate**: account must be > 7 days old to export (anti-burner).
- **2FA required** for export request.
**Residual:** Low.
**Owner:** Argus + Atlas + Zeus.

### AS-P2-11. User Account Merge Bug → Orphan broker_account Access
**STRIDE:** T+E
**Attack path:** User signs up twice (typo email then corrects), customer support "merges" by updating `broker_credentials.user_id` to canonical account. Orphan original account still has session token cached → can decrypt creds via API path that didn't re-verify ownership at every step.
**Mitigation:**
- **No account merge feature** initially (Phase 2 — defer).
- If/when added: only via admin runbook + explicit transactional move + invalidate ALL sessions of both source + target + force re-auth.
- Every API path that returns broker_credentials re-checks `owner_id == current_user.id` at fetch time (default in `OwnedResource` base repo from Phase 1).
- Audit log on every credential read.
**Residual:** Low (Phase 2 — feature deferred).
**Owner:** Argus + Atlas.

### AS-P2-12. Time-of-Check vs Time-of-Use on Live Gate
**STRIDE:** T+E
**Attack path:** User passes 7 live-gate checks (2FA, T&C, KYC tier, plan, balance, risk acknowledged, jurisdiction). Two of those (balance, plan) checked once at toggle. User then downgrades plan / withdraws → trades continue with stale "premium" entitlement until next check at midnight.
**Mitigation:**
- **Per-trade live gate**: engine re-checks 7 gates **before every order send**:
  1. live_mode_enabled
  2. 2fa_recent (within step-up window)
  3. tos_version_accepted >= current
  4. plan_active and includes_live
  5. broker_connected and balance >= min
  6. kyc_tier sufficient
  7. jurisdiction allowed
- **Cache invalidation**: any state change publishes Redis event; engine subscribes; invalidates cached gate within seconds.
- **Hard rule**: when in doubt → pause (not trade).
**Residual:** Low.
**Owner:** Argus + Kairos + Atlas.

### AS-P2-13. Strategy Code Injection via Params JSONB (eval-like patterns)
**STRIDE:** T+E
**Attack path:** Strategy code uses `getattr(self, params['method_name'])(...)` or constructs lambdas from `params['expression']` → user crafts params that invoke arbitrary methods or evaluate Python expressions → RCE in engine process.
**Mitigation:**
- **NO `eval` / `exec` / `compile`** in strategy or engine code — ban via lint (`ruff S307`, `bandit B102/B302/B307`).
- **NO `getattr(obj, user_input)`** patterns; if dispatch needed, explicit `dict[str, Callable]` whitelist.
- **NO `pickle.loads`** on anything from DB/network/file.
- **Pydantic schema per strategy_code**: `params` validated against `Strategy.params_schema` — extra keys forbid, types/ranges constrained.
- **Process isolation**: strategy runs in separate process with restricted environment (no FS write outside scratch dir, no network outside broker, OS-level seccomp if Linux).
- **CI grep gate**: fail build on `eval(`, `exec(`, `pickle.loads(`, `yaml.load(`, `subprocess(...shell=True)`, `getattr.*request|params|input`.
**Residual:** Medium — relies on lint coverage + reviewer vigilance.
**Owner:** Argus + Kairos + Themis.

### AS-P2-14. Cron Job Overlap → Duplicate Backups Corrupting Target
**STRIDE:** T+D
**Attack path:** Daily backup cron takes longer than expected (DB growth) → next day's job starts while previous still writing → both write to same target file → corruption → next restore fails silently → silent data loss until needed.
**Mitigation:**
- **Lockfile** in backup script (`flock`-based); second invocation exits with alert.
- **Timestamped target paths**: `backup-YYYY-MM-DDTHH-MM-SS-uuidv7.dump.age` — no overwrites.
- **Backup verification job**: nightly `pg_restore --list` on most recent backup in scratch env; alert on failure.
- **Quarterly restore drill** (already in pre-launch C5).
- **R2 bucket object-lock** (write-once-read-many for 30 days minimum).
**Residual:** Low.
**Owner:** Argus + Mnemosyne + Hestia.

### AS-P2-15. Supply Chain on `MetaTrader5` Package (Rare Publisher)
**STRIDE:** T+I+E
**Attack path:** `MetaTrader5` PyPI package is published by a less-audited vendor account. Compromised release → bridge installs malicious version on next deploy → backdoor in bridge process → token + creds exfiltration.
**Mitigation:**
- **Pin to specific version + hash**: `MetaTrader5==5.0.45 --hash=sha256:...` in `requirements.txt`.
- **Mirror to internal index** (PyPI cache like devpi or Artifactory) — install from internal mirror only in prod build.
- **Renovate** flags version updates; manual review of release notes + PyPI changelog before bump.
- **Sigstore lookup** (when MetaTrader5 publishes there) — verify provenance.
- **Network egress allowlist on bridge VPS**: only MT5 broker + Sentry; no arbitrary outbound (would limit blast if backdoored).
- **Trivy on bridge image** in CI; manual review on critical CVEs for this package.
- **Backup plan**: forked vendored copy of MetaTrader5 wrapper if needed.
**Residual:** High — supply chain on closed-source vendor package is inherently hard.
**Owner:** Argus + Hestia + Kairos.

---

## 3. Updated Risk Register (Phase 2 additions)

| ID | Risk | Severity | Owner | Status | Due |
|---|---|---|---|---|---|
| R-P2-1 | mt5-bridge token leak via Windows VPS compromise | Critical | Argus + Hestia | Mitigation in `mt5-bridge-security.md` | Before first live user |
| R-P2-2 | Email provider compromise | High | Argus + Atlas | DPA + monitoring + SPF/DKIM/DMARC | Before first live user |
| R-P2-3 | Stripe webhook spoof / replay | High | Argus + Atlas | Signature + idempotency tested | Before first live user |
| R-P2-4 | Adversarial strategy push (insider) | High | Argus + Kairos | CODEOWNERS + cosign + canary | Before Phase 2 GA |
| R-P2-5 | Caddy misconfig exposes internal | High | Argus + Hestia | Path allowlist test in CI | Before first live user |
| R-P2-6 | TOCTOU on live gate | High | Argus + Kairos | Per-trade gate re-check | Before first live user |
| R-P2-7 | Strategy params RCE (eval-like) | High | Argus + Kairos | Lint + schema + CI grep | Before first live user |
| R-P2-8 | Refund-then-keep-using | Medium | Argus + Atlas | Webhooks + nightly reconcile | Before first live user |
| R-P2-9 | DSAR mass scraping | Medium | Argus + Atlas | Rate-limit + async + 2FA | Before first EU user |
| R-P2-10 | MetaTrader5 supply chain | High | Argus + Hestia | Hash pin + internal mirror + Trivy | Before first live user |
| R-P2-11 | DNS hijack | Medium | Argus + Zeus | Registrar 2FA + lock + CAA + CT monitor | Before first live user |
| R-P2-12 | Race on go-live double-spend | Low | Argus + Atlas | FOR UPDATE + idempotency token | Before first live user |
| R-P2-13 | Cron overlap / backup corruption | Low | Argus + Mnemosyne | flock + timestamped path + verify | Before first live user |

---

## 4. What Phase 1 Mocked That We Now Own

Phase 1 wisely deferred several integrations. We must acknowledge:

- **Stripe was a stub** — webhook code paths now must be production-grade. Idempotency table did not exist. Add migration + tests.
- **Email was a stub** — we never had to consider SPF/DKIM/DMARC, token leakage in mailbox, provider compromise. All new.
- **mt5-bridge was a stub** — actual MT5 dependency on Windows is a brand-new surface with all its hardening burden.
- **"Live mode" feature flag was a boolean** — now it is a 7-check gate, and TOCTOU matters.
- **Production secrets** are generated for the first time. They were dev-mode secrets in `dev.sh`. We must establish: where they come from, who has them, how they rotate.

If we did not catch one of these — we are pretending Phase 1 made it safe. It did not. Phase 1 made it possible to *develop* — Phase 2 makes it possible to *get hurt*.

---

## 5. Re-Run Cadence

- Re-run STRIDE before adding: copy-trading, mobile app, withdraw, social signup, broker beyond Exness.
- Quarterly full review.
- After every SEV-1 — incorporate lessons.
