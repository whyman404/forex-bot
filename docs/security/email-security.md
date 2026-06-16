# Email Security

> Email is an attack vector and an authentication channel. Treat both axes seriously.
> **Author:** Argus Hayato | **Date:** 2026-06-15
> **Scope:** outbound transactional email (verify, reset, billing, alerts).
> **Provider candidates:** Resend, Postmark, Amazon SES (one is chosen; this doc applies to all).

---

## 1. Inbound — We Don't Accept Email

We do **not** parse inbound email programmatically (no mailbot, no support inbox-to-ticket bridge in Phase 2). Inbound is human-only via a real mailbox (Google Workspace / Fastmail / similar) with normal user 2FA.

**Therefore inbound risk is the standard "support@ inbox" hygiene** — not a programmatic surface. Not in this doc's scope.

---

## 2. Outbound — Domain Authentication

The single biggest user-facing risk is **someone else sending mail as us**, leading to phishing of our users. SPF, DKIM, DMARC are the controls.

### 2.1 SPF
```dns
; @ <our-domain> (root)
TXT  v=spf1 include:_spf.resend.com include:_spf.google.com -all
```
- `-all` (hard fail) — receivers should reject if source IP not in includes.
- Only include the providers we actually send through. Periodically audit.
- Watch the **10-DNS-lookup limit** — fewer includes is safer.

### 2.2 DKIM
- Provider gives us a key pair; we publish public key in DNS as `<selector>._domainkey.<our-domain>`.
- Selector naming: `resend._domainkey.<our-domain>` or vendor default.
- Rotate selectors annually (publish new, dual-publish for 1 week, retire old).
- Key size: 2048-bit minimum.

### 2.3 DMARC
Phased rollout:

| Phase | Policy | Duration |
|---|---|---|
| Bootstrap (Phase 2 launch) | `v=DMARC1; p=none; rua=mailto:dmarc-rua@<our-domain>; ruf=mailto:dmarc-ruf@<our-domain>; fo=1; pct=100` | 2 weeks (monitor reports for legit traffic we forgot to authenticate) |
| Quarantine | `p=quarantine; pct=25` then `pct=100` | 2 weeks each |
| Reject (target) | `p=reject; sp=reject; adkim=s; aspf=s` | steady state |

- `rua` reports aggregated to a mailbox we read (free option: `dmarcian.com`, `valimail.com`, `parsedmarc` self-hosted).
- Aim for **p=reject** before first live customer outside our org.

### 2.4 BIMI (Brand Indicators) — Phase 3
Once DMARC at `p=reject`, publish BIMI for in-inbox brand logo. Requires VMC certificate (paid). Optional.

### 2.5 MTA-STS + TLS-RPT (recommended)
```dns
TXT _mta-sts.<our-domain>  v=STSv1; id=20260615
TXT _smtp._tls.<our-domain> v=TLSRPTv1; rua=mailto:tls-rpt@<our-domain>
```
Publishes `https://mta-sts.<our-domain>/.well-known/mta-sts.txt` with `mode: enforce`. Forces TLS on inbound mail.

---

## 3. Token Hygiene — Verify, Reset, Magic Link

### 3.1 Common rules
- **Generation:** `secrets.token_urlsafe(32)` → 32 random bytes, URL-safe base64.
- **Storage:** SHA-256 hash in DB; **never** plaintext.
- **Lookup:** by hash; never trial decryption.
- **Single-use:** invalidate on first use AND invalidate sibling tokens on success.
- **TTL:**
  | Token type | TTL | Why |
  |---|---|---|
  | Email verify (signup) | 1 hour | User just signed up; longer for convenience |
  | Password reset | 15 minutes | High-value; tight window |
  | Magic link (passwordless) | 10 minutes | Very high-value if we add this |
  | Email change confirmation | 30 minutes | Sensitive op |

- **Bind to email**: token rows store `target_email`; flow rejects if user mid-flow changes email.
- **Bind to IP optionally**: log the requesting IP; show user on reset page (UX honesty + soft signal if attacker uses different IP).

### 3.2 Reset request endpoint — anti-enumeration
- **Always** return generic message: `"If an account exists for that email, a reset link has been sent."`
- Same response on success and on "email not found".
- Same response time (use background job; don't block on DB lookup time).
- Rate-limit: 3 per hour per email + 5 per hour per IP.

### 3.3 Reset confirmation — preserve 2FA
If user had 2FA on, the reset flow must **also** require a current 2FA code (or recovery code).
Bypassing 2FA via password reset alone defeats the security model.

### 3.4 Email change
- Send confirmation token to **NEW** email; old email gets notification "your email is being changed to ...@..."
- Both must be acknowledged within TTL or change rolls back.

### 3.5 No tokens in URL fragments
Tokens in URL query string are visible to:
- Browser history (shared device).
- Referrer header sent to third-party trackers loaded on the landing page.
- Proxies/load balancers logs (if we log URLs).

**Mitigations:**
- Reset landing page: `<meta name="referrer" content="no-referrer">` + `Referrer-Policy: no-referrer` header.
- No third-party scripts (analytics, fonts CDN) on reset / verify landing pages.
- `Cache-Control: no-store` on the landing pages.
- After redeeming token: redirect to clean URL without token in query string.

---

## 4. Provider Verification

Before sending any production email:

- [ ] **Domain verified** in provider dashboard (SPF + DKIM published, provider confirms).
- [ ] **Bounce + complaint** webhook configured → ingested → emails to high-bounce destinations stop.
- [ ] **Suppression list** managed (auto-add on hard bounce, complaint).
- [ ] **Sender reputation**: warm-up by sending low volume first week if a brand-new domain (most providers handle this automatically).
- [ ] **Logging**: provider stores send events for 30+ days (audit).
- [ ] **Restrict to transactional**; no marketing without separate consent track (CAN-SPAM, PDPA, GDPR).

---

## 5. Provider Compromise Threat (AS-P2-2 from threat-model-phase2)

If our email provider is compromised, attacker can:
- Send mail as us → phish all users.
- Read API logs → see what we sent → some reset links may be replayable (depending on TTL window).

**Mitigations:**
- **API token scope**: send only (no list-management, no domain-modify, no historical-read if avoidable).
- **API token rotation**: quarterly + on incident; alert on any token use from unexpected source IP.
- **Per-call IP allowlist** at provider level (limit which IPs can use the token).
- **In-app notifications** in addition to email for sensitive events (so user has a second source of truth).
- **Dual-source for password reset**: Phase 3 — allow reset only after email + SMS or email + 2FA — for live-mode users.

---

## 6. Sender Discipline

### 6.1 Sender addresses
- `no-reply@<our-domain>` — automated transactional (verify, reset, billing).
- `support@<our-domain>` — human-monitored (does not auto-respond).
- `security@<our-domain>` — vuln disclosure; published in `/security` + RFC9116 `security.txt`.

### 6.2 Subject lines
Avoid PII / hot keywords:
- BAD: `"Reset password for jane@example.com"`
- GOOD: `"Action required on your account"`

Avoid spammy language; passes spam filters easier.

### 6.3 Body
- Clear sender identity in body (helps users distinguish phishing).
- Always include the requesting IP / UA when sensitive op was triggered.
- Always say: "If you didn't request this, contact security@<our-domain>".
- Plain-text version included alongside HTML.
- Link target plain in body so URL is visible in plaintext fallback.

### 6.4 Link safety
- Use canonical domain only (`<our-domain>`). No URL shorteners (Bitly etc.) — looks phishy + makes destination opaque.
- Optional: redirect through `https://l.<our-domain>/...` with allowlist of inner destinations.

---

## 7. CI / Test Hooks

- [ ] Test: signup → verify email → uses token → 200; token re-use → 410 Gone.
- [ ] Test: reset request for unknown email → same response shape + similar timing as known email.
- [ ] Test: reset with 2FA enabled → requires 2FA → bypass attempt → 403.
- [ ] Test: token expired → 410 Gone with non-disclosing message.
- [ ] Test: provider webhook for bounce → marks email as undeliverable → blocks future sends.
- [ ] Test: email body doesn't include `<script>` (DOM-XSS not relevant in email but template injection is).
- [ ] CI: external test (`mxtoolbox` or `mail-tester.com` integration) before each major release — SPF/DKIM/DMARC pass.

---

## 8. Sign-off

- [ ] SPF, DKIM, DMARC published.
- [ ] DMARC at `p=reject` (or scheduled transition).
- [ ] Domain verified at provider.
- [ ] Provider API token restricted scope + IP allowlist where possible.
- [ ] Token TTL + single-use enforced in code (tested).
- [ ] Anti-enumeration on reset request.
- [ ] Reset preserves 2FA.
- [ ] No tokens in browser history of landing pages (Referrer-Policy + no third-party scripts).

Argus Hayato: ____________ Date: ____________
Atlas: ___________________ Date: ____________
