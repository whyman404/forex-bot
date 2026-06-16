# Backtest Validation Plan

**Owner:** Themis Saori + Kairos Toki
**Updated:** 2026-06-14
**Why this exists:** A dishonest backtest is the most expensive defect we can ship. Users will fund accounts based on what backtest shows. If the backtest leaks future data, ignores slippage, or excludes losers, we are selling a fantasy. This document defines the checks the backtest engine **must** pass before each release.

---

## 1. Required properties (must hold for every strategy)

| # | Property | What it means | How we test |
|---|---|---|---|
| R1 | **Reproducibility** | Same input data + same code + same seed → byte-identical results | Run backtest twice, diff result frames |
| R2 | **No look-ahead** | Decision at bar t uses only data ≤ t (including indicator warmup) | Inject future-data anomaly at t+1; result must NOT improve |
| R3 | **No survivorship bias** | Universe of instruments includes delisted / withdrawn pairs for the test period | Compare universe size vs symbol master at period start |
| R4 | **Realistic slippage** | Each fill has a slippage model (fixed bps + adverse selection on volatility) applied | Snapshot fills, assert price ≠ bar's open/close by ≥ slippage |
| R5 | **Realistic fees** | Spread + commission deducted from PnL on every trade | Assert net_pnl = gross_pnl − fees_total per trade |
| R6 | **No leakage via parameters** | Strategy parameters do not encode the test set (over-fit telltale) | Walk-forward validation report |
| R7 | **Timezone correctness** | All bars stamped in UTC; session filters (London / NY) computed from UTC + DST-aware tz | Test cases on DST boundary (Mar / Nov) |
| R8 | **Order semantics match live** | Backtest order types (market/limit/stop/SL/TP) behave like broker adapter | Cross-check via canned scenarios |
| R9 | **Partial fill handling** | A partial fill in backtest reduces position size; remainder either fills or cancels by rule | Inject partial-fill scenario |
| R10 | **Corporate action / gap** | Weekend gap, news gap respected; positions not silently teleported through gap | Gap fixture asserts |

---

## 2. Test cases per strategy

### 2.1 Gold London Breakout

Strategies signal in the London session (07:00–10:00 UTC) when price breaks the Asian range high/low.

| Case | Fixture | Expected |
|---|---|---|
| LB-01 | Clear breakout day: Asian range 1800–1810, London opens 1810.50, prints 1812 | **BUY** signal at 1810 (or breakout candle close), SL at Asian low − buffer |
| LB-02 | Flat day: range 1805–1808, London chops 1806–1809 (no break) | **No signal** |
| LB-03 | False breakout: prints 1810.5 then closes 1808 | **No signal** (filter requires close > range high), or signal that hits SL — both acceptable, must NOT both happen |
| LB-04 | Breakout outside London hours (Asian session) | **No signal** (session filter) |
| LB-05 | DST boundary day (March): London 07:00 UTC = 08:00 BST | Session filter still aligns with London local 08:00 |
| LB-06 | News spike day (NFP candle inside London) | News filter (if enabled) blocks signal |
| LB-07 | Look-ahead injection: artificially boost bar t+1 high by 50 pips | Result must NOT change — if it does, look-ahead is leaking |

### 2.2 NY Killzone, EMA+ADX, Mean Reversion, Grid (BTC), Trend Follow — same template

Each strategy has a sheet under `docs/strategies/<name>/test-fixtures.md` (Kairos owns) with at least: 1 known-positive, 1 known-negative, 1 false-positive, 1 edge.

---

## 3. Reproducibility test (R1)

```python
def test_backtest_reproducible(strategy, fixture_data):
    result_a = run_backtest(strategy, fixture_data, seed=42)
    result_b = run_backtest(strategy, fixture_data, seed=42)
    pd.testing.assert_frame_equal(result_a.trades, result_b.trades)
    assert result_a.metrics == result_b.metrics
```

Run on every PR that touches `trading-engine/backtest/` or `trading-engine/strategies/`.

---

## 4. Look-ahead test (R2) — the most important check

For each strategy:

1. Run baseline backtest → record metrics (PF, Sharpe, total return).
2. Mutate the input data: for each future bar relative to a decision bar, boost the high by N%.
3. Re-run backtest.
4. **Assertion:** `metrics_mutated ≈ metrics_baseline` (within ±1% Sharpe, ±2% return).

If the mutated run is significantly better, the strategy is reading the future. Fail loudly.

```python
def test_no_look_ahead(strategy, fixture_data):
    baseline = run_backtest(strategy, fixture_data, seed=42)
    poisoned = inject_future_high_boost(fixture_data, pct=0.02)
    mutated = run_backtest(strategy, poisoned, seed=42)
    assert abs(mutated.sharpe - baseline.sharpe) < 0.05, \
        "Backtest appears to use future data; look-ahead detected"
```

---

## 5. Survivorship bias check (R3)

Crypto: universe must include pairs delisted from Binance during test period. We pull historical symbol master from CCXT, snapshot per quarter, and assert universe contains symbols that are now delisted.

Gold: single-instrument so N/A.

---

## 6. Slippage realism (R4)

- Min slippage model: fixed 2 pips on Gold, 5 bps on BTC.
- Volatility-aware: in top decile ATR bars, double slippage.
- Assertion: every fill price differs from bar OHLC reference by ≥ slippage; on aggressive entries, fill is the adverse side.

```python
def test_slippage_applied(filled_trades):
    for t in filled_trades:
        if t.side == "BUY":
            assert t.fill_price >= t.signal_price + slippage(t)
        else:
            assert t.fill_price <= t.signal_price - slippage(t)
```

---

## 7. Walk-forward validation (R6)

- Split history into 6 segments.
- Optimize params on segments 1–3, test on 4. Roll forward.
- Report: in-sample vs out-of-sample Sharpe ratio per fold.
- Flag: out-of-sample Sharpe < 50% of in-sample → over-fit warning.

---

## 8. Honest reporting required

Every backtest report **must** show:
- Profit Factor, Sharpe, Sortino, Max DD, calmar
- Total trades, win rate, avg win, avg loss, avg RR
- Fees + slippage as % of gross PnL
- Walk-forward fold table
- Universe size vs symbol-master start size
- Data source + version hash
- Code commit hash
- Seed used

A "great" backtest with PF 3.0 and 95% win rate but no slippage row and 50 trades is **not shippable**.

---

## 9. CI integration

- On every PR touching `trading-engine/`, run: reproducibility + look-ahead + slippage tests on the 6 canonical fixtures (fast, < 60s).
- Nightly: full walk-forward on each strategy, post diff vs last green.
- Quarterly: human review of full backtest reports before publishing to users.

---

## 10. Acceptance gate to publish a strategy result to users

A strategy report can be shown to users in the dashboard only if:
1. All R1–R10 pass.
2. Walk-forward out-of-sample Sharpe ≥ 0.5 of in-sample.
3. PF > 1.5, Max DD ≤ 20%, Sharpe > 1.0, positive expectancy (project gates per README).
4. Report includes the honest-reporting fields above.
5. QA + Kairos + Hephaestus signoff recorded in `docs/strategies/<name>/signoff.md`.

If any fail → report stays internal, strategy not listed for users.
