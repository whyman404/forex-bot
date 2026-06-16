# Windows MT5 VPS — Provisioning Runbook

> Owner: Hestia Kaoru
> Last updated: 2026-06-15
> Audience: Operator setting up the Windows VPS that hosts the MT5 terminal
> pool + the `mt5-bridge` FastAPI service.
> Estimated time: 90 minutes first-time.

---

## Why Windows?

MT5 terminal (MetaTrader 5) is Windows-only. We can't ship MT5 in a Linux
container. The choices were:

- **A.** Windows VPS dedicated to MT5 (recommended — this doc).
- **B.** Wine on Linux — fragile, breaks on every MT5 update.
- **C.** A managed broker REST API — only available for some brokers, and not
  for Exness (our primary).

We chose A. The Linux VPS reaches the Windows VPS over Cloudflare Tunnel
(zero-trust, no public port).

---

## Recommended provider + size

| Provider | Plan | vCPU | RAM | Disk | Region | Cost |
|---|---|---|---|---|---|---|
| **Contabo** | VPS M Windows | 4 | 8GB | 50GB SSD | Düsseldorf (EU) | ~$20/mo |
| Vultr | High-Frequency Win | 2 | 4GB | 64GB NVMe | Frankfurt | ~$24/mo |
| Hetzner | (No Windows direct — needs BYOL) | — | — | — | — | — |

**Pick Contabo for MVP.** It's cheap, EU-located (low ping to Exness servers),
and gives you 4 vCPU which is enough for ~15-20 MT5 terminals concurrently.

**Region:** Match the broker. Exness is Cyprus/EU → Düsseldorf or
Frankfurt give <20ms RTT to broker, <10ms to Linux VPS in Falkenstein.

---

## Step 1 — Provision

1. Sign up at https://contabo.com → buy VPS M Windows (€8.49/mo or similar).
2. Choose:
   - OS: **Windows Server 2022 Standard**
   - Region: Düsseldorf
   - Add-ons: none (no extra IPv4 needed)
3. Wait ~10 min for provisioning email with RDP credentials.

---

## Step 2 — First RDP login

1. RDP from your laptop:
   - macOS: Microsoft Remote Desktop
   - Linux: `xfreerdp /u:Administrator /v:<ip> /p:<password>`
2. Change Administrator password immediately to something stored in 1Password.
3. Install latest Windows updates (Settings → Windows Update → check). Reboot.

---

## Step 3 — Create non-admin user for the bridge

PowerShell as Administrator:

```powershell
$pass = Read-Host -AsSecureString "Enter password for mt5runner"
New-LocalUser -Name "mt5runner" -Password $pass -Description "MT5 bridge runner" -PasswordNeverExpires
Add-LocalGroupMember -Group "Users" -Member "mt5runner"
```

The bridge service runs as `mt5runner`, NOT Administrator.

---

## Step 4 — Install Python 3.12

```powershell
winget install --id Python.Python.3.12 --silent --accept-source-agreements --accept-package-agreements
# verify
python --version
pip --version
```

If `winget` not available (older Server 2019), download installer from
https://www.python.org/downloads/windows/ → check "Add to PATH" and
"Install for all users".

---

## Step 5 — Install MetaTrader 5

1. Download MT5 from Exness: https://www.exness.com/platforms/mt5/
   (use the broker your users connect to — Exness MT5 is broker-specific).
2. Install with defaults. Run once to verify launches and connects to broker.
3. **Do NOT log in with your personal account here** — terminal pool will
   log in per-user later via the bridge.
4. Disable auto-updates: MT5 → Tools → Options → Server → uncheck "Allow live
   updates" (we test updates in staging first).

---

## Step 6 — Install AutoHotkey for keep-alive

MT5 terminals can show modal dialogs (e.g., "Reconnect", "Update available").
AutoHotkey dismisses them automatically.

```powershell
winget install --id AutoHotkey.AutoHotkey
```

Save to `C:\mt5-bridge\keepalive.ahk`:

```ahk
#Persistent
SetTitleMatchMode, 2

Loop {
    Sleep, 5000

    ; Dismiss "Reconnect" prompts
    IfWinExist, ahk_class #32770 ; standard Windows dialog
    {
        WinActivate
        ControlClick, Button2, A, , , , NA  ; Cancel/No
    }

    ; Dismiss "Update available"
    IfWinExist, Update available
    {
        ControlClick, Button1, A, , , , NA  ; Later
    }
}
```

Add to startup folder: `shell:startup` → drop a shortcut to `keepalive.ahk`.

---

## Step 7 — Cloudflare Tunnel (recommended over public port)

Skip if you prefer WireGuard (see deployment-architecture.md). Cloudflare
Tunnel is easier — zero firewall config, no public IP exposed.

### Install cloudflared

```powershell
winget install --id Cloudflare.cloudflared
```

### Authenticate

```powershell
cloudflared login
```

→ Opens browser → choose your `forexbot.example.com` zone → write cert to
`%USERPROFILE%\.cloudflared\cert.pem`.

### Create tunnel

```powershell
cloudflared tunnel create forex-mt5-bridge
# returns: Tunnel UUID: 1a2b3c4d-5e6f-...
```

Note the UUID for the next step.

### Configure

Create `C:\cloudflared\config.yml`:

```yaml
tunnel: <UUID-from-previous-step>
credentials-file: C:\Users\Administrator\.cloudflared\<UUID>.json
ingress:
  - hostname: mt5-bridge.internal.forexbot.example.com
    service: http://localhost:9100
    originRequest:
      connectTimeout: 10s
      keepAliveConnections: 4
      noTLSVerify: true
  - service: http_status:404
```

### Route DNS

```powershell
cloudflared tunnel route dns forex-mt5-bridge mt5-bridge.internal.forexbot.example.com
```

### Install as Windows service

```powershell
cloudflared --config C:\cloudflared\config.yml service install
net start cloudflared
sc.exe failure cloudflared reset= 0 actions= restart/5000/restart/5000/restart/10000
```

### Verify

```powershell
cloudflared tunnel info forex-mt5-bridge
# Should show "4 active connections" (one per CF edge region)
```

### Cloudflare Access policy

In CF dashboard → Zero Trust → Access → Applications → Add:

- **Type:** Self-hosted
- **Application domain:** `mt5-bridge.internal.forexbot.example.com`
- **Session duration:** 24h
- **Policy:** Service token only — name `backend-mt5-token`, action Allow.

Store the `CF-Access-Client-Id` and `CF-Access-Client-Secret` in 1Password,
and inject them into the backend `.env.prod` as
`MT5_BRIDGE_CF_ACCESS_ID` and `MT5_BRIDGE_CF_ACCESS_SECRET`.

---

## Step 8 — Install mt5-bridge service

The bridge code lives in the main repo at `mt5-bridge/`. Clone it:

```powershell
mkdir C:\mt5-bridge
cd C:\mt5-bridge
git clone https://github.com/whyman404/forex-bot.git .
# Or just sync the mt5-bridge subdir:
#   robocopy ... C:\mt5-bridge mt5-bridge\
cd mt5-bridge
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Create `C:\mt5-bridge\.env` (chmod n/a but restrict ACL):

```ini
APP_ENV=production
BIND=127.0.0.1:9100
LOG_LEVEL=INFO
# Inbound auth — backend uses CF Access service token; bridge re-validates header
CF_ACCESS_AUD=<from-cf-access-policy>
CF_ACCESS_TEAM=<your-team-name>.cloudflareaccess.com
# MT5
MT5_TERMINAL_POOL_SIZE=10
MT5_TERMINAL_TIMEOUT_SECONDS=30
```

Restrict file access:

```powershell
icacls C:\mt5-bridge\.env /inheritance:r /grant:r "mt5runner:R" "Administrators:F"
```

### Install as Windows service via NSSM

```powershell
winget install --id NSSM.NSSM
nssm install mt5-bridge "C:\mt5-bridge\.venv\Scripts\python.exe"
nssm set mt5-bridge AppParameters "-m uvicorn server:app --host 127.0.0.1 --port 9100 --workers 1"
nssm set mt5-bridge AppDirectory "C:\mt5-bridge"
nssm set mt5-bridge ObjectName ".\mt5runner" "<password>"
nssm set mt5-bridge Start SERVICE_AUTO_START
nssm set mt5-bridge AppExit Default Restart
nssm set mt5-bridge AppStdout C:\mt5-bridge\logs\stdout.log
nssm set mt5-bridge AppStderr C:\mt5-bridge\logs\stderr.log
nssm start mt5-bridge
```

Verify: `nssm status mt5-bridge` → `SERVICE_RUNNING`.

---

## Step 9 — Auto-login + auto-start MT5

Without auto-login, a power cycle would leave the VPS at the lock screen with
no bridge running.

### Auto-login

Run `netplwiz` → uncheck "Users must enter a user name and password" → enter
Administrator credentials when prompted. (For higher security, set the
auto-login user to a non-admin and grant only "Log on as a service".)

### Disable lock screen on idle

```powershell
powercfg /change monitor-timeout-ac 0
powercfg /change monitor-timeout-dc 0
powercfg /change disk-timeout-ac 0
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
```

### Disable screen saver lock

`gpedit.msc` → User Configuration → Administrative Templates → Control Panel →
Personalization → "Password protect the screen saver" → Disabled.

---

## Step 10 — Antivirus exclusions

Windows Defender will scan MT5 EX5 files on every load → 2–3 second freezes.

```powershell
Add-MpPreference -ExclusionPath "C:\Program Files\MetaTrader 5"
Add-MpPreference -ExclusionPath "C:\Users\mt5runner\AppData\Roaming\MetaQuotes"
Add-MpPreference -ExclusionPath "C:\mt5-bridge"
Add-MpPreference -ExclusionProcess "terminal64.exe"
Add-MpPreference -ExclusionProcess "python.exe"
```

---

## Step 11 — Smoke test (from Linux VPS)

SSH to Linux VPS and call the bridge via Cloudflare Tunnel:

```bash
curl -fsS \
  -H "CF-Access-Client-Id: $MT5_BRIDGE_CF_ACCESS_ID" \
  -H "CF-Access-Client-Secret: $MT5_BRIDGE_CF_ACCESS_SECRET" \
  https://mt5-bridge.internal.forexbot.example.com/healthz
# {"status":"ok","terminals":10,"connected":10,"version":"0.2.1"}
```

Then a more meaningful smoke:

```bash
curl -fsS \
  -H "CF-Access-Client-Id: $MT5_BRIDGE_CF_ACCESS_ID" \
  -H "CF-Access-Client-Secret: $MT5_BRIDGE_CF_ACCESS_SECRET" \
  https://mt5-bridge.internal.forexbot.example.com/api/v1/terminal/symbols
```

---

## Step 12 — Monitoring (Prometheus)

The bridge exposes `/metrics` on `:9100` (same port, behind the same CF Access
policy). Add it to the Linux Prometheus scrape config (already done in
`infra/observability/prometheus.prod.yml`).

Run a quick test:

```bash
curl -fsS -H "Authorization: Bearer $(cat /etc/prometheus/secrets/mt5-bridge-token)" \
  https://mt5-bridge.internal.forexbot.example.com/metrics | grep mt5_
```

---

## Step 13 — Reboot test

```powershell
shutdown /r /t 5
```

After reboot (wait 2 min):

- [ ] Auto-login worked → desktop visible.
- [ ] `nssm status mt5-bridge` → SERVICE_RUNNING.
- [ ] `Get-Process -Name terminal64` returns one or more processes (terminal pool).
- [ ] `cloudflared tunnel info forex-mt5-bridge` → 4 active connections.
- [ ] Smoke from Linux VPS still returns 200.

If any step fails, fix and re-test before declaring the VPS production-ready.

---

## Maintenance cadence

| Task | Cadence | How |
|---|---|---|
| Windows updates | Weekly (Tue 03:00 UTC) | Auto via "Active hours" 09–17 |
| MT5 updates | Monthly | Manual — test on staging Windows first |
| Reboot | Quarterly | Off-peak Sunday 04:00 UTC |
| Service log rotation | Auto via NSSM rotation | `nssm set mt5-bridge AppRotateFiles 1` |
| Disk cleanup | Monthly | `cleanmgr /sagerun:1` |
| AV update | Auto | n/a |

---

## Cost note

Total Windows VPS spend at Phase 1: ~$20/mo. If we exceed 50 active users
the terminal pool will saturate 4 vCPU and we'll need a second Windows VPS
(linear scaling — see `docs/deployment/cost-tracking.md`).
