# CI / CD — pipelines for forex-bot

Owner: Hestia Kaoru

The actual workflows live in `.github/workflows/`. This directory holds
shared scripts and references invoked from those workflows.

| Workflow file | Trigger | Purpose |
|---------------|---------|---------|
| `ci.yml` | push, PR | lint, typecheck, test, build, scan, SAST |
| `deploy-staging.yml` | after `ci` on main | rolling deploy + smoke test |
| `deploy-prod.yml` | tag `release/*` or manual | rolling deploy + smoke test + auto rollback |
| `migrate.yml` | manual only | alembic against staging or prod |

## Required secrets

Set in repo (or org) settings → Secrets → Actions:

| Secret | Used by | Example |
|--------|---------|---------|
| `STAGING_HOST` | staging deploy | `staging.forex-bot.app` |
| `PROD_HOST` | prod deploy + migrate | `app.forex-bot.app` |
| `STAGING_SSH_KEY` | staging deploy + migrate | ed25519 private key |
| `PROD_SSH_KEY` | prod deploy + migrate | ed25519 private key |
| `GHCR_PAT` | image pulls on hosts | classic PAT, `read:packages` |
| `DISCORD_WEBHOOK` | notifications | https://discord.com/api/webhooks/... |

## Environments

* `staging` — auto-deploy after CI.
* `production` — manual approval required (Repo → Settings →
  Environments → production → Required reviewers).

## Local CI dry run

```bash
# pip install nektos act
act -j python-test -W .github/workflows/ci.yml --container-architecture linux/amd64
```

## Why this shape

* Single `ci.yml` with matrix instead of one workflow per service — less
  duplication, easier to keep in sync.
* Deploy via SSH+compose, not a fancy GitOps tool, because the project
  has 1 host in Phase 1. We will swap for ArgoCD or Flux when we move
  to Kubernetes in Phase 3 (if ever).
* Auto-rollback only triggers on smoke-test failure, not on flaky logs.
* No "deploy on merge to main" for prod — too easy to deploy on a Friday
  by accident. Tag-based or manual only.
