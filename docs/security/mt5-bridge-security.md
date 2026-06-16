# mt5-bridge — Comprehensive Security

> The component placing real orders on real accounts. Everything else matters less if this is wrong.
> **Author:** Argus Hayato | **Date:** 2026-06-15
> **Scope:** `mt5-bridge/` package + Windows VPS hosting it.

---

## 0. Architecture Recap

```
backend (Linux VPS)  --[mTLS / Tailscale]-->  mt5-bridge (Windows VPS)  --[MT5 API]-->  Exness server
       ^                                            ^                                       ^
       |                                            |                                       |
   trading engine signal             bearer token + HMAC envelope                   broker fills order
```

The bridge is a small FastAPI app on Windows that imports the `MetaTrader5` Python package, holds (decrypted-just-in-time) the user's MT5 credentials, and places orders.

**Trust boundary** crossings to protect: Internet/internal → bridge → MT5 terminal → broker.

---

## 1. Bearer Token

### 1.1 Generation
- **Length:** 32 bytes from `secrets.token_urlsafe(32)` (Python).
- **Scope:** single bridge instance has one active token at a time. Multi-tenant (one user per bridge instance) optional dimension.
- **Format:** opaque random; we do NOT use JWT for the bridge token (KISS; revocation is easier on opaque).

### 1.2 Storage
- **On Windows VPS:**
  - Stored in `secret.json` with NTFS ACL: only `mt5-bridge-svc` user can read.
  - Better: DPAPI-protected file (`win32crypt.CryptProtectData`) tied to machine + user account.
- **On backend Linux VPS:**
  - Env var sourced from secrets manager (1Password / Doppler / Bitwarden / SOPS-encrypted file).
- **Never in:**
  - Git (gitleaks scan in CI).
  - CI logs (`add-mask` if surfaced).
  - Process command line args.
  - Sentry breadcrumbs.

### 1.3 Rotation Cadence
- **Quarterly** (every 90 days) regardless.
- **On-demand** triggers:
  - RDP login from unexpected geo / IP.
  - Bridge VPS restart (out-of-band — if Hestia rebuilds the host).
  - Suspected leak (token surfaced in any log).
  - Personnel change (anyone with read access leaves).
  - Any incident touching the bridge.

### 1.4 Rotation Procedure
1. Generate new token N+1 on isolated host.
2. Push N+1 to bridge `secret.json` (atomic write + reload signal).
3. Update backend env to N+1; rolling restart backend; verify trades flowing.
4. Wait one acceptance window (5 min); check no calls with old token N (alert).
5. Remove N from bridge (now N+1 only valid).
6. Audit log: rotation actor + timestamp + reason.

### 1.5 Constant-time Comparison
```python
# in bridge auth dependency
import hmac
def verify_token(provided: str) -> bool:
    expected = settings.BRIDGE_TOKEN
    return hmac.compare_digest(provided.encode(), expected.encode())
```
Never use `==` for token comparison — timing leak.

### 1.6 Token Never in Logs — derive audit ID
```python
import hashlib
def token_audit_id(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:16]
```
- Log only the `audit_id` (truncated SHA256 of token).
- Reverse lookup impossible without the original token; sufficient for correlation.
- Even on rotation, old audit_id values remain meaningful in archived logs.

### 1.7 Auth Endpoint Failure Behavior
- Return generic `401 {"detail":"unauthorized"}`. No body distinguishing "no token", "bad format", "wrong value".
- Rate-limit: 5 attempts per minute per source IP; lock source IP at 20/hr.
- Alert at 3 failed attempts within a minute → SEV-2 (possible token brute / leak).

---

## 2. Network Architecture (Pick One — Ranked)

### Option A: **Tailscale** (recommended)
- Both backend VPS and bridge VPS join the same Tailnet.
- Bridge listens on `tailscale0` interface only; no public IP routes to bridge port.
- Use Tailscale ACLs to allow only the backend node → bridge node on port 8200.
- 2FA on Tailscale admin.
- **Benefit:** zero attack surface from internet. Token leak alone insufficient (must also be inside tailnet).

### Option B: **Cloudflare Tunnel** (recommended)
- Bridge VPS runs `cloudflared` connecting outbound to Cloudflare.
- Cloudflare Access policy: only backend VPS public IP allowed + service token.
- **Benefit:** no public listener on bridge VPS. CF Access acts as extra auth layer.

### Option C: **Public IP + UFW allowlist** (acceptable)
- Bridge VPS firewall (Windows Firewall + provider firewall) allows port 8200 ONLY from backend VPS public IP.
- Bearer token + HMAC envelope as application auth.
- TLS terminated on bridge (self-signed cert + pinned on backend, or Let's Encrypt).
- **Risk:** if backend IP changes (auto-scaling, IP rotation), firewall stale. If attacker IP-spoofs (rare on TCP), still token-protected.

### Option D: **Public IP + token only** (NOT recommended)
- Bridge VPS has port 8200 public.
- Sole defense is bearer token.
- **Risk:** token leak = full pwn. No defense in depth.
- **Only acceptable as last resort** with all of: aggressive rate limit, token rotated weekly, every order alerted.

**Decision for Phase 2:** Tailscale (lowest cost, lowest config burden, defense in depth).

---

## 3. Symbol + Side Allowlist (Per User)

The bridge enforces what the backend would normally enforce. Defense in depth — even if backend compromised, the bridge limits damage.

### 3.1 Symbol allowlist
- Per user: `allowed_symbols = ['XAUUSD', 'EURUSD', 'BTCUSD']` (configured at broker connection time).
- Bridge rejects order: symbol not in user's allowlist → 400 + alert.
- Default-deny: empty allowlist = no trades.

### 3.2 Side validation
- Order body includes `symbol` AND `side` (BUY/SELL). Bridge **does not** accept "side: any" or wildcard.
- Per (user, symbol), optional `allow_buy`, `allow_sell` flags (e.g., user wants long-only XAUUSD).

### 3.3 Lot size cap
- Per user `max_lot_per_order = 0.10` (configurable).
- Per user `max_orders_per_minute = 5`.
- Bridge rejects exceedance + alert.

### 3.4 Stop-loss requirement
- For Phase 2 conservative posture: orders MUST include `sl` (stop-loss). Missing SL = reject.
- Exception per user via explicit config flag (founder approval).

---

## 4. Magic Number Namespace

MT5 "magic number" tags orders for grouping. Without discipline, two users' strategies could collide on the same magic.

### 4.1 Scheme
```python
def compute_magic(user_id: UUID, strategy_id: UUID) -> int:
    h = sha256(f"{user_id}:{strategy_id}".encode()).digest()
    # MT5 magic is 32-bit int; mask to positive 31 bits
    return int.from_bytes(h[:4], 'big') & 0x7FFFFFFF
```
- Deterministic from (user, strategy) → reproducible.
- Per-user, per-strategy unique with overwhelming probability (collision = birthday on 2^31).

### 4.2 Bridge enforcement
- Order request includes `expected_magic`; bridge computes it from request context (user + strategy) and verifies match.
- Cross-namespace order = reject + SEV-1 alert (likely impersonation).

### 4.3 Reconciliation
- Daily job: pull broker history → group by magic → cross-reference against `(user, strategy)` map.
- Orphan magic (no map entry) = SEV-1; could indicate insider or compromise.

---

## 5. MT5 Terminal Settings — "Allow algorithmic trading" + "Allow imports of DLL"

These are checkboxes inside MT5 terminal that the Python `MetaTrader5` package depends on.

| Setting | Risk if ON | Why we need it |
|---|---|---|
| "Allow algorithmic trading" | EAs / scripts can place orders without user interaction | Required for our bridge to function — accepted risk |
| "Allow DLL imports" | A loaded EA can load arbitrary DLL → RCE on terminal | We DO NOT install third-party EAs. Risk = if any EA were ever installed by mistake / malice. |
| "Allow WebRequest" to `*` | EA can call out to any URL | Set allowlist or leave OFF — bridge doesn't need it. |

### Hardening
- "Allow algorithmic trading": **ON** — required.
- "Allow DLL imports": **OFF** unless a vetted EA needs it. We don't install EAs — leave OFF.
- "Allow WebRequest": **OFF**.
- "Allow live trading": **ON** — required.
- `Tools → Options → Server`: pin Exness server name; disable auto-discovery.
- `Tools → Options → Experts`: max bars in chart = lowest reasonable (perf hardening).
- Disable "send crash report to MetaQuotes" if possible (privacy — broker credentials should never go anywhere).

### Account-level
- MT5 broker-side account: **read+trade only**, **NO withdraw**. (Exness allows API key without withdraw permission — use that.)
- 2FA at broker if available.

---

## 6. Windows VPS Hardening Checklist

### 6.1 OS baseline
- [ ] Windows Server 2022 (or Windows 11 Pro), fully patched, auto-update on patch Tuesday cadence.
- [ ] Local admin account renamed (not "Administrator"); strong password.
- [ ] Disable Guest, Helper, and any unused built-in accounts.
- [ ] Create dedicated `mt5-bridge-svc` user (limited rights) — service runs as this user, NOT as admin.
- [ ] BitLocker FDE enabled with TPM + recovery key escrowed in password manager.
- [ ] Windows Defender + cloud-based protection on; tamper protection on.
- [ ] SmartScreen on.
- [ ] No browsers used on this host except for emergency. Edge/Chrome installed only if needed; never sign in.

### 6.2 Remote access
- [ ] **NO public RDP.** RDP only via Tailscale or VPN.
- [ ] If RDP must be enabled internally: NLA required, account lockout 5/15min, fail2ban-equivalent (e.g., RdpGuard) optional.
- [ ] SSH (if installed) only via Tailscale.
- [ ] 2FA on the user account that has RDP rights (Duo, Microsoft Authenticator for Windows).

### 6.3 Firewall
- [ ] Windows Firewall: deny inbound by default.
- [ ] Allow inbound on bridge port 8200 only from backend VPS or Tailnet.
- [ ] Allow MT5 outbound to broker server only (or unrestricted outbound if MT5 protocol needs flexibility — broker IPs change; can use FQDN filtering with WFP).
- [ ] Provider-side firewall echoing same rules.

### 6.4 Logging & monitoring
- [ ] Windows Event Forwarding to a central log VPS (or to Loki via Promtail).
- [ ] Security logs: logon success/fail, account lockout, privileged use.
- [ ] Bridge app logs → JSON → forward via Promtail → Loki.
- [ ] Sysmon installed with sensible config (e.g., SwiftOnSecurity baseline).
- [ ] Alert: any RDP login → Slack with source IP + user.
- [ ] Alert: any new process started under `mt5-bridge-svc` other than the bridge + MT5 terminal.

### 6.5 Application install
- [ ] MT5 terminal installed from official Exness link (verified hash if Exness publishes).
- [ ] Python 3.12 official installer; signature verified.
- [ ] No other software installed.
- [ ] Bridge code deployed via signed artifact (cosign-signed zip from CI); hash verified before unpack.

### 6.6 Backup / DR
- [ ] No user data on this host (all in Postgres on Linux VPS).
- [ ] Image backup weekly.
- [ ] DR plan: rebuild from scratch playbook in `/runbooks/mt5-bridge-rebuild.md`; tested.

### 6.7 Time sync
- [ ] NTP sync (windows time service) → broker depends on accurate time for order signing.

### 6.8 Audit cadence
- [ ] Monthly Argus + Hestia review: patch status, log review, unusual processes.

---

## 7. Bridge API Surface (Contract)

| Endpoint | Method | Purpose | Auth |
|---|---|---|---|
| `/healthz` | GET | Liveness | none (allowed without token; no sensitive info) |
| `/readyz` | GET | Readiness incl. MT5 connection status | token |
| `/account/{login}/info` | GET | Balance, equity, positions count | token + HMAC |
| `/account/{login}/positions` | GET | Open positions list | token + HMAC |
| `/account/{login}/orders` | POST | Place order | token + HMAC |
| `/account/{login}/orders/{ticket}` | DELETE | Close / cancel | token + HMAC |
| `/account/{login}/orders/{ticket}/modify` | PATCH | Modify SL/TP | token + HMAC |
| `/admin/reload` | POST | Hot-reload config | token + admin scope (separate) |

**HMAC envelope** on every request body:
```
X-Bridge-Signature: hmac_sha256(INTERNAL_API_SECRET, timestamp || nonce || body)
X-Bridge-Timestamp: <unix>
X-Bridge-Nonce: <uuid7>
```
Reject if:
- timestamp skew > 60s
- nonce seen in last 5 min (Redis dedup)
- signature mismatch

---

## 8. Tests Required Before First Live User

- [ ] Token rotation: in staging, rotate while orders in flight; verify no order dropped.
- [ ] Constant-time compare unit test.
- [ ] Allowlist enforcement: send `XYZUSD` order for user with `[XAUUSD]` allowlist → expect 400.
- [ ] Side validation: omitted `side` → 400.
- [ ] Magic mismatch: pass wrong `expected_magic` → 400 + alert fires.
- [ ] Lot cap: exceed → 400.
- [ ] Missing SL: → 400.
- [ ] HMAC nonce replay: same nonce twice → second rejected.
- [ ] Token-in-log scan: full e2e in staging → `grep -i $TOKEN staging-loki.log` → 0 hits.
- [ ] Network: with Tailscale down, public access to bridge port = unreachable.
- [ ] Disconnect MT5 terminal mid-trade → bridge returns 503, signal queued or alerted.
- [ ] Kill switch: backend invokes `/admin/halt` → bridge refuses all subsequent orders until re-armed.

---

## 9. Failure Modes & Their Detection

| Failure | Detection | Response |
|---|---|---|
| Bridge unreachable | Backend health probe → alert in 30s | Pause new live signals; surface user banner |
| MT5 terminal disconnected from broker | MT5 API returns connection error; bridge surfaces | Pause that user's strategies; alert |
| Bridge token rotation failure | Backend calls fail with 401 | Roll back; alert |
| Order rejected by broker (margin, market closed) | Broker error code | Surface to user; do not retry blindly |
| Bridge OOM / crash | Watchdog restart; alert | Service restarts; SEV-2 |
| Time skew on Windows VPS | HMAC timestamp skew rejections | Re-sync NTP; alert |

---

## 10. Sign-off

- [ ] Tailscale or Cloudflare Tunnel in front of bridge.
- [ ] Token rotation runbook tested in staging.
- [ ] Token never in log (grep verified).
- [ ] Allowlist + side + lot + SL enforcement tested.
- [ ] Magic namespace deployed + reconciliation job running.
- [ ] Windows VPS hardening checklist complete.
- [ ] HMAC envelope tested with replay rejected.

Argus Hayato: ____________ Date: ____________
Hestia: __________________ Date: ____________
