# Live Trading Runbook

> What to do before, during, and after enabling live mode on a real Exness account.
> Owner: Kairos Toki (trading-engine). Reviewed by: Atlas (backend), Argus (ops).

This runbook assumes the **MT5 bridge** is already installed on a Windows
host — see `mt5-bridge-setup.md` if it isn't.

---

## Pre-live checklist

Run through every item. Skipping any = automatic NO-GO.

### Strategy fitness

- [ ] Backtest on **≥ 3 years** of data with realistic spread/commission/slippage.
- [ ] Profit factor **> 1.3**, max drawdown **< 25%**, total trades **≥ 30**.
- [ ] Walk-forward: `python -m cli.walk_forward` rollup shows `verdict_hint=stable`
      (`stability_ratio < 0.4`).
- [ ] Paper-traded for **≥ 14 days** with **≥ 10 trades** and Sharpe **≥ 0.5**.
- [ ] `GET /live/{id}/gate` returns `approved=true`.

### Risk caps

- [ ] `risk_per_trade_pct` ∈ (0.1, 2.0] — default 1.0% for first live week.
- [ ] `max_drawdown_pct` ∈ (5, 20] — default 15%.
- [ ] `daily_loss_pct` ∈ (1, 10] — default 5%.
- [ ] `BRIDGE_MAX_LOT` on the Windows host **caps** the first trade size
      (recommend `0.05` for the first session, then ratchet up).

### Plumbing

- [ ] MT5 terminal running and logged in on the Windows host.
- [ ] `curl -H "Authorization: Bearer $BRIDGE_TOKEN" http://<bridge>:8500/healthz`
      returns `mt5_connected=true`.
- [ ] Trading-engine env has `MT5_BRIDGE_URL`, `MT5_BRIDGE_TOKEN`,
      `INTERNAL_API_SECRET` set.
- [ ] Backend has the **same** `INTERNAL_API_SECRET` (HMAC verify will fail
      silently otherwise — symptom: no signals show up in DB).
- [ ] PagerDuty / Discord webhook configured for `KILL` and `HALT` events.

---

## First trade procedure

1. Open the Atlas dashboard. Pick the validated `strategy_instance`.
2. Confirm `params.risk_per_trade_pct = 0.5%` (half of normal) and
   `BRIDGE_MAX_LOT=0.05`.
3. POST `/live/start` with the spec. Watch the response — must be
   `{"ok": true, "status": "running"}`.
4. Tail the bridge logs and the engine logs in two terminals:
   ```
   # On Windows host
   Get-Content .\logs\bridge.err.log -Tail 50 -Wait

   # On backend host
   docker logs -f trading-engine
   ```
5. Wait for the first signal. When the order fills, **manually verify
   in MT5 terminal**: open MT5 → Trade tab → confirm ticket + lot + SL/TP
   match what the engine sent.
6. Let it run **at least 24 hours** at half-risk before scaling.
7. After 24h with no anomalies (no `HALT`, no missed fills, no SL not set),
   lift `risk_per_trade_pct` back to 1.0% and remove the
   `BRIDGE_MAX_LOT=0.05` cap (back to the configured default).

---

## Emergency stop

| What's wrong                          | What to do                                                                                                |
| ------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| Strategy is clearly losing            | `POST /live/stop` — engine stops opening NEW positions; existing positions stay.                          |
| Strategy is losing AND has open pos.  | `POST /live/kill` — engine closes all positions with our magic via `mt5-bridge /position/close`, then stops. |
| Bridge unreachable                    | Engine auto-HALTs after 5 min disconnect. If bridge is down longer, **log into MT5 directly** and close.    |
| Wrong account                         | `POST /live/kill` immediately. Verify in MT5 terminal that no positions remain with our magic.            |
| Suspected token compromise            | On Windows host: rotate `BRIDGE_TOKEN`; on backend: rotate `MT5_BRIDGE_TOKEN`; restart both.                |

### Manual close (bridge down)

If the bridge is unreachable but positions are open:

1. Log into the **same MT5 terminal** the bridge uses (UI, not API).
2. Right-click the position → Close Position.
3. **Do NOT** restart the bridge until you've verified positions are flat —
   the engine may reopen on next bar if the strategy still signals.

---

## Common issues

| Symptom                                  | Likely cause                       | Fix                                                                                              |
| ---------------------------------------- | ---------------------------------- | ------------------------------------------------------------------------------------------------ |
| `/live/start` returns 400 "no SL"        | Strategy emitted `sl=0`            | Check strategy params; many strategies need `sl_pips` set.                                       |
| `/live/start` returns `lot exceeds MAX_LOT` | `BRIDGE_MAX_LOT` < computed size  | Lower `risk_per_trade_pct` OR raise `BRIDGE_MAX_LOT` (with care).                                |
| Engine status `halted` with reason `daily_loss_pct` | Hit daily loss cap          | Wait for UTC midnight; breaker auto-resets `start_of_day_equity`. Investigate why losses landed.  |
| Engine status `killed` with reason `max_drawdown` | DD circuit tripped           | **Investigate first.** Manual reset by stopping and re-starting after RCA. Do not auto-resume.    |
| Engine status `halted` with reason `slippage_anomaly` | Spread spike (news event)   | Wait for spread to normalize; check `/quote/{symbol}` ask-bid. Adjust `slippage_alarm_x` if false positive. |
| `/live/{id}/gate` returns `approved=false` even though backtest is fine | Missing paper data | Run paper trading for the required 14 days first.                                                |
| No fills logged in DB                    | HMAC mismatch on `/internal/trades` | Confirm `INTERNAL_API_SECRET` matches on both sides; check engine logs for `internal.post_rejected`. |

---

## Daily ops cadence

| Time (UTC) | Action                                                                                              |
| ---------- | --------------------------------------------------------------------------------------------------- |
| 00:00      | Daily roll — breaker resets `realized_pnl_today` and `start_of_day_equity`. Nothing to do.          |
| 06:00      | Spot-check `/live` — every engine should be `running` or paused (intended).                         |
| 21:00      | Check the day's signals + fills in Atlas dashboard.                                                 |
| Sundays    | `python -m cli.retro --strategy-instance <id> --window-days 7` — quick weekly retro for each live strategy. |
| Monthly    | `python -m cli.retro --window-days 30` — full retro; commit the report to git.                       |

---

## Promotion / demotion flow

```
[backtest]  ──>  [walk-forward]  ──>  [paper ≥ 14d]  ──>  [gate]  ──>  [live (1/2 risk)]  ──>  [live (full risk)]
                                                                                    │
                                                                                    └──>  [retro 30d]
                                                                                              │
                                                                                              ├──> KEEP
                                                                                              ├──> ADJUST  (lower risk, rerun walk-forward)
                                                                                              └──> KILL    (back to paper)
```

Demotion is **never** reversible to live in fewer than 14 paper days.

---

## Contact

- Trading engine bugs → Kairos Toki (`/dev-team/09-quant-kairos-toki/`)
- API contract questions → see `backtest-api.md`
- Bridge / Windows host issues → see `mt5-bridge-setup.md`
- Ops alerts / on-call → Argus
