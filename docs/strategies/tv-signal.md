# TradingView Signal Follow — Strategy Spec

**Strategy code:** `tv_signal`
**Asset class:** multi (forex / gold / crypto)
**Risk rating:** medium
**Default TFs:** 15m + 1h + 4h
**Owner:** Kairos Toki
**Status:** R4 — initial implementation, paper-only until walk-forward of proxy passes.

---

## 1. What it does

This strategy subscribes to TradingView's public technical-analysis
recommendation (via the `tradingview-ta` PyPI library) across multiple
timeframes for one instrument. At each bar close it:

1. Fetches `Recommendation` (STRONG_BUY .. STRONG_SELL) per timeframe.
2. Combines them into a single signed score in `[-100, +100]` via
   `tradingview/scorer.py` (higher timeframes weighted higher).
3. Computes the % of timeframes that agree on direction.
4. Enters long when `score >= +entry_threshold` AND
   `agreement_pct >= min_agreement_pct`.
5. Enters short when `score <= -entry_threshold` AND
   `agreement_pct >= min_agreement_pct`.
6. SL/TP from ATR on the trading timeframe.
7. Enforces a cool-down (default 60 minutes) between exits and re-entries
   so we don't whipsaw across consecutive bars.

It is a **signal follower**, not an oracle. All trades still pass through
the platform's `RiskManager`, `CircuitBreaker`, and the MT5 bridge's
safety layer.

---

## 2. Parameters

| Param                    | Default          | Notes                                                                          |
| ------------------------ | ---------------- | ------------------------------------------------------------------------------ |
| `intervals`              | `["15m","1h","4h"]` | TV intervals to query — list of strings. Add `1d` for higher-conviction setups. |
| `entry_score_threshold`  | `60`             | Score above which entry is considered. Tune up (e.g. 75) for stricter entries.  |
| `exit_score_threshold`   | `20`             | Score below which exit is considered (looser than entry by design).             |
| `min_agreement_pct`      | `0.6`            | Fraction of TFs that must agree on direction.                                  |
| `sl_atr_mult`            | `1.5`            | SL distance = ATR × this. Wider in volatile regimes.                            |
| `tp_atr_mult`            | `3.0`            | TP distance = ATR × this. RR = 2 by default.                                   |
| `atr_period`             | `14`             | ATR look-back on the trading timeframe.                                        |
| `cool_down_min`          | `60`             | Minutes between a position close and the next allowed entry.                   |
| `tv_symbol` / `tv_exchange` | auto          | Optional override. Default resolved by `tradingview/symbols.py`.                |
| `tv_screener`            | `forex`          | TV screener — `forex` or `crypto`. Auto from asset class.                       |

---

## 3. Mechanics — multi-TF score

We weight each timeframe roughly proportional to "data-half-life":

| TF   | Weight |
| ---- | ------ |
| 1m   | 0.2    |
| 5m   | 0.4    |
| 15m  | 0.6    |
| 1h   | 1.0    |
| 4h   | 1.5    |
| 1d   | 2.0    |
| 1w   | 2.5    |

`score = Σ(rec_score × weight) / Σ(weight)`

`rec_score`:
- STRONG_BUY = +100, BUY = +50, NEUTRAL = 0, SELL = -50, STRONG_SELL = -100.

`agreement_pct` = max(bullish_count, bearish_count, neutral_count) / total_tfs.

`confidence` = agreement × |score| / 100 (both must be high to call it "high confidence").

---

## 4. Required permissions

- **Network egress** from the engine container/host to TradingView CDN
  (TLS over 443 to scanner.tradingview.com and similar). No API key,
  no auth — this is public data, but rate-limited per IP.
- **No additional broker permissions** — TV is read-only.

---

## 5. Risk warnings (REQUIRED user disclosure)

Per the upstream `tradingview-mcp` disclaimer (`atilaahmettaner/tradingview-mcp`):

> TradingView's recommendations are informational. They are NOT
> financial advice and should not be relied upon as the sole input
> to a trading decision.

We surface this in the UI before enabling any `tv_signal` instance. The
user explicitly accepts:

1. TradingView signals are NOT financial advice.
2. The platform does not vouch for TV's accuracy — it merely follows them.
3. The strategy halts (does NOT trade blindly) when TV is unreachable.
4. **Backtest is an approximation** — see §7 below.

---

## 6. Recommended pairs

| Internal | TV symbol | Exchange | Notes                                              |
| -------- | --------- | -------- | -------------------------------------------------- |
| XAUUSD   | XAUUSD    | OANDA    | Best-tested. Strong intraday news sensitivity.     |
| BTCUSDT  | BTCUSDT   | BINANCE  | Deepest crypto feed. 24/7 trading.                 |
| EURUSD   | EURUSD    | OANDA    | Tight spreads, generally trending.                 |
| GBPUSD   | GBPUSD    | OANDA    | Higher vol; consider wider SL ATR mult.            |

Full list in `tradingview/symbols.py`.

---

## 7. Backtest caveat (READ THIS)

`tradingview-ta` returns **LIVE** recommendations only — there is no
public TV API for historical replay of the Recommendation. Therefore:

- **Live mode** queries TV at each bar close (real signals).
- **Backtest mode** uses a **PROXY**: a local blend of RSI + EMA cross
  computed on the historical OHLCV. This is documented in
  `strategies/tv_signal.py::TVSignalStrategy.describe()`.

Implications:
- Backtest numbers are **directional only**. Live PF/Sharpe will differ.
- Walk-forward analysis on the proxy validates the STRUCTURE of the
  strategy (entry/exit/risk logic), not the actual TV edge.
- Recommended rollout: paper-trade live for ≥ 30 days before
  promoting to real capital. The gate (`live/gate.py`) enforces this.

This caveat is non-negotiable. Per Kairos's identity: realistic backtest
is compulsory.

---

## 8. Tuning knobs (quick guide)

- **More selective entries** → raise `entry_score_threshold` (60 → 75) +
  `min_agreement_pct` (0.6 → 0.75).
- **More trades** → add lower TFs to `intervals` (`["5m","15m","1h"]`)
  and lower threshold (50). Expect more whipsaw.
- **Trend-only regime** → use `intervals=["1h","4h","1d"]` and require
  100% agreement. Fewer trades, higher conviction.
- **Tighter risk** → reduce `sl_atr_mult` to 1.0 (more stop-outs but
  smaller per-trade loss).
- **Volatile asset (e.g. crypto)** → widen SL to 2.0+ and lengthen
  cool-down (120 min) to avoid re-entering chop.

Do NOT optimize these on in-sample data. Pick from convention; validate
with walk-forward (`cli/walk_forward.py`).

---

## 9. Failure modes

| Failure                                     | Engine response                                |
| ------------------------------------------- | ---------------------------------------------- |
| `tradingview-ta` not installed              | Strategy halts; logs `tv_module_missing`.       |
| `TV_ENABLED=false`                          | Strategy halts; logs `disabled_by_env`.         |
| TV API unreachable (network)                | Per-TF call retries 3x, then partial result.   |
| All TFs fail in one cycle                   | No signal that bar (logged).                   |
| TV returns garbage / parse error            | Caught in client; logged; treated as failure.  |

The strategy NEVER trades on a stale or partial signal silently. If TV
is degraded, the engine emits a `halted` health event and waits.

---

## 10. References

- Upstream repo: `atilaahmettaner/tradingview-mcp` (analysis-only MCP server).
- PyPI library: `tradingview-ta` (synchronous).
- Throttle params mirror upstream PR #34 (concurrency + spacing).
- Architecture doc: `docs/strategies/tradingview-integration.md`.

---

## 11. Tests

`trading-engine/tests/test_tv_signal.py` covers:
- Symbol resolution (XAUUSD → OANDA, BTCUSDT → BINANCE, fallback)
- Scorer math (extremes, mixed, empty, weighted)
- Strategy live mode (long, short, agreement rejection, cool-down, fetch failure)
- Strategy backtest proxy mode (no TV client)
- Worker registry registration

All tests are offline (mocked TV); CI never hits TradingView.
