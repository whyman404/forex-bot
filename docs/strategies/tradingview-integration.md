# TradingView Integration — Architecture & Compliance

**Status:** R4 (Phase 2 round 4 — added 2026-06-16)
**Owner:** Kairos Toki
**Audience:** engineers + ops + compliance.

---

## 1. Why integrate TradingView?

TradingView (TV) computes a multi-indicator "Recommendation" per symbol
per timeframe that is widely respected as a quick consensus signal. The
`atilaahmettaner/tradingview-mcp` project packages this as an MCP server
with 30+ TA tools, 9 backtest strategies, multi-timeframe analysis, and
news sentiment.

For the forex-bot platform, we want TV's recommendation as **a signal
source** that flows into our existing live engine (MT5 bridge → Exness).

---

## 2. Boundary — what we DO and DO NOT do

| Decision                                                     | Choice                                                  | Rationale                                                                 |
| ------------------------------------------------------------ | ------------------------------------------------------- | ------------------------------------------------------------------------- |
| Run `tradingview-mcp` as an MCP server inside our prod stack | **No**                                                  | One more service to deploy, monitor, secure. Unnecessary indirection.     |
| Import its underlying `tradingview-ta` PyPI lib directly     | **Yes**                                                 | Single dependency; sync API matches our threading model.                  |
| Wire TV's MCP backtest engine to our trades                  | **No**                                                  | Upstream MCP is analysis-only. We use OUR backtest framework.             |
| Surface TV recommendations to the user                       | **Yes** (via `/tv/preview` endpoint + Strategy Detail UI) | Transparency — user sees the same signal the bot trades on.               |
| Claim "TV signals are accurate / a buy recommendation"       | **NEVER**                                               | Per upstream disclaimer, TV signals are informational, not advice.        |
| Trade on TV signal if TV is unreachable                      | **No** — halt instead                                   | Per Kairos identity: never trade blindly when the edge source is down.    |

---

## 3. Wiring diagram

```
                                      ┌──────────────────────┐
   TradingView CDN (public)  ◄────────┤ tradingview/client.py│
   scanner.tradingview.com            │  - retry x3          │
                                      │  - TTL cache 60s     │
                                      │  - throttle (4/0.8s) │
                                      └──────────┬───────────┘
                                                 │
                                                 │ TVAnalysis per TF
                                                 ▼
                                      ┌──────────────────────┐
                                      │ tradingview/scorer.py│
                                      │  combined score      │
                                      │  [-100, +100]        │
                                      └──────────┬───────────┘
                                                 │
                                                 ▼
       configs/strategies.yaml        ┌──────────────────────┐
       (tv_signal block)     ────────►│ strategies/tv_signal │
                                      │  Strategy            │
                                      └──────────┬───────────┘
                                                 │ signals(data)
                                                 ▼
                                      ┌──────────────────────┐
                                      │ live/tv_signal_engine│
                                      │  (LiveEngine subclass)│
                                      └──────────┬───────────┘
                                                 │
                                  ┌──────────────┼──────────────┐
                                  ▼              ▼              ▼
                          RiskManager     CircuitBreaker   InternalClient
                          (sizing)        (HALT/KILL)      (HMAC → backend)
                                  │
                                  ▼
                          MT5 bridge (HTTP /order)
                                  │
                                  ▼
                          MT5 terminal → Exness
```

Key invariant: the LAST mile (RiskManager → CircuitBreaker → bridge) is
identical for ALL strategies. TV integration only changes the SIGNAL
SOURCE — never the risk path. This means existing safety guarantees
(daily loss cap, max DD breaker, SL-required) apply equally.

---

## 4. Rate-limit considerations

TradingView does not publish official rate limits. Our defaults:
- 4 concurrent calls
- 0.8s spacing
- 60s cache TTL

At full load (4 tv_signal instances × 3 TFs × 1 bar/15min) we make
~48 calls/hour, well below any reasonable threshold. The cache absorbs
co-location bursts (multiple strategies asking the same (sym, TF) at
once).

If TV starts returning 429 or empty responses, the client's exponential
backoff covers transient errors. Sustained failures → strategy halts.

---

## 5. Failure modes & engine behavior

| Scenario                          | Engine behavior                                       |
| --------------------------------- | ----------------------------------------------------- |
| `tradingview-ta` not installed    | TV-derived strategies halt; non-TV strategies unaffected. |
| `TV_ENABLED=false`                | Same as above.                                        |
| TV returns 429 / network drop     | 3 retries with exponential backoff (0.5s → 1s → 2s).   |
| All retries exhausted             | Per-TF result skipped. If all TFs fail → no signal.   |
| TV returns malformed JSON         | Exception caught; treated as failed call.             |
| TV consistently degraded (≥ 5 min)| Engine emits `halted` health event; ops alerted.      |
| TV recovers after halt            | Engine resumes automatically on next successful call. |

---

## 6. Compliance posture

### What we tell the user (UI gate)

Before a user enables a `tv_signal` instance, they accept:

> The TradingView Signal Follow strategy uses TradingView's public
> technical-analysis recommendation as its primary entry signal.
> **TradingView recommendations are informational and are not
> financial advice.** The platform follows these signals but does
> not warrant their accuracy. You acknowledge that:
>
> 1. Signals can be wrong; losses may occur.
> 2. The strategy may halt without notice if TradingView is unreachable.
> 3. Backtest results are an approximation (see `tv-signal.md` §7).
>
> By enabling this strategy, you accept full responsibility for trades
> placed on your behalf.

This is enforced by the UI gate (same pattern as the existing risk
disclaimer) and the acceptance is logged with the consent version.

### What we do NOT claim

- That TV signals are "accurate" or "professional advice".
- That we have any special relationship with TradingView.
- That backtest performance translates to live performance.
- That the strategy will not lose money.

---

## 7. SBOM additions

The R4 release adds the following dependencies; both must appear in the
generated SBOM for the trading-engine image:

| Package                  | Version  | License                     | Source         |
| ------------------------ | -------- | --------------------------- | -------------- |
| `tradingview-ta`         | >= 3.3.0 | MIT                         | PyPI           |
| `tradingview-mcp-server` | >= 0.7.0 | MIT (per upstream)          | PyPI (optional) |

`tradingview-mcp-server` is in the optional `[tv]` extra and NOT shipped
in the default trading-engine image. It is listed so that operators who
want to run the upstream MCP server alongside (e.g. for ad-hoc TA via
Claude Desktop) can install it with a documented command.

---

## 8. Disabling the integration

To disable TV in prod without a redeploy:
```
TV_ENABLED=false
```

The `tv_signal` strategy halts; all other strategies continue. The UI
should show a banner if `/tv/symbols` returns `tv_enabled=false`.

To uninstall entirely, remove `tradingview-ta` from `pyproject.toml`
dependencies and rebuild — the engine code degrades gracefully
(documented in `tradingview/client.py`).

---

## 9. Operational checklist (R4 → R5)

- [ ] Verify `/tv/preview` returns a non-empty response in staging.
- [ ] Confirm throttle params in `.env` match production network capacity.
- [ ] Walk-forward analysis of the **proxy** strategy in backtest mode
      (validates structure, not TV edge).
- [ ] Paper-trade live for ≥ 30 days (gate enforced).
- [ ] Monitor TV call success rate; alert below 95%.
- [ ] Confirm SBOM includes `tradingview-ta` and `tradingview-mcp-server`.

---

## 10. References

- Upstream: https://github.com/atilaahmettaner/tradingview-mcp
- PyPI: https://pypi.org/project/tradingview-ta/
- Strategy spec: `docs/strategies/tv-signal.md`
- Throttle PR (upstream): tradingview-mcp PR #34
