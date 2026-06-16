# Runbook — Postgres Failover / Disaster Recovery

> Severity: page
> Owner: on-call DevOps (Hestia)
> Last updated: 2026-06-15

> Phase 1 has **no live replica**. "Failover" here means "restore from R2
> backup as fast as we can." The RTO target is **< 1 hour**; the RPO target
> (data loss tolerance) is **< 5 minutes**, achievable because WAL archives
> ship continuously to R2.

## Symptom

One or more:

* `PostgresDown` alert firing.
* Backend health check failing with DB connection errors.
* User reports of data loss / inconsistency.

## Pre-checks (60 seconds)

1. SSH into the Linux VPS: `ssh deploy@app.forex-bot.app`.
2. `docker compose ps postgres` — is the container running?
3. `docker compose logs postgres --tail=200` — what is it complaining
   about?

## Decision tree

```
Container running?
├── NO  → A. Container stopped
└── YES → Can the backend connect?
         ├── YES → False alarm, investigate the alert
         └── NO  → B. Disk full / corrupt / OOM
```

### A. Container stopped

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d postgres
docker compose logs postgres --tail=200
```

If it stays exited:

* Disk space: `df -h /data`.
* Corruption: `docker compose logs postgres | grep -iE "panic|invalid page"`.

If corruption is suspected, jump to "Restore from backup" below.

### B. Disk full

```bash
df -h /data
docker compose exec postgres du -sh /var/lib/postgresql/data/*
# If pg_wal is huge, archive_command is failing — check R2 reachability.
```

* Free up: drop old log files, vacuum old tables, or extend the volume
  in Hetzner Cloud (then `parted` + `resize2fs`).
* Verify `archive_command` is succeeding:
  `docker compose exec postgres psql -U forex -c "select last_archived_wal, last_failed_wal from pg_stat_archiver;"`

### Restore from backup (worst case)

You need:

* The R2 bucket (`forex-bot-backups`).
* The GPG passphrase (1Password → `forex-bot/secrets/pgbackup-gpg`).
* The newest base dump + every WAL since it.

```bash
# 1. Take the current (broken) DB offline.
docker compose stop postgres trading-engine backend

# 2. Move broken data dir aside (do not delete — forensics).
sudo mv /data/postgres /data/postgres.broken-$(date -u +%Y%m%dT%H%M%SZ)
sudo mkdir -p /data/postgres
sudo chown 999:999 /data/postgres

# 3. Pull most recent base dump.
aws s3 ls s3://forex-bot-backups/pgdump/ --endpoint $R2_ENDPOINT | tail -5
aws s3 cp s3://forex-bot-backups/pgdump/forex_bot-2026-06-15T0200Z.dump.gpg . --endpoint $R2_ENDPOINT
gpg --decrypt --passphrase-file ~/gpg-pass forex_bot-2026-06-15T0200Z.dump.gpg > forex_bot.dump

# 4. Start a fresh postgres container.
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d postgres
sleep 10
docker compose exec -T postgres createdb -U forex forex_bot
docker compose exec -T postgres pg_restore -U forex -d forex_bot < forex_bot.dump

# 5. (Optional) Replay WAL to recover newer data — PITR.
#    We use a separate "restore" container with recovery.conf.
#    Skip this if the morning dump is acceptable for RPO.
#
#    See backup-and-restore.md for PITR procedure.

# 6. Smoke test.
docker compose exec postgres psql -U forex forex_bot -c "select count(*) from users;"

# 7. Start dependent services.
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d backend trading-engine
curl -fsS https://api.forex-bot.app/healthz
```

## Mitigation order

1. Restart container (the easy fix).
2. Extend disk if disk-full.
3. Restore from backup (worst case).
4. Failover to standby host (if provisioned in Phase 2+).

## Rollback

This is restore-from-backup; there is no further rollback. If the
restore fails, escalate; we keep the broken data dir for forensics.

## Communications

* Status page: post within 5 minutes of declaration.
* Discord ops channel: continuous updates.
* User comms (email + in-app banner): within 15 minutes if data loss is
  possible, including the affected time window.

## Escalation

* Restore taking longer than 30 minutes → page Atlas (backend lead) and
  consider customer comms for extended downtime.
* Any indication of data corruption that wasn't from disk failure →
  isolate the data, do not delete; involve security (Argus).

## After

* Postmortem within 48 h, including: data-loss estimate (rows / users
  affected), customer comms timeline, action items.
* Verify the daily backup that restored cleanly — add a Grafana panel
  for "last successful restore drill timestamp" so we never go > 90 days
  without one.
