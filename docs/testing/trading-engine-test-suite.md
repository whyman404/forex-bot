# Trading Engine Test Suite — pytest

**Owner:** Themis Saori + Kairos Toki
**Updated:** 2026-06-14

---

## Layout

```
trading-engine/tests/
├── conftest.py
├── fixtures/
│   ├── ohlcv/                  # canned CSV/parquet bars per strategy
│   │   ├── xauusd_5m_known_breakout_day.parquet
│   │   ├── xauusd_5m_flat_day.parquet
│   │   ├── btc_15m_trend_day.parquet
│   │   └── ... (see below)
│   └── strategies/
├── strategies/
│   ├── test_london_breakout.py
│   ├── test_ny_killzone.py
│   ├── test_ema_adx.py
│   ├── test_mean_reversion.py
│   ├── test_grid_btc.py
│   └── test_trend_follow.py
├── risk/
│   └── test_risk_manager.py
├── broker/
│   ├── test_mt5_adapter.py
│   ├── test_binance_adapter.py
│   └── test_paper_adapter.py
└── oms/
    └── test_order_lifecycle.py
```

---

## 1. Strategies — `test_*.py`

Pattern for every strategy:

```python
@pytest.mark.parametrize("fixture,expected_signal", [
    ("xauusd_5m_known_breakout_day", {"side": "BUY", "must_signal": True}),
    ("xauusd_5m_flat_day", {"must_signal": False}),
    ("xauusd_5m_false_breakout", {"must_signal": False}),  # filter rejects
    ("xauusd_5m_dst_boundary", {"side": "BUY", "must_signal": True}),
    ("xauusd_5m_news_spike", {"must_signal": False}),  # news filter
])
def test_signal_emission(strategy, fixture, expected_signal):
    bars = load_fixture(fixture)
    signals = list(strategy.signals(bars))
    if expected_signal["must_signal"]:
        assert len(signals) >= 1
        assert signals[0].side == expected_signal["side"]
        assert signals[0].sl is not None
        assert signals[0].tp is not None
    else:
        assert signals == []
```

Per-strategy specific assertions:

### London Breakout (LB)
- LB-01..LB-07 per `backtest-validation.md` §2.1
- Asian range must include only 00:00–07:00 UTC bars (boundary test)
- Signal time must be within 07:00–10:00 UTC
- SL distance ≤ 1.5 × Asian range
- RR ≥ 1:1.5 enforced

### NY Killzone
- Active window 13:00–16:00 UTC
- DST-aware (NY local 09:30–12:00)
- BUY breaks NY-pre range high; SELL breaks NY-pre range low

### EMA + ADX
- BUY when EMA-fast crosses above EMA-slow AND ADX > 25
- ADX threshold parameterized; test 0 / 25 / 100 boundaries
- No signal when ADX < threshold

### Mean Reversion
- Reverts when price hits Bollinger ±2σ AND RSI < 30 (buy) or > 70 (sell)
- Stops out beyond ±3σ

### Grid (BTC)
- Places ladder of orders within range
- **MUST have hard SL outside range** (user-facing protection — addresses README §95% myth)
- Test: grid without SL config → strategy refuses to start (raises)

### Trend Follow
- Donchian breakout 20-bar; trailing SL ATR-based
- Trailing SL never widens (monotone)

---

## 2. RiskManager — `test_risk_manager.py`

| # | Test | Expected |
|---|---|---|
| RM-01 | Position size for $10k equity, 1% risk, 50-pip SL on XAUUSD | 0.04 lot (rounded down to 0.01 step) |
| RM-02 | Position size respects broker min lot 0.01 — if rounded to 0 → returns 0 + log warning | 0 lot, warn |
| RM-03 | Position size respects broker max lot 50 | min(calc, 50) |
| RM-04 | Daily loss limit hit (cumulative loss ≥ 2% equity since 00:00 UTC) | new orders rejected, `RiskBreach.DAILY_LIMIT` raised |
| RM-05 | DD circuit breaker (peak equity vs current ≥ 20%) | all running strategies stopped, kill switch flag set |
| RM-06 | DD breaker resets only on operator action, not on equity recovery | still tripped after recovery |
| RM-07 | Leverage cap: order that would push leverage > 1:30 → rejected | rejected |
| RM-08 | Concurrent orders cap per strategy = 1 (configurable) → 2nd rejected | rejected |
| RM-09 | Position sizing is deterministic (no float drift across runs) | identical |
| RM-10 | Daily reset happens at user-configured timezone, default UTC | boundary test |

Property-based test (hypothesis): for any `equity ∈ [100, 1_000_000]`, `risk_pct ∈ (0, 0.05]`, `sl_pips ∈ [1, 500]` → `lot ≥ 0` and `lot * pip_value * sl_pips ≤ risk_pct * equity * (1 + 1e-9)`.

---

## 3. Broker adapter (MT5 mocked) — `test_mt5_adapter.py`

| # | Test | Expected |
|---|---|---|
| MT5-01 | Connect with good creds (mock) | adapter.connected = True within 5s |
| MT5-02 | Connect bad creds | raises BrokerAuthError, credentials never serialized in exception |
| MT5-03 | place_order BUY 0.1 XAUUSD market | mock receives correct symbol, side, volume; returns deal_id; trade row written |
| MT5-04 | place_order SELL 0.05 — direction not flipped, size not corrupted | exact match |
| MT5-05 | place_order with SL+TP | broker request includes both |
| MT5-06 | place_order partial fill (mock fills 0.06 of 0.1) | trade record has filled_volume=0.06, remaining=0.04, status=partial |
| MT5-07 | Disconnect mid-trade → adapter reconnects within retry policy (3 attempts, exp backoff) | reconnected, no orphan order |
| MT5-08 | Disconnect with order in flight → reconciliation on reconnect pulls order state from broker | order state synced |
| MT5-09 | Network 5s timeout → not silently retried (would risk double-order) | TimeoutError raised; OMS decides |
| MT5-10 | Idempotency: place_order with same client_order_id twice → second is no-op | broker called once |
| MT5-11 | Symbol not subscribed → adapter subscribes + retries once | success on 2nd |
| MT5-12 | Market closed (weekend, mock) | raises MarketClosed, OMS records reason |

---

## 4. Paper adapter — `test_paper_adapter.py`

| # | Test | Expected |
|---|---|---|
| PA-01 | Buy at bar close + 2 pip slippage | fill price = close + 0.2 (XAUUSD) |
| PA-02 | Spread + commission deducted | net_pnl computed correctly |
| PA-03 | SL triggered when bar low ≤ SL | trade closed at SL price (configurable slip on SL hit) |
| PA-04 | TP triggered when bar high ≥ TP | trade closed at TP |
| PA-05 | Gap through SL (open beyond SL) | filled at open (worse than SL) — realistic |
| PA-06 | Equity curve = initial + Σ realized + open MtM | matches |
| PA-07 | No future leak: order placed at bar t fills at t+1 open (configurable) | bar t price never used for fill |

---

## 5. OMS — `test_order_lifecycle.py`

| # | Test | Expected |
|---|---|---|
| OMS-01 | Signal → order placed → fill → trade record | full chain in DB |
| OMS-02 | Engine crash between signal and order — restart resumes from `pending_orders` table, no duplicate | one order |
| OMS-03 | Engine crash between order and fill — broker is source of truth on restart | reconciled |
| OMS-04 | Order with risk breach → not placed | risk_rejected event |
| OMS-05 | Kill switch event arrives mid-cycle → no new orders, in-flight respected per policy (cancel or let-fill, configurable) | per config |
| OMS-06 | Trade events idempotent (broker may resend) | dedupe by deal_id |

---

## 6. Coverage + mutation gates

- Coverage line ≥ 80% on `trading-engine/strategies/`, `trading-engine/risk/`, `trading-engine/broker/`, `trading-engine/oms/`.
- Mutation score ≥ 70% on `trading-engine/risk/` and `trading-engine/strategies/` (run quarterly via mutmut).
- Property tests with hypothesis on risk math and OHLCV invariants.
