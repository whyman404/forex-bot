# Cost Tracking — Forex Bot Infrastructure

> Owner: Hestia Kaoru
> Last updated: 2026-06-15
> Review cadence: monthly
>
> "Cost optimization is engineering, not accounting." — Hestia

---

## Cost by scale tier

| Item | 10 users (Phase 1) | 50 users (Phase 2) | 200 users (Phase 3) |
|---|---|---|---|
| Linux VPS (Hetzner) | CX31 $15 | CX31 $15 | CX41 $30 |
| Windows VPS (Contabo) | VPS M $20 | VPS M $20 | 2× VPS M $40 |
| Cloudflare | Free | Free | Pro $20 |
| R2 storage | <$0.05 | $0.30 | $1.50 |
| R2 ops (Class A) | <$0.01 | $0.05 | $0.20 |
| Backblaze B2 (weekly off-site) | $0.10 | $0.50 | $2.00 |
| Status page (better-stack) | Free | Free | $18 |
| PagerDuty | Free tier 5 users | Free tier | Team $19/user |
| Slack | Free | Free | Standard $7.25/user |
| Sentry (errors) | Free 5k events | Team $26 | Team $26 |
| Domain renewal (annualized) | $1 | $1 | $1 |
| GitHub Actions (CI) | Free 2000 min | $4 (3500 min) | $16 (5000 min) |
| **TOTAL / month** | **~$36** | **~$67** | **~$200** |

Notes:
- "10 users" assumes ~3 paying ($25/mo Pro). Net profit margin = (75-36)/75 = 52%.
- "50 users" assumes ~15 paying. Net = (375-67)/375 = 82%.
- "200 users" assumes ~60 paying. Net = (1500-200)/1500 = 87%.
- Variable users (free tier) cost ~$0.50/mo each in compute share.

---

## Cost guardrails (alerts)

- Alert when Hetzner monthly bill > $50 (1.5x current CX31).
- Alert when Cloudflare bandwidth > 95% of free plan (Plan B: Pro upgrade is
  pre-approved).
- Alert when R2 storage > 5 GB (means backups not pruning correctly).
- Alert when CI minutes > 80% of free allotment.

All implemented as Cloudflare API + AWS billing API checks in
`infra/scripts/cost-report.sh` (cron 0 8 * * 1 — Monday morning email).

---

## Optimization wins (already taken)

1. **R2 over S3** — R2 has zero egress fees. We test-restore weekly without
   paying for egress.
2. **Cloudflare in front of VPS** — caches static (free), reduces Hetzner
   egress (Hetzner has a soft 20 TB cap; we use ~50 GB/mo).
3. **Single-VPS dev** — no separate "staging" until we have paying users
   (currently CI builds the prod image in PR and tests it, no separate env).
4. **Hetzner over AWS/GCP** — same workload would be ~$120/mo on EC2.
5. **Docker compose over k8s** — at 200 users, k8s would add $30/mo control
   plane (managed) or 1 vCPU/2GB of overhead (self-managed). Compose wins
   until ~500 users.

---

## Optimization candidates (not yet taken)

| Item | Saving | Effort | When |
|---|---|---|---|
| Use Hetzner volumes (cheap storage) for /srv | $5/mo at 100GB | low | Phase 3 |
| Move logs to S3 archive tier after 30d | $0.50/mo | medium | Phase 3 |
| Spot Windows VPS for backtest pool | $10/mo | high | Phase 4 |
| Self-hosted PagerDuty (oncall.tools, etc.) | $30/mo | medium | Phase 4 |
| Bunny.net CDN for video assets | $5/mo | low | when we add tutorials |

---

## Variable cost model

Per-user monthly cost (incremental, above fixed):

| Resource | Per active user | Per paying user (lives) | Per backtest run |
|---|---|---|---|
| CPU-hours (backend) | $0.10 | $0.20 | n/a |
| CPU-hours (engine) | n/a | $0.50 | $0.05 |
| DB storage | $0.01 | $0.05 | n/a |
| Bandwidth | $0.02 | $0.05 | n/a |
| MT5 terminal slot | n/a | $1.00 | n/a |
| **Total / user** | **$0.13** | **$1.80** | **$0.05** |

Pricing implication: $25/mo Pro tier is 13× margin. Healthy.

---

## Reporting

Monthly cost report posted in `#leadership` Slack channel on the 1st:

- Hetzner invoice (from API).
- Cloudflare invoice (export from dashboard).
- AWS-style consolidated for R2 + B2.
- Per-user cost trend.
- Outliers (e.g., one user generating 80% of backtest minutes — investigate).

Generator: `infra/scripts/cost-report.sh`. Output: markdown + Slack post.

---

## Phase 4 — when to consider managed services

We move to managed Postgres (Hetzner Cloud, Aiven, Neon) when:

- DB > 50 GB
- DB connections sustained > 70% of max
- DBA-grade ops eating > 2 engineer-hours/week

Estimated cost increase: +$50–150/mo. Worth it once an engineer's hour > $50.
