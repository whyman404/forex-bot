# Neon (Postgres) + Upstash (Redis) — External managed DB setup

> Optional path: use Neon for Postgres and Upstash for Redis instead of
> Railway plugins. Lower cost at low traffic, generous free tiers.

---

## When to choose this over Railway plugins

| Need | Railway plugin | Neon/Upstash |
|---|---|---|
| First 100 users | $10/mo combined | $0 (free tier) |
| Low maintenance | yes (same dashboard) | separate accounts, similar pain |
| Branching DBs (preview env) | no | **yes (Neon)** |
| Globally edge-cached reads | no | **yes (Upstash)** |
| Single bill | **yes** | no |

**Recommendation:** start with Neon + Upstash to stay free; migrate to Railway plugins when you outgrow tier limits.

---

## Step 1 — Create Neon project (Postgres)

1. Sign up at **https://neon.tech** (GitHub login).
2. New Project → name `forex-bot-prod` → region `Singapore` (closest to Railway `asia-southeast1`).
3. Postgres version → **16**.
4. Default database: `forexbot`.
5. From the dashboard → **Connection Details** → copy the **Pooled connection** string:

   ```
   postgresql://forexbot:PASSWORD@ep-cool-name-12345.ap-southeast-1.aws.neon.tech/forexbot?sslmode=require
   ```

6. For SQLAlchemy async, swap `postgresql://` → `postgresql+asyncpg://`:

   ```
   DATABASE_URL=postgresql+asyncpg://forexbot:PASSWORD@ep-cool-name-12345.ap-southeast-1.aws.neon.tech/forexbot?ssl=require
   ```

   > **Important:** asyncpg uses `ssl=require`, not `sslmode=require`. Both work but asyncpg prefers the former.

### Run migrations from your local machine

```bash
cd backend
export DATABASE_URL='postgresql+asyncpg://forexbot:PASSWORD@ep-...neon.tech/forexbot?ssl=require'
uv run alembic upgrade head
uv run python -m scripts.seed_admin    # optional dev seed
```

### Neon free tier limits (as of 2026)

- 0.5 GB storage
- 1 compute unit, auto-suspends after 5 min idle (cold start ~1s)
- 100 hours of compute time per month
- 10 branches (great for preview environments)

> **Cold start gotcha:** the auto-suspend means the first request after idle adds ~1s. Disable auto-suspend on the production branch (paid feature, $19/mo Launch plan) once traffic justifies it.

---

## Step 2 — Create Upstash Redis

1. Sign up at **https://upstash.com** (GitHub login).
2. Create Database → name `forex-bot-prod` → region `ap-southeast-1` (Singapore).
3. Type → **Regional** (cheaper than Global; pick Global only if you need multi-region).
4. Enable **TLS** (default).
5. Copy the URL from "Connect" → **TLS (rediss://)**:

   ```
   REDIS_URL=rediss://default:PASSWORD@apt-frog-12345.upstash.io:6379
   ```

   The `rediss://` scheme (double `s`) signals TLS to the client library.

### Configure RQ worker for TLS

The backtest worker uses `rq worker backtest --url $REDIS_URL`. RQ handles `rediss://` transparently.

### Upstash free tier limits

- 256 MB max DB size
- 10,000 commands/day (resets at 00:00 UTC)
- 1 connection at a time on the absolute free tier (upgrade to **Pay as you go** for $0.20/100k commands once you exceed)

> Most Forex Bot workloads stay well under 10k/day until ~50 concurrent users.

---

## Step 3 — Wire into Railway (or Vercel)

In Railway dashboard → backend service → Variables:

```
DATABASE_URL = postgresql+asyncpg://forexbot:...neon.tech/forexbot?ssl=require
REDIS_URL    = rediss://default:...upstash.io:6379
```

Skip the Postgres + Redis plugins entirely. Restart all services.

For Vercel (frontend doesn't touch DB directly), no change needed.

---

## Cost comparison

| Tier | Railway plugins | Neon + Upstash |
|---|---|---|
| First user | $10/mo | **$0** |
| 100 users / 1M requests | $10/mo | **$0** |
| 1000 users / 50M requests | $10/mo (Hobby still fits) | ~$20/mo (Neon Launch + Upstash PAYG) |
| 10000 users | $30/mo (Pro plan) | ~$50/mo |

**Break-even:** around 1000 active users / mo. Below that → Neon+Upstash is free. Above that → Railway plugins become cheaper.

---

## Backup strategy

### Neon
- **Point-in-time recovery (PITR):** 24h on free tier, 7 days on Launch
- Manual backup → use Neon's "Restore" tab to create a branch from any time in the retention window
- Off-Neon backup: cron `pg_dump $DATABASE_URL | gzip | aws s3 cp - s3://...` weekly

### Upstash
- Daily backup included on Pay-as-you-go tier ($0.10/GB)
- Free tier: NO backups. Critical state (subscriptions, audit log) MUST be in Postgres, never only in Redis.

---

## Migration runbook (Neon → Railway plugin, if you outgrow)

1. Create Railway Postgres plugin → it gives you a new `DATABASE_URL`.
2. Put backend in maintenance mode (set `FEATURE_FLAGS_MAINTENANCE=true` env var → middleware returns 503).
3. `pg_dump` from Neon → restore into Railway Postgres:
   ```bash
   pg_dump $NEON_URL | psql $RAILWAY_DATABASE_URL
   ```
4. Update `DATABASE_URL` env var on Railway services → restart.
5. Verify `alembic current` matches head → drop maintenance mode.
6. Keep Neon read-only for 7 days as fallback. Then archive + delete.

Expected downtime: 2–10 min depending on DB size.

---

## Troubleshooting

### "asyncpg: SSL connection failed"
Use `?ssl=require`, not `?sslmode=require`. asyncpg parses ssl options differently from psycopg2.

### "Too many connections" on Neon free tier
The free tier limits 100 simultaneous connections. Use Neon's **pooled** connection string (not direct) — it's already in pgbouncer transaction mode.

### "ECONNREFUSED" from RQ worker → Upstash
Some old versions of RQ/redis-py don't handle TLS correctly. Pin `redis>=5.0.1` (already done in `pyproject.toml`).

### Migration fails: `relation does not exist`
You ran `alembic upgrade head` against the wrong URL. Confirm:
```bash
alembic current   # should print: 0004 (head)
```

### Redis evictions
Free tier evicts oldest keys when full. Avoid storing long-lived state in Redis — use Postgres for anything that must persist > 24h.
