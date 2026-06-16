# Windows VPS Setup — MT5 Adapter Host

> Owner: Hestia Kaoru — DevOps / SRE
> Last updated: 2026-06-14

This document walks through bringing up a Windows VPS that runs the MT5
terminal and our `mt5-supervisor.py` process. MT5 only ships a Windows
binary and the official `MetaTrader5` Python package is Windows-only, so
we cannot containerise this on Linux. We keep this host as small as
possible — it only:

1. Runs MT5 terminal (headless)
2. Runs `mt5-supervisor.py` as a Windows Service
3. Talks to the Linux backend over WSS (mTLS)

Nothing else lives here. No web UI. No database. No public ports.

---

## 0. Provider choice

| Provider | Plan | $/mo | Why |
|----------|------|------|-----|
| **Contabo** | VPS S Windows | ~$11 | cheap, RAM-generous |
| **Exness VPS** | Free (with broker) | $0 | best latency, but tied to one account |
| **AWS EC2 t3.small (Windows)** | spot/SR | ~$30 | use only if scale demands |

For MVP/Phase 1 we use **Contabo VPS S Windows** (provisioned via web UI).
Terraform skeleton lives at `infra/terraform/main.tf` but Contabo has no
mature Terraform provider, so this step is manual. Once we move to AWS
EC2, we will Terraform the Windows VPS too.

After provisioning, capture:

- Public IPv4
- Admin password (rotate immediately, store in 1Password vault `forex-bot/secrets`)
- RDP port (move off 3389 to a high port)

---

## 1. Harden Windows

RDP in once, then immediately:

```powershell
# Disable telemetry that isn't needed
Set-Service -Name DiagTrack -StartupType Disabled
Stop-Service -Name DiagTrack

# Enable Windows Update auto-install (security only)
Install-Module PSWindowsUpdate -Force
Get-WUInstall -AcceptAll -AutoReboot -Category 'Security Updates'

# Turn off Windows Defender real-time scan for the trading dir (perf)
Add-MpPreference -ExclusionPath "C:\forex-bot"

# Disable IE Enhanced Security (it breaks installers)
$AdminKey = "HKLM:\SOFTWARE\Microsoft\Active Setup\Installed Components\{A509B1A7-37EF-4b3f-8CFC-4F3A74704073}"
Set-ItemProperty -Path $AdminKey -Name "IsInstalled" -Value 0
```

Move RDP off 3389:

```powershell
Set-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp' -Name PortNumber -Value 52389
New-NetFirewallRule -DisplayName "RDP-52389" -Direction Inbound -LocalPort 52389 -Protocol TCP -Action Allow
Restart-Service TermService -Force
```

Create a non-admin operator account (`forexop`) and use it for the
supervisor service. Admin account is only for emergencies.

---

## 2. Install MT5 terminal (Exness build)

1. Download Exness MT5 installer from broker portal.
2. Install to `C:\forex-bot\mt5\`. Do **not** install to Program Files
   (UAC complications).
3. First-launch: login with the **demo** account first to verify
   connectivity. Live credentials are only injected by the supervisor
   from the secret store later.
4. Enable Algo Trading: `Tools → Options → Expert Advisors → Allow algorithmic trading`.
5. Confirm DLL imports allowed (required for the Python bridge):
   `Tools → Options → Expert Advisors → Allow DLL imports`.

Verify the terminal can run headless:

```powershell
Start-Process "C:\forex-bot\mt5\terminal64.exe" -ArgumentList "/portable"
```

---

## 3. Install Python 3.12

```powershell
# Download Python 3.12 installer.
$installer = "$env:TEMP\python-3.12.6-amd64.exe"
Invoke-WebRequest "https://www.python.org/ftp/python/3.12.6/python-3.12.6-amd64.exe" -OutFile $installer
# Silent install, all users, add to PATH.
Start-Process $installer -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_test=0" -Wait
```

Verify: `python --version` → `3.12.6`.

---

## 4. Install the trading-engine + supervisor

```powershell
# Pull our supervisor script
mkdir C:\forex-bot\supervisor
cd C:\forex-bot\supervisor
# Option A: git pull
git clone https://github.com/your-org/forex-bot.git
cp .\forex-bot\infra\scripts\mt5-supervisor.py .

# Option B: copy file manually via SCP/WinSCP if the host has no git access.

# Create venv and install deps
python -m venv .\venv
.\venv\Scripts\Activate.ps1

pip install --upgrade pip
pip install MetaTrader5 websockets structlog pydantic pydantic-settings httpx tenacity prometheus-client cryptography
```

Sanity check:

```powershell
python -c "import MetaTrader5 as mt5; print(mt5.initialize()); print(mt5.version()); mt5.shutdown()"
```

If `initialize()` returns `False`, run `mt5.last_error()` and check
firewall + that the terminal is currently launched at least once
(MT5 must have a profile dir).

---

## 5. Configure environment

Create `C:\forex-bot\supervisor\.env` (NTFS ACL restrict to `forexop`):

```env
BACKEND_WSS_URL=wss://api.forex-bot.app/ws/mt5-supervisor
SUPERVISOR_ID=mt5-vps-01
SUPERVISOR_SHARED_SECRET=<from 1password — rotate quarterly>
MT5_LOGIN=<from 1password — broker login>
MT5_PASSWORD=<from 1password — broker password>
MT5_SERVER=Exness-MT5Real8
MT5_TERMINAL_PATH=C:\forex-bot\mt5\terminal64.exe
HEARTBEAT_INTERVAL=10
RECONNECT_BACKOFF_MAX=60
PROMETHEUS_PORT=9101
LOG_LEVEL=INFO
```

ACL:

```powershell
icacls "C:\forex-bot\supervisor\.env" /inheritance:r /grant:r "forexop:R" /grant:r "SYSTEM:R" /grant:r "Administrators:F"
```

---

## 6. Install as Windows Service via NSSM

NSSM (Non-Sucking Service Manager) wraps the Python process as a proper
Windows service with restart-on-failure and stdout/stderr capture.

```powershell
# Download NSSM
$nssm = "$env:TEMP\nssm.zip"
Invoke-WebRequest "https://nssm.cc/release/nssm-2.24.zip" -OutFile $nssm
Expand-Archive $nssm -DestinationPath C:\nssm
Copy-Item C:\nssm\nssm-2.24\win64\nssm.exe C:\Windows\System32\

# Create the service
nssm install MT5Supervisor `
  "C:\forex-bot\supervisor\venv\Scripts\python.exe" `
  "C:\forex-bot\supervisor\mt5-supervisor.py"

nssm set MT5Supervisor AppDirectory "C:\forex-bot\supervisor"
nssm set MT5Supervisor DisplayName "Forex Bot MT5 Supervisor"
nssm set MT5Supervisor Description "Bridges MT5 terminal with backend over WSS"
nssm set MT5Supervisor Start SERVICE_AUTO_START
nssm set MT5Supervisor ObjectName ".\forexop" "<password>"
nssm set MT5Supervisor AppStdout "C:\forex-bot\supervisor\logs\stdout.log"
nssm set MT5Supervisor AppStderr "C:\forex-bot\supervisor\logs\stderr.log"
nssm set MT5Supervisor AppRotateFiles 1
nssm set MT5Supervisor AppRotateBytes 10485760

# Auto-restart on crash with exponential backoff
nssm set MT5Supervisor AppExit Default Restart
nssm set MT5Supervisor AppRestartDelay 5000

nssm start MT5Supervisor
```

Verify:

```powershell
nssm status MT5Supervisor
Get-Content C:\forex-bot\supervisor\logs\stdout.log -Tail 50
```

---

## 7. Firewall — outbound to backend only

Lock outbound to just our backend (Cloudflare Tunnel endpoint):

```powershell
# Block all outbound by default — opt in to what we need
New-NetFirewallRule -DisplayName "Block all out" -Direction Outbound -Action Block -Profile Any

# Allow DNS, NTP, Windows Update (Microsoft signed)
New-NetFirewallRule -DisplayName "DNS" -Direction Outbound -Protocol UDP -RemotePort 53 -Action Allow
New-NetFirewallRule -DisplayName "NTP" -Direction Outbound -Protocol UDP -RemotePort 123 -Action Allow

# Allow MT5 broker servers (Exness)
New-NetFirewallRule -DisplayName "MT5 broker out" -Direction Outbound -Program "C:\forex-bot\mt5\terminal64.exe" -Action Allow

# Allow our backend WSS endpoint
New-NetFirewallRule -DisplayName "Backend WSS" -Direction Outbound -RemoteAddress api.forex-bot.app -Protocol TCP -RemotePort 443 -Action Allow

# Allow Prometheus pull from internal monitoring host only
New-NetFirewallRule -DisplayName "Prom scrape" -Direction Inbound -RemoteAddress <monitoring-host-ip> -Protocol TCP -LocalPort 9101 -Action Allow
```

---

## 8. Monitoring agent

We use `windows_exporter` for host metrics — Prometheus scrapes it.

```powershell
$exporter = "$env:TEMP\windows_exporter.msi"
Invoke-WebRequest "https://github.com/prometheus-community/windows_exporter/releases/download/v0.27.2/windows_exporter-0.27.2-amd64.msi" -OutFile $exporter
Start-Process msiexec.exe -ArgumentList "/i $exporter ENABLED_COLLECTORS=cpu,cs,logical_disk,net,os,service,system,memory,process LISTEN_PORT=9182 /quiet" -Wait
```

Allow inbound 9182 from monitoring host only (same pattern as above).

---

## 9. Verification checklist

- [ ] RDP works on the custom port
- [ ] `nssm status MT5Supervisor` returns `SERVICE_RUNNING`
- [ ] Backend dashboard shows `mt5_supervisor_last_heartbeat_timestamp_seconds` updating
- [ ] `windows_exporter` reachable on 9182 from monitoring host
- [ ] All outbound traffic blocked except the rules above
- [ ] BitLocker enabled on system drive
- [ ] Local admin account renamed; default `Administrator` disabled
- [ ] Telemetry/Cortana disabled

---

## 10. Disaster recovery

| Scenario | Action |
|----------|--------|
| VPS lost | Rebuild from this doc + restore `.env` from 1Password. RTO ~30min. |
| MT5 corrupted | Reinstall, log in once with demo, restart supervisor. |
| Service stuck | `nssm restart MT5Supervisor`. If repeat → see runbook `mt5-disconnect.md`. |
| Broker change | Update `MT5_SERVER` in `.env`, restart. |

When in doubt — the backend's kill switch already pauses live orders if
heartbeats stop. There is no urgency to ssh in at 3am; first roll over
to the standby Windows VPS if provisioned.
