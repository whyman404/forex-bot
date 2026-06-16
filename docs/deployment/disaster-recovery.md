# Disaster Recovery Plan — Forex Bot

> Owner: Hestia Kaoru
> Last updated: 2026-06-15
> Review cadence: every 6 months
>
> "If we can't restore, we don't have backups." — Charity Majors

---

## Targets

| Metric | Phase 1 (current) | Phase 3 target |
|---|---|---|
| RPO (max data loss) | 24h (daily dump) | 1h (WAL shipping) |
| RTO (recovery wall-clock) | 4h | 2h |
| Tested quarterly? | Yes | Yes |

---

## Scenario matrix

| Scenario | Probability | Impact | Recovery procedure |
|---|---|---|---|
| Linux VPS host failure | low | total app outage | A. Provision fresh VPS + restore from R2 |
| Postgres data corruption | low | data loss | B. Stop app, restore latest dump |
| Accidental DROP TABLE / DELETE | medium | partial data loss | C. PITR (post Phase 3) or restore + replay diff |
| Windows MT5 VPS failure | medium | live trading paused | D. Provision new VPS or fail over to second |
| Cloudflare account compromise | very low | DNS hijack | E. Use registrar to point DNS to alternate provider |
| R2 backup loss | very low | DR option gone | F. We keep weekly off-site copy on Backblaze B2 |
| Full regional outage (Hetzner EU) | very low | total | G. Standby VPS in different provider |

---

## Recovery procedure A — Linux VPS replacement

**RTO target: 4h.**

```
T+0:00  Detect outage (alertmanager: ExternalHealthCheckFailing,
                       BackendDown, PostgresDown all firing).
T+0:05  Acknowledge in #incidents. Post status page.
T+0:15  Provision fresh Hetzner CX31 in Falkenstein (same region).
T+0:30  SSH in, run setup-vps.sh.
T+0:45  Copy /etc/forex-bot/.env (from 1Password backup).
T+1:00  Update Cloudflare DNS A records to new IP.
        (TTL was Auto-Cloudflare; propagation ~30s.)
T+1:05  Pull repo, make deploy-prod (skip tests for speed).
T+1:30  Restore DB from R2: ./infra/backup/restore.sh --tier daily --yes
T+1:50  Run alembic upgrade head if a migration was pending.
T+2:00  Smoke: curl /healthz, login as admin, run a backtest.
T+2:30  Post in #incidents that app is up.
T+3:00  Reconnect Windows VPS bridge (verify CF Access policy still valid).
T+4:00  Backfill any orders missed during outage (see broker reconciliation
        below).
```

### Broker reconciliation (post-outage)

Live engines may have entered or exited positions while the app was down.
Procedure:

1. Query MT5 for `position_history` since outage start.
2. Compare to backend `trades` table.
3. INSERT missing trade rows (don't UPDATE — preserve audit).
4. Recompute daily P&L.

Tool: `backend/app/scripts/reconcile_broker.py` (writes diff to a CSV before
applying — DO read it before pressing y).

---

## Recovery procedure B — DB restore in-place

When the host is fine but the DB is corrupt or wrong (bad migration, ops
error, schema drift).

```
1) Stop app — leave postgres running:
   docker compose ... stop backend frontend trading-engine

2) Take a snapshot of the bad state (forensics):
   docker compose ... exec postgres pg_dump -U forex forex_bot \
     | gzip > /srv/forex-bot/data/bad-state-$(date +%s).sql.gz

3) Rename current DB to keep as evidence:
   ALTER DATABASE forex_bot RENAME TO forex_bot_pre_restore;

4) Restore from R2 into fresh DB:
   ./infra/backup/restore.sh --target-db forex_bot --yes

5) Run alembic upgrade head if app is newer than backup.

6) Start app:
   docker compose ... up -d backend frontend trading-engine

7) Smoke + reconcile.

8) After 7 days, drop the evidence DB.
```

---

## Recovery procedure C — Point-in-time-recovery (Phase 3)

Today (Phase 1-2) we have daily dumps only. PITR requires WAL shipping which
is on the Phase 3 backlog. Until then, we accept up to 24h data loss for the
"accidental DELETE" case.

**Phase 3 plan:**
- WAL shipping with `pgbackrest` to R2 (RPO ~5 min).
- `restore_target_time` parameter on restore.
- Test in quarterly drill.

---

## Recovery procedure D — Windows VPS failover

Today we run one Windows VPS (singleton). If it fails:

1. Live engines pause automatically (heartbeat alert fires within 2 min).
2. Provision new Contabo VPS M Windows.
3. Follow `infra/scripts/setup-windows-mt5-vps.md` (~90 min).
4. Update Cloudflare Tunnel hostname → new VPS.
5. Re-enable live engines via admin panel.

**Phase 3 plan:** active/passive Windows pair, automatic failover on
heartbeat loss.

---

## Off-site copies

R2 is our primary backup target. As a belt-and-suspenders we also push the
**weekly** dump to Backblaze B2 (different vendor, different region) via a
cron entry:

```cron
30 2 * * 0  /srv/forex-bot/infra/backup/sync-to-b2.sh
```

(That script is a thin wrapper around `aws s3 sync` against B2's S3-compatible
endpoint. Cost: ~$1/year for the weekly copies.)

---

## Quarterly DR drill

**Cadence:** first Sunday of quarter, 14:00 UTC, 2h window.

**Drill script:**

1. Operator provisions a throwaway Hetzner CX21 in a different region.
2. Run `setup-vps.sh`.
3. Run `restore.sh --tier weekly` against fresh DB.
4. Run `verify.sh` style sanity checks.
5. Boot the app, login as admin, run a backtest.
6. Time each step.
7. Destroy the throwaway VPS.
8. Document timing + any surprises in `docs/deployment/dr-drill-log.md`.

If RTO blew past 4h, the drill is a FAIL → open postmortem.

---

## Secrets recovery

`.env.prod` lives in 1Password vault "forex-bot-ops" (shared with: Zeus, Hestia,
Argus). If 1Password is lost:

1. Apple recovery contact (Zeus's mother) has emergency access kit.
2. Cloudflare account 2FA recovery code printed and stored in safety
   deposit box (physical paper).
3. GitHub recovery codes likewise.

This is the painful "what if the founder gets hit by a bus" plan. We test it
annually with a no-laptop drill.
