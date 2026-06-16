# Cloudflare Setup — Forex Bot Production

> Owner: Hestia Kaoru
> Last updated: 2026-06-15
> Audience: Operator setting up `forexbot.example.com` in Cloudflare for the
> first time, or rotating WAF rules.
>
> Reference paths (absolute):
> - Caddyfile: `/Users/shinzo/Desktop/whyman404/projects/forex-bot/infra/caddy/Caddyfile`
> - Compose: `/Users/shinzo/Desktop/whyman404/projects/forex-bot/infra/docker-compose.prod.yml`

---

## Why Cloudflare in front?

1. **DDoS** at the edge — protect the $15 VPS from L3/L4 floods we can't filter.
2. **WAF managed rules** — Cloudflare's OWASP and security ruleset blocks
   common scanners before they reach our app.
3. **Bot Fight Mode** — blocks known scrapers.
4. **Caching** for `_next/static/*` static — saves origin egress (Hetzner has
   a soft cap).
5. **TLS termination + re-encryption** to origin (Full Strict).
6. **Zero-trust Cloudflare Tunnel** for the MT5 bridge (recommended over a
   public port on the Windows VPS).

---

## 1. DNS Records

Account: Zeus owns `whyman404@gmail.com` (see `docs/security/secrets-management.md`).

| Type  | Name              | Target                  | Proxy   | TTL  | Notes |
|-------|-------------------|-------------------------|---------|------|-------|
| A     | `@` (apex)        | `<linux-vps-ip>`        | Yes     | Auto | Redirects to forexbot.example.com via page rule |
| A     | `forexbot`        | `<linux-vps-ip>`        | Yes     | Auto | Frontend (Next.js) |
| A     | `api.forexbot`    | `<linux-vps-ip>`        | Yes     | Auto | Backend (FastAPI) |
| A     | `grafana.forexbot`| `<linux-vps-ip>`        | Yes     | Auto | Admin only — IP allowlist + Access |
| CNAME | `status`          | `stats.uptimerobot.com` | DNS only | Auto | Public status page |
| TXT   | `_dmarc`          | `v=DMARC1; p=quarantine; rua=mailto:dmarc@forexbot.example.com` | n/a | 3600 | Email auth |
| TXT   | `@`               | `v=spf1 include:_spf.google.com -all` | n/a | 3600 | SPF |
| MX    | `@`               | Google Workspace / configured provider | n/a | 3600 | If we send transactional email from gmail / SES |

**Important:** Windows VPS (MT5 bridge) has **no public DNS record**.
It is accessed only via Cloudflare Tunnel or WireGuard (see section 6 below).

---

## 2. SSL/TLS

- **Mode:** Full (Strict). Caddy holds a real Let's Encrypt cert, Cloudflare
  re-encrypts. This is the only safe production mode — `Flexible` lets MITM
  attackers see plaintext between CF and origin.
- **Edge cert:** Universal (free) is fine for MVP. Upgrade to Advanced when
  >100 paying users for SNI improvements.
- **Always Use HTTPS:** On.
- **Automatic HTTPS Rewrites:** On.
- **Min TLS Version:** 1.2 (TLS 1.0/1.1 dead).
- **Opportunistic Encryption + 0-RTT:** On.
- **HSTS at CF edge:** Off — Caddy emits HSTS already (avoid double headers).

---

## 3. Cache Rules

Site → Caching → Cache Rules. Order matters.

### Rule 1 — Bypass cache for API
- **If incoming requests match:**
  - Hostname equals `api.forexbot.example.com`, OR
  - URI Path starts with `/api/`, OR
  - URI Path starts with `/stripe/`
- **Then:**
  - Cache eligibility: Bypass cache
  - Browser TTL: Respect origin

### Rule 2 — Bypass cache for auth pages
- **If:** URI Path starts with `/login`, `/signup`, `/auth/`, `/account`, `/dashboard`
- **Then:** Bypass cache

### Rule 3 — Cache static aggressively
- **If:** URI Path matches `/_next/static/*` or matches `/static/*` or matches `*.{ico,png,jpg,webp,svg,woff2}`
- **Then:**
  - Cache eligibility: Eligible for cache
  - Edge TTL: 1 year
  - Browser TTL: 1 year
  - Cache by device type: Off

### Rule 4 — Cache HTML modestly (SSR)
- **If:** Hostname equals `forexbot.example.com` AND URI Path does not match `/api/*`
- **Then:**
  - Edge TTL: 60s (Next.js can revalidate)
  - Browser TTL: Respect origin

---

## 4. WAF Rules

Site → Security → WAF.

### Managed Rules
- **Cloudflare Managed Ruleset:** On (paranoia: Medium, action: Block for severity High and Critical, Log for Medium).
- **OWASP Core Ruleset:** On (paranoia 1, score threshold 25 → Block).
- **Cloudflare Free Managed Ruleset:** On.
- **Sensitive Data Detection:** On (alerts only — we don't want false-positives blocking real users).

### Custom Rules

#### Rule 1 — Block known bad bots
- **Expression:** `(cf.client.bot) and not (cf.verified_bot)`
- **Action:** Block

#### Rule 2 — Aggressive rate limit on /auth/*
- **Expression:** `(http.request.uri.path contains "/api/v1/auth/") or (http.request.uri.path contains "/api/v1/login") or (http.request.uri.path contains "/api/v1/signup")`
- **Action:** Rate limit
- **Threshold:** 10 requests per IP per minute
- **Mitigation timeout:** 10 minutes
- **Mitigation action:** Block

#### Rule 3 — Geo restriction (optional, Phase 3)
- **Expression:** `(ip.geoip.country in {"KP" "IR" "SY"})`
- **Action:** Block
- (Conservative — only block fully sanctioned countries. Don't block emerging markets we want to serve.)

#### Rule 4 — Block requests with no User-Agent
- **Expression:** `(http.user_agent eq "")`
- **Action:** Managed Challenge

#### Rule 5 — Allow Stripe webhooks
- **Expression:** `(http.request.uri.path contains "/stripe/webhook") and (ip.src in {3.18.12.63 3.130.192.231 13.235.14.237 13.235.122.149 18.211.135.69 35.154.171.200 52.15.183.38 54.88.130.119 54.88.130.237 54.187.174.169 54.187.205.235 54.187.216.72})`
- **Action:** Skip (bypass other WAF rules)
- **Source:** [Stripe webhook IP list](https://stripe.com/docs/ips) — verify and update quarterly.

#### Rule 6 — Bot Fight Mode
- Site → Security → Bots → Bot Fight Mode: On.
- This blocks known bad-bot ASNs cheaply.

### Page Rules (legacy — prefer Cache Rules above)
- Decommission Page Rules once Cache Rules are stable (Cloudflare deprecating).

---

## 5. Network Settings

Site → Network.

- **HTTP/2:** On
- **HTTP/3 (with QUIC):** On
- **0-RTT Connection Resumption:** On
- **gRPC:** Off (we don't use it)
- **WebSockets:** On (NextAuth + some live updates)
- **Onion Routing:** Off (paid Tor users — not our market yet)
- **IP Geolocation:** On (used by audit log)
- **Maximum Upload Size:** 100 MB (CSV upload feature)

---

## 6. Cloudflare Tunnel — MT5 Bridge (Recommended)

The Windows VPS runs the MT5 bridge. Instead of opening port 9100 to the
internet (which would require firewall rules + IP allowlist), we run a
Cloudflare Tunnel. This gives us:

- No public port on Windows
- mTLS-equivalent identity (cloudflared auth)
- Zero-trust Access policy (only `backend@forex-bot.app` can call)

### Steps (run on Windows VPS as admin)

1. Install cloudflared: `winget install --id Cloudflare.cloudflared`
2. `cloudflared login` → opens browser → choose `forexbot.example.com` zone.
3. `cloudflared tunnel create forex-mt5-bridge` → returns tunnel UUID, writes
   `C:\Users\<user>\.cloudflared\<UUID>.json`.
4. Create `C:\cloudflared\config.yml`:
   ```yaml
   tunnel: <UUID>
   credentials-file: C:\Users\<user>\.cloudflared\<UUID>.json
   ingress:
     - hostname: mt5-bridge.internal.forexbot.example.com
       service: http://localhost:9100
       originRequest:
         noTLSVerify: true
         connectTimeout: 10s
     - service: http_status:404
   ```
5. Route DNS: `cloudflared tunnel route dns forex-mt5-bridge mt5-bridge.internal.forexbot.example.com`
6. Install as Windows service: `cloudflared --config C:\cloudflared\config.yml service install`
7. Start: `net start cloudflared`.

### Cloudflare Access policy (Zero Trust → Access → Applications)

- **Application:** Self-hosted
- **Application domain:** `mt5-bridge.internal.forexbot.example.com`
- **Session duration:** 24h
- **Policy 1:** Service token only — name `backend-mt5-token`, action Allow.
- **Policy 2:** Block all other identities.

The backend then calls:
```
GET https://mt5-bridge.internal.forexbot.example.com/healthz
Headers:
  CF-Access-Client-Id:     <id>
  CF-Access-Client-Secret: <secret>
```

Store these in `.env.prod` as `MT5_BRIDGE_CF_ACCESS_ID` and
`MT5_BRIDGE_CF_ACCESS_SECRET`.

---

## 7. Verification checklist

After setup:

- [ ] `dig forexbot.example.com` returns Cloudflare IPs (104.x / 172.x).
- [ ] `curl -I https://forexbot.example.com/` → HTTP/2, server header empty, HSTS present.
- [ ] `curl -I https://api.forexbot.example.com/healthz` → 200, `cf-cache-status: BYPASS`.
- [ ] `curl https://forexbot.example.com/_next/static/<file>` → `cf-cache-status: HIT` after second request.
- [ ] Open `forexbot.example.com` in browser, DevTools → Security → Cert chain shows Caddy LE cert.
- [ ] Authenticated request from non-allowlisted IP to `grafana.forexbot.example.com` → 403.
- [ ] Run `cloudflared tunnel info forex-mt5-bridge` from Windows → "Connections: 4 active connections."
- [ ] Backend `curl` to MT5 bridge via tunnel returns 200.

---

## 8. Rotation cadence

| Item | Cadence | Owner | Runbook |
|---|---|---|---|
| Cloudflare API token | 90 days | Hestia | `infra/scripts/rotate-secrets.sh` |
| CF Access service token | 90 days | Hestia | manual in Zero Trust dashboard |
| WAF rule review | 30 days | Argus + Hestia | check WAF events for FP rate |
| Stripe IP allowlist | 90 days | Hestia | refresh from https://stripe.com/docs/ips |
| Cloudflare Tunnel cert | auto (cloudflared rolls) | none | nothing |
