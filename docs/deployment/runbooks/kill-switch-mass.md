# Runbook — Mass Kill Switch

> Severity: page (highest)
> Owner: on-call DevOps (Hestia) + on-call Quant (Kairos)
> Last updated: 2026-06-15

> When in doubt, **engage the kill switch.** Recovering a halted bot is
> easier than recovering from a runaway one.

## When to use

* `DailyLossLimitHit` fires (single account).
* `MaxDrawdownExceeded` fires.
* Multiple accounts simultaneously losing — possible bug or broker
  malfunction.
* A user reports the bot doing something obviously wrong (e.g. inverted
  signal direction).
* You don't know what's going on but money is being lost in real time.

## Kill switch tiers

| Tier | Scope | Endpoint | Effect |
|------|-------|----------|--------|
| 1 | Single account | `POST /admin/kill-switch?account=<id>` | Reject all new orders for that account. Open positions untouched. |
| 2 | Single strategy | `POST /admin/kill-switch?strategy=<id>` | Disable that strategy globally. |
| 3 | All accounts | `POST /admin/kill-switch?scope=all` | No new orders go anywhere. Trading engine still computes signals but they are not routed. |
| 4 | Hard stop | `docker compose stop trading-engine` | Engine offline. No signals generated at all. |
| 5 | MT5 supervisor offline | `nssm stop MT5Supervisor` on Windows VPS | Even if engine emits orders, they cannot reach the broker. |

Use the lowest tier that addresses the symptom.

## How to invoke

### Through the ops dashboard (preferred)

`https://app.forex-bot.app/ops/kill-switch` — select scope, click,
confirm with TOTP. Requires the `ops` role.

### Through curl (fallback if dashboard is broken)

```bash
TOKEN=$(... your ops token ...)
curl -fsS -X POST -H "Authorization: Bearer $TOKEN" \
  "https://api.forex-bot.app/admin/kill-switch?scope=all"
```

### Through Postgres direct (last resort)

```bash
docker compose exec postgres psql -U forex forex_bot \
  -c "UPDATE feature_flags SET enabled=false WHERE name='live_trading';"
```

Backend re-reads the flag every 5 s; effect within 5–10 s.

## Confirm the kill switch is active

1. Grafana: `Forex Bot — Trading → orders_routed_total` should drop to
   zero rate.
2. Backend logs: `kill_switch_engaged` event count > 0.
3. UI: "Live trading paused" banner visible in dashboards.
4. Test by sending a simulated signal in staging-like account — should
   be rejected with `kill_switch_engaged`.

## What about open positions?

The kill switch does **not** close positions. That is intentional —
auto-closing a basket during a tilted moment can lock in losses worse
than holding.

If you need to close positions:

1. On Windows VPS via MT5 GUI, close manually (small number of
   positions).
2. Or call `POST /admin/positions/close-all?account=<id>` — emits
   correctly-tagged orders that the supervisor routes as `close`
   intents. Confirms via MT5 fills.

## Recovery

1. Mitigate the root cause.
2. Verify in staging that the original symptom does not reproduce.
3. Open `POST /admin/kill-switch?scope=clear` (same tiered scopes).
4. Watch the first 10 minutes carefully — order rate, error rate,
   account PnL.
5. Document the incident, root cause, and the test that now catches it
   in CI.

## Communications

* Discord ops channel: announce when engaging and when clearing.
* All affected users: email within 15 minutes if their bot is paused
  (template at `dev-team/05-devops-hestia-kaoru/skills/comms-templates.md`).
* Status page: update at engage + clear time, with cause and ETA.

## Postmortem

For every mass kill switch event, postmortem is mandatory within 48h.
Include:

* Trigger (which alert fired, which account thresholds breached).
* Decision timeline (who engaged the switch, when, why).
* Total dollar PnL impact (recovered after the fact).
* Time to mitigate (kill switch engage), time to recover (clear), time
  to user comms.
* What allowed the underlying bug to ship; what changes prevent it next
  time.
