# Backup & Restore — Forex Bot

> Owner: Hestia Kaoru
> Last updated: 2026-06-15

## Layout

```
infra/backup/
├── backup.sh   # pg_dump → gzip → R2 (cron 0 2 * * *)
├── restore.sh  # interactive restore (DR drill or recovery)
├── verify.sh   # random restore into throwaway db (cron 0 4 * * 0)
└── README.md   # you are here
```

## Configuration

Single env file: `/etc/forex-bot/backup.env`, chmod 600 root:root.

```bash
R2_BUCKET=forex-bot-backups
R2_ACCESS_KEY=...
R2_SECRET_KEY=...
R2_ENDPOINT=https://<accountid>.r2.cloudflarestorage.com
POSTGRES_USER=forex
POSTGRES_PASSWORD=...
POSTGRES_DB=forex_bot
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
GPG_RECIPIENT=ops@forexbot.example.com   # optional encryption
SLACK_WEBHOOK_URL=https://hooks.slack.com/...
NODE_TEXTFILE_DIR=/var/lib/node_exporter/textfile_collector
```

## Retention

- Daily : 7 newest
- Weekly: 4 newest (Sunday dumps)
- Monthly: 12 newest (1st of month dumps)

Enforced in two places (defense in depth):

1. `backup.sh` runs `prune_tier` after each upload.
2. R2 bucket lifecycle policy (configure via Cloudflare dashboard or wrangler):
   ```
   postgres/daily/*    -> delete after 8 days
   postgres/weekly/*   -> delete after 35 days
   postgres/monthly/*  -> delete after 400 days
   ```

## Cron entries (host)

```cron
# m h dom mon dow command
0 2 * * *  /srv/forex-bot/infra/backup/backup.sh >/dev/null 2>&1
0 4 * * 0  /srv/forex-bot/infra/backup/verify.sh >/dev/null 2>&1
```

## RPO / RTO

- **RPO** — 24h with daily backup; 1h once WAL shipping is added (Phase 3).
- **RTO** — 4h: provision fresh VPS, install docker, clone repo, `make deploy-prod`, `restore.sh --tier daily`.

## Cost projection (Cloudflare R2)

- Storage: $0.015/GB/mo (no egress fees).
- 50 MB compressed dump × (7 + 4 + 12) = 1.15 GB → **$0.02/mo**.
- 1000 Class A ops/mo (writes): $4.50 per million → ~$0.005/mo.
- **Effective cost: under $0.05/mo.**

Compare to B2: $0.005/GB/mo + $0.01/GB egress. R2 wins as soon as we need to
test-restore (egress is free on R2).

## Verification cadence

- `verify.sh` runs weekly on Sunday 04:00 UTC.
- Quarterly DR drill: human-driven restore to fresh VPS, verify full app starts,
  document in `docs/deployment/disaster-recovery.md`.

## Alerts

Prometheus alert (defined in `infra/observability/alerts/rules.yml`):

```promql
# No backup in 26h (give 2h grace window)
absent_over_time(forex_bot_backup_last_success_timestamp_seconds[26h])
or
time() - forex_bot_backup_last_success_timestamp_seconds > 26*3600
```
