# MT5 Bridge — Windows Setup Guide

> Step-by-step for installing the `mt5-bridge` service on a Windows machine
> so the Linux backend can place orders on Exness.

This guide is for whoever owns the Windows host — your personal PC or a
small Windows VPS (Vultr / Contabo / Hetzner / Azure all work). Budget
~30 min for the first install.

---

## Topology

```
                           Internet (ALWAYS via Tailscale or
                                    Cloudflare Tunnel)
                                     │
            ┌────────────────────────▼─────────────────────────┐
            │  Windows host (your PC or VPS)                   │
            │                                                  │
            │     ┌──────────────┐    ┌─────────────────┐      │
            │     │ MT5 Terminal │◄───┤  mt5-bridge     │      │
            │     │  (Exness)    │ IPC│  FastAPI :8500  │      │
            │     └──────────────┘    └────────▲────────┘      │
            │                                  │ Bearer        │
            └──────────────────────────────────┼───────────────┘
                                               │
                                  ┌────────────┴────────────┐
                                  │ Linux backend host       │
                                  │  trading-engine /live   │
                                  └─────────────────────────┘
```

The bridge is the **only** Windows-side piece. Everything else runs on Linux.

---

## Step 1 — Install Python 3.12

1. Open <https://www.python.org/downloads/release/python-3128/>.
2. Download **Windows installer (64-bit)**.
3. Run the installer.
   ```
   [✓] Add python.exe to PATH      <-- CRITICAL, tick this
   [✓] Install for all users        <-- recommended
   [Install Now]
   ```
4. Open a new PowerShell window and confirm:
   ```powershell
   python --version
   # expected: Python 3.12.8
   ```

If you already have an older Python 3, the install above coexists fine —
the launcher (`py -3.12`) picks the right one.

---

## Step 2 — Install MT5 terminal

1. Go to <https://www.exness.com/platform/metatrader5/>.
2. Download the MT5 installer.
3. Run it. After install, open MT5 and log into your real or demo account.

   ```
   File → Login to Trade Account
       Login:    [your account number]
       Password: [your trader password]
       Server:   [Exness-MT5Real8 or similar — copy from Exness portal]
   ```

4. **Enable algo trading** (the bridge will not work otherwise):

   ```
   Tools → Options → Expert Advisors
       [✓] Allow algorithmic trading
       [✓] Allow DLL imports
       [✓] Allow WebRequest for listed URL
           (no URLs needed — leave list empty)
   ```

   Click **OK** and confirm the "AutoTrading" button on the top toolbar
   is **green**.

5. Keep MT5 **running**. The bridge talks to the running terminal via
   shared memory — no terminal, no orders.

---

## Step 3 — Get the bridge code on the Windows host

Choose one:

**Option A: clone with git**

```powershell
cd C:\Apps
git clone https://github.com/<your-org>/forex-bot.git
cd .\forex-bot\mt5-bridge
```

**Option B: download zip**

```powershell
Invoke-WebRequest -Uri https://github.com/<your-org>/forex-bot/archive/refs/heads/main.zip -OutFile main.zip
Expand-Archive main.zip
cd .\main\forex-bot\mt5-bridge
```

---

## Step 4 — Install the service

In an **Administrator PowerShell**, from the `mt5-bridge` folder:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
.\install.ps1 -BackendIP 100.64.0.5     # use your backend's Tailscale IP
```

The script:

1. Creates `.venv` and installs the package.
2. Generates a fresh `BRIDGE_TOKEN` and **prints it once**:
   ```
   ----------------------------------------------------------
   SAVE THIS TOKEN — backend needs it as MT5_BRIDGE_TOKEN:
   l9XyqM8z+rA0H3vK... (≥ 48 chars)
   ----------------------------------------------------------
   ```
   Copy this string. You'll paste it into the backend's
   `MT5_BRIDGE_TOKEN` env var.
3. Downloads NSSM and registers a Windows service called `MT5Bridge`
   (auto-start on boot).
4. Opens TCP/8500 inbound, restricted to `-BackendIP`.

If you DON'T pass `-BackendIP`, it falls back to `LocalSubnet` — fine for
LAN-only setups but **never** expose port 8500 to the public internet.

---

## Step 5 — Verify

```powershell
# Health (no auth — works from localhost)
curl http://localhost:8500/healthz
```

Expected:

```json
{
  "status": "ok",
  "service": "mt5-bridge",
  "version": "0.1.0",
  "mt5_connected": false,
  "subscribers": 0
}
```

`mt5_connected: false` is expected — we haven't called `/connect` yet.

```powershell
# Connect to your Exness account
$token = "<paste BRIDGE_TOKEN from step 4>"
$body = @{
    server   = "Exness-MT5Real8"   # exact server name from Exness portal
    login    = 1234567
    password = "<trader password>"
} | ConvertTo-Json

curl -Method POST `
     -Headers @{ "Authorization"="Bearer $token"; "Content-Type"="application/json" } `
     -Body $body `
     http://localhost:8500/connect
```

Expected:

```json
{ "success": true, "account": { "balance": 100.0, "equity": 100.0, ... } }
```

If you get `502 mt5.initialize failed`, MT5 terminal is not running.
If you get `502 mt5.login failed`, double-check server name + login + password.

---

## Step 6 — Networking — pick ONE

### Recommended: Tailscale (free for personal use)

On the Windows host:

```powershell
winget install Tailscale.Tailscale
tailscale up
```

Note the Windows host's `100.x.x.x` address. On the **backend** Linux host:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

In the backend's `.env`:

```env
MT5_BRIDGE_URL=http://100.64.0.5:8500   # your Windows Tailscale IP
MT5_BRIDGE_TOKEN=<paste from step 4>
```

Re-run `install.ps1 -BackendIP 100.64.0.10` (the backend's Tailscale IP)
so the firewall whitelists that address.

### Alternative: Cloudflare Tunnel (if you have a domain)

```powershell
winget install Cloudflare.cloudflared
cloudflared tunnel login
cloudflared tunnel create mt5-bridge
cloudflared tunnel route dns mt5-bridge bridge.example.com

# Add config at C:\Users\<you>\.cloudflared\config.yml:
#   tunnel: mt5-bridge
#   credentials-file: C:\Users\<you>\.cloudflared\<id>.json
#   ingress:
#     - hostname: bridge.example.com
#       service: http://localhost:8500
#     - service: http_status:404

cloudflared service install
```

Backend `.env`:

```env
MT5_BRIDGE_URL=https://bridge.example.com
MT5_BRIDGE_TOKEN=<paste from step 4>
```

Add a **Cloudflare Access** policy in front of the hostname (free tier
allows 50 users) — gives you a second auth layer.

### NOT recommended: public port

```
ngrok / port-forward → ANY internet host can hit :8500
```

The Bearer token is your only defence. If you must, rotate the token
every 30 days and monitor `bridge.err.log` for 401s.

---

## Step 7 — Wire up the backend

On the Linux backend host (`/Users/.../forex-bot/`):

```bash
# Edit .env
MT5_BRIDGE_URL=http://100.64.0.5:8500
MT5_BRIDGE_TOKEN=<paste from step 4>
INTERNAL_API_SECRET=$(openssl rand -hex 32)   # also paste into Atlas backend
BACKEND_INTERNAL_URL=http://backend:8000

# Restart engine
docker compose restart trading-engine
```

From inside the trading-engine container:

```bash
curl -H "Authorization: Bearer $MT5_BRIDGE_TOKEN" $MT5_BRIDGE_URL/healthz
# Expected: { "mt5_connected": true, ... }
```

---

## Service management

```powershell
# Status
Get-Service MT5Bridge

# Tail logs
Get-Content .\logs\bridge.err.log -Tail 100 -Wait
Get-Content .\logs\bridge.out.log -Tail 100 -Wait

# Restart (e.g. after MT5 update)
Restart-Service MT5Bridge

# Stop temporarily
Stop-Service MT5Bridge

# Uninstall
.\tools\nssm.exe stop MT5Bridge
.\tools\nssm.exe remove MT5Bridge confirm
Remove-NetFirewallRule -DisplayName "MT5Bridge-In-8500"
```

---

## Updating

```powershell
cd C:\Apps\forex-bot
git pull
cd mt5-bridge
.\.venv\Scripts\python.exe -m pip install -e .
Restart-Service MT5Bridge
```

---

## Troubleshooting

| Symptom                                          | Fix                                                                                       |
| ------------------------------------------------ | ----------------------------------------------------------------------------------------- |
| Service won't start                              | `Get-Content .\logs\bridge.err.log -Tail 100` — usually `BRIDGE_TOKEN` missing/too short. |
| `curl /healthz` works but backend can't reach it | Firewall rule scoped to wrong IP. Check `Get-NetFirewallRule -DisplayName "MT5Bridge-*"`. |
| `/connect` returns 502 `initialize failed`       | MT5 terminal not running, or "Allow DLL imports" off.                                     |
| `/connect` returns 502 `login failed`            | Wrong server name. Copy it from Exness portal → Personal Area → MT5 → server.             |
| Orders place but no SL                           | The engine sent SL=0. Check strategy params; bridge requires SL by default.               |
| MT5 terminal randomly logs out                   | Exness sometimes does this. Re-login and call `/connect` again. We auto-reconnect.        |
| BRIDGE_TOKEN compromised                         | `[Convert]::ToBase64String((1..48 \| %{Get-Random -Max 256}))` → setx → restart. Update backend too. |

---

## Why all this complexity?

MetaTrader 5 is a Windows-only app. The official Python package
(`MetaTrader5`) talks to a **running terminal** via shared memory — so we
need a Windows process between Linux and Exness. The bridge keeps that
process small, auditable, and pinned to a single MT5 session.

The alternative — running the full backend on Windows — would force the
whole stack (Postgres, Redis, Next.js) onto a less-mature platform and
make ops harder. So we bite the bullet on one tiny Windows service.
