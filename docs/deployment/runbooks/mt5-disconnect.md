# Runbook — MT5 Supervisor Disconnect

> Severity: page
> Owner: on-call DevOps (Hestia)
> Last updated: 2026-06-15

## Symptom

One or both alerts firing:

* `MT5SupervisorDown` — no heartbeat for ≥ 60 s.
* `MT5BrokerConnectionLost` — `mt5_broker_connected == 0`.

Customer impact: **new live orders pause automatically** (the backend's
kill switch trips on stale heartbeat). Existing positions remain at the
broker, untouched.

## Pre-checks (60 seconds)

1. Open the Grafana panel
   `Forex Bot — API Overview → MT5 heartbeat (s ago)`.
   Confirm the spike is real, not a Prometheus scrape glitch (scrape gap
   < 30 s ≠ supervisor down).
2. Check the alert was not also raised in staging — if so, ignore the
   prod page (someone is testing).

## Diagnosis tree

```
mt5_supervisor up?
├── NO  → A. Process/service crash
└── YES → mt5_broker_connected == 1?
         ├── NO  → B. Broker connection lost
         └── YES → C. WSS dropped between supervisor and backend
```

### A. Process / service crash (supervisor down)

* RDP into the Windows VPS (jumphost or Cloudflare Access).
* `nssm status MT5Supervisor` — expect `SERVICE_RUNNING`.
* If not running:
  * `nssm start MT5Supervisor`.
  * `Get-Content C:\forex-bot\supervisor\logs\stderr.log -Tail 100` —
    look for stack traces.
* If crashing in a loop:
  * Disable the service (`nssm pause`) and run the script manually in a
    PowerShell window to see the real failure:
    `C:\forex-bot\supervisor\venv\Scripts\python.exe mt5-supervisor.py`.
  * Common causes:
    * `.env` missing or corrupt (file permissions)
    * Wrong broker credentials → `mt5.last_error()` will say
      `Invalid account`
    * MT5 terminal directory missing — reinstall MT5 then retry.

### B. Broker connection lost

* Open the MT5 terminal GUI (RDP). The status bar shows "No connection".
* Usually broker-side; check Exness status page.
* If broker is up:
  * Verify VPS outbound to broker hostnames is allowed by Windows
    firewall (`Get-NetFirewallRule -DisplayName "MT5 broker out"`).
  * Sometimes Exness rotates server hostnames — update `MT5_SERVER` in
    `.env` and restart the service.

### C. WSS dropped (supervisor up, broker connected)

* Backend side first:
  * Check backend logs for `mt5-supervisor disconnect`.
  * `docker compose logs backend | grep mt5` on the Linux VPS.
  * If backend has been bouncing, the supervisor will reconnect with
    exponential backoff (max 60 s).
* Cloudflare Tunnel:
  * `cloudflared tunnel info forex-bot-app` — must show a healthy
    connection.
  * If tunnel is degraded, supervisor cannot reach the backend WSS.

## Mitigation

In order of preference:

1. **Restart the supervisor service** if it is in a stuck state:

   ```powershell
   nssm restart MT5Supervisor
   ```

2. **Failover to standby Windows VPS** (only if provisioned):

   * Switch backend env var `MT5_SUPERVISOR_ALLOWLIST` to include the
     standby's `supervisor_id`.
   * Start the standby supervisor; it will register and start receiving
     orders within ~10 s.

3. **Manual position reconciliation** (only if supervisor was down > 5 min
   and trading was active):

   * In MT5 terminal, list current positions.
   * Run `POST /admin/reconcile` on backend with the listed positions.
     The endpoint matches them against backend state, marks any
     orphaned ones, and emits a Slack/Discord notice for review.

4. **Operator override — manual kill switch**:

   * If something is fundamentally wrong, hit
     `POST /admin/kill-switch?account=ALL` from the ops dashboard.
     All future orders will be rejected with a clear error until you
     clear the flag.

## Rollback

If you suspect the latest supervisor build broke things:

```powershell
# On the Windows VPS
cd C:\forex-bot\supervisor
git log --oneline -5
git checkout <previous-sha> -- mt5-supervisor.py
nssm restart MT5Supervisor
```

## Escalation

* No heartbeat after 15 minutes despite restarts → page the on-call
  backend engineer (Atlas) too; we may need to disable the broker
  integration entirely.
* Funds at risk → engage user comms within 30 minutes (Discord +
  in-app banner).
* Repeat incident this week → open postmortem doc and book a 30-minute
  retro within 48h.

## Postmortem expectations

* Include: timeline (every action with UTC timestamp), root cause,
  blast radius (open positions, orders rejected), action items with
  owners and deadlines. File in
  `dev-team/05-devops-hestia-kaoru/work/postmortems/`.
