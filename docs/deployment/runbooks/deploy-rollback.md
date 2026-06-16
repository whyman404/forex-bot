# Runbook — Deploy Rollback

> Severity: depends on impact
> Owner: on-call DevOps (Hestia)
> Last updated: 2026-06-15

> Rule of thumb: **rollback first, fix forward second.** If you can roll
> back in < 10 minutes, do it. Then debug.

## When to use

* A deploy went out → error rate jumps, latency spikes, or a critical
  feature is broken.
* The `deploy-prod` workflow's smoke test failed.
* A user report comes in within an hour of a deploy.

## Identify the bad version

```bash
# On the prod VPS
cat /opt/forex-bot/.last-deploy-tag      # the version live right now
docker image ls | grep forex-bot         # previous images present locally
```

In GitHub:

* `Actions → deploy-prod` history shows the previous successful tag.
* The image is still in GHCR — `ghcr.io/<org>/forex-bot-backend:<tag>`.

## Procedure — manual rollback

```bash
# 1. SSH in.
ssh deploy@app.forex-bot.app
cd /opt/forex-bot

# 2. Find the previous good tag — usually one before .last-deploy-tag.
# Example: assume current is `release/2026-06-15` and previous was `release/2026-06-14`.
PREV_TAG=release/2026-06-14
export IMAGE_TAG=$PREV_TAG

# 3. Pull (idempotent if local).
echo "$GHCR_PAT" | docker login ghcr.io -u "$GH_USER" --password-stdin
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull

# 4. Roll back, start-first to avoid downtime.
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --remove-orphans

# 5. Update the marker so next deploy compares against the right baseline.
echo "$PREV_TAG" > .last-deploy-tag

# 6. Confirm.
curl -fsS https://api.forex-bot.app/healthz
curl -fsS https://api.forex-bot.app/readyz
```

## Procedure — GitHub Actions rollback

If the SSH path is unavailable but Actions works:

1. `Actions → deploy-prod → Run workflow`.
2. Set `image_tag` to the last good tag.
3. Confirm "Friday check" allows it (or include `[force-friday]` in a
   trivial commit message if needed).
4. Watch the smoke test step.

## What if the rollback also fails the smoke test?

* Don't keep rolling back further blindly — that usually means a
  dependency (DB schema, env var) is the real problem.
* Roll forward partially: keep the old backend image but apply the bad
  release's migration revert. See "Schema rollback" below.
* If the issue is environmental (e.g. broker credentials changed), fix
  the env in `/opt/forex-bot/backend/.env` and `docker compose up -d`.

## Schema rollback (rare)

We treat Alembic migrations as **forward-only**. To "roll back" a
migration:

1. Write a new migration that reverses the change.
2. Run `migrate.yml` with `target=head`.

Direct `alembic downgrade` is only used in emergencies and only after
taking a DB backup. The runbook for that:

```bash
# Backup first.
docker compose exec postgres pg_dump -U forex -Fc forex_bot > /data/backups/pre-downgrade-$(date -u +%Y%m%dT%H%M%SZ).dump

# Then downgrade.
docker compose exec backend alembic downgrade -1
```

## Verification

After rolling back, sanity-check:

* `/healthz` and `/readyz` 200.
* p95 latency back below 500 ms within 5 minutes.
* Error rate back below 1%.
* Open-positions dashboard matches MT5 terminal count (no drift).
* User report sample re-run if applicable.

## Communications

* Post in #ops Discord: "Rolled back prod to `<tag>` due to <reason>.
  Will follow with postmortem."
* Status page: update within 5 minutes of starting rollback and again on
  completion.

## After

* Within 48 h: postmortem covering what shipped, what broke, what was
  missing in CI to catch it.
* Add a regression test that fails on the original bad change.
* If repeated rollbacks in a week → call a 30-min team retro to discuss
  process changes.
