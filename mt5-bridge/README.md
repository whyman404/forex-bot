# MT5 Bridge

> Windows-side service that exposes [MetaTrader5](https://pypi.org/project/MetaTrader5/)
> over HTTP so the Linux/Mac backend (`trading-engine`) can place orders on Exness.

This is the **only** piece of the stack that has to run on Windows. Everything
else (Postgres, Redis, FastAPI backend, Next.js frontend) runs on Linux.

```
[trading-engine on Linux] --HTTPS+Bearer--> [mt5-bridge on Windows] --IPC--> [MT5 Terminal] --> [Exness]
```

---

## Prerequisites

1. **Windows 10 / 11** — your PC or a small VPS (Vultr / Contabo / Hetzner all work).
2. **Python 3.12.x** — install from <https://www.python.org/downloads/release/python-3128/>.
   - Tick "Add Python 3.12 to PATH" in the installer.
3. **MT5 terminal** — download Exness's MT5 build:
   <https://www.exness.com/platform/metatrader5/> and log in to your real or demo account once.
4. **Allow algorithmic trading** in MT5:
   - `Tools → Options → Expert Advisors`
   - Tick `Allow algorithmic trading`
   - Tick `Allow DLL imports` (required by the Python package)
5. (Recommended) **Tailscale** or **Cloudflare Tunnel** — see §Networking.

---

## Install

Clone or copy this folder onto the Windows machine. Then, from an
**Administrator PowerShell**:

```powershell
cd C:\path\to\mt5-bridge
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
.\install.ps1 -BackendIP 10.0.0.5      # IP your backend will call from
```

What it does:

1. Verifies Python 3.12 is on PATH.
2. Creates `.venv` and installs the bridge package (`pip install -e .`).
3. Generates a random `BRIDGE_TOKEN` (machine env), prints it once.
   **Save this token — you will paste it into the backend's `MT5_BRIDGE_TOKEN`.**
4. Downloads NSSM and registers a Windows service called `MT5Bridge` (auto-start on boot).
5. Opens TCP/8500 inbound, restricted to `-BackendIP` if given, else `LocalSubnet`.

Re-running `install.ps1` is idempotent.

### Minimal manual install (no service)

```cmd
setx BRIDGE_TOKEN "<paste a 48-byte base64 string>" /M
:: open a NEW cmd window so setx takes effect
install.bat
```

---

## Configure

All config is environment variables. Set with `setx <NAME> "<value>" /M` for
machine-wide persistence.

| Variable                  | Required | Default         | Notes                                          |
| ------------------------- | -------- | --------------- | ---------------------------------------------- |
| `BRIDGE_TOKEN`            | yes      | —               | ≥ 32 chars. The backend's `MT5_BRIDGE_TOKEN`.  |
| `BRIDGE_BIND`             | no       | `0.0.0.0:8500`  | host:port                                      |
| `MT5_PATH`                | no       | autodetect      | Full path to `terminal64.exe`                  |
| `BRIDGE_MAX_LOT`          | no       | `1.0`           | Hard cap on a single order's volume            |
| `BRIDGE_SYMBOL_ALLOWLIST` | no       | (any)           | CSV: `XAUUSD,BTCUSD,EURUSD`                    |
| `BRIDGE_REQUIRE_SL`       | no       | `true`          | Reject orders without SL                       |
| `BRIDGE_ALLOWED_ORIGINS`  | no       | (none)          | CSV of caller IPs (informational; firewall is authoritative) |

---

## Verify

After `install.ps1` finishes, in PowerShell:

```powershell
# 1. Health (no auth)
curl http://localhost:8500/healthz

# Expected:
# { "status":"ok", "mt5_connected":false, "subscribers":0, ... }
```

```powershell
# 2. Connect to your Exness account
$token = "<the token install.ps1 printed>"
$body = @{ server="Exness-MT5Real8"; login=1234567; password="..." } | ConvertTo-Json
curl -Method POST `
     -Headers @{ "Authorization"="Bearer $token"; "Content-Type"="application/json" } `
     -Body $body `
     http://localhost:8500/connect
```

```powershell
# 3. Read account info
curl -Headers @{ "Authorization"="Bearer $token" } http://localhost:8500/account
```

If `/connect` returns `502`, check `logs\bridge.err.log` and confirm:

- MT5 terminal is **already running and logged in** on this machine.
- Algorithmic trading is allowed.
- The login / password / server fields match what you use to log into MT5 manually.

---

## Networking — do NOT expose port 8500 publicly

Even with auth, putting `8500` on the open internet is asking for trouble.
Choose one:

### Option A — Tailscale (recommended for hobbyists)

```powershell
winget install Tailscale.Tailscale
tailscale up
```

The backend installs the Linux Tailscale client and gets a `100.x.x.x`
address. Then the firewall rule in `install.ps1` should use that address:

```powershell
.\install.ps1 -BackendIP 100.64.0.5
```

The backend's `.env` points at `MT5_BRIDGE_URL=http://100.64.0.1:8500`
(your Windows Tailscale IP). Tailscale handles auth + encryption; no
public ingress needed.

### Option B — Cloudflare Tunnel

```powershell
winget install Cloudflare.cloudflared
cloudflared tunnel login
cloudflared tunnel create mt5-bridge
cloudflared tunnel route dns mt5-bridge bridge.example.com
cloudflared tunnel run --url http://localhost:8500 mt5-bridge
```

Set `MT5_BRIDGE_URL=https://bridge.example.com` on the backend. Add a
Cloudflare Access policy in front for an extra layer.

### Option C — WireGuard

Spin up a WireGuard server next to your backend, install the WireGuard
client on Windows, and use the peer IP in `-BackendIP`.

### Option D — Public port (NOT RECOMMENDED)

If you absolutely must, force HTTPS via a reverse proxy (Caddy is the
simplest on Windows) and **rotate `BRIDGE_TOKEN` every 90 days**.

---

## Service management

```powershell
# Status / logs
Get-Service MT5Bridge
Get-Content .\logs\bridge.err.log -Tail 100 -Wait

# Restart after MT5 update
Restart-Service MT5Bridge

# Uninstall
.\tools\nssm.exe stop MT5Bridge
.\tools\nssm.exe remove MT5Bridge confirm
Remove-NetFirewallRule -DisplayName "MT5Bridge-In-8500" -ErrorAction SilentlyContinue
```

---

## Tests

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
```

The test suite mocks `MetaTrader5` so it runs on any platform — useful
for CI before promoting to a real Windows host.

---

## Troubleshooting

| Symptom                                                | Fix                                                                                  |
| ------------------------------------------------------ | ------------------------------------------------------------------------------------ |
| Service starts then stops within 5s                    | Check `logs\bridge.err.log` — usually `BRIDGE_TOKEN` missing or too short.           |
| `/connect` returns 502 "mt5.initialize failed"         | MT5 terminal is not running OR `Allow DLL imports` is off.                            |
| `/order` returns 400 "safety: SL is required"          | The engine sent an order with no SL. Add SL in the strategy params or set `BRIDGE_REQUIRE_SL=false` (NOT recommended). |
| Tick stream goes silent for > 60s                      | MT5 terminal lost broker connection. The bridge auto-reconnects on next call.        |
| `bridge.import_skipped` at boot                        | You're on Mac/Linux. Install on Windows. The import is intentionally graceful.       |

---

## Security model

- **Bearer token** with constant-time comparison (`hmac.compare_digest`).
- **No secrets in logs** — `BridgeConfig.redact()` masks the token; the
  connect endpoint does not log the password.
- **Firewall** — `install.ps1` restricts inbound to a specific IP.
- **Belt-and-braces safety** — `safety.py` validates every order even if
  the engine has its own risk manager. Defense in depth.
- **No public exposure** — see §Networking.

If you suspect token compromise:

```powershell
$new = [Convert]::ToBase64String((1..48 | %{ Get-Random -Max 256 }))
setx BRIDGE_TOKEN "$new" /M
Restart-Service MT5Bridge
# Then update MT5_BRIDGE_TOKEN on the backend and restart the trading-engine.
```
