# `tv_signal` strategy — data model

> Schema impact + retention implications of the TradingView-driven
> ``tv_signal`` strategy (migration 0005, 2026-06-16).
>
> **Author:** Mnemosyne Rin
> **Reviewed with:** Kairos Toki (Quant), Atlas Goro (Backend), Argus Hayato (Privacy)

---

## 1. Why this strategy is special

Unlike the other six catalog strategies, ``tv_signal`` derives its decisions
from an **external service** (TradingView, via the ``tradingview-ta`` library).
This has three database-visible consequences:

1. The catalog row needs a flag the application can read to gate
   enablement (``strategies.requires_external_service``).
2. Per-instance audit needs to remember which external provider supplied
   the signal (``strategy_instances.external_signal_provider``).
3. Generated ``signals`` rows carry a TV-specific reason payload that
   contains the ticker + multi-timeframe recommendation breakdown. These
   are **not PII** but ARE user-attributable (via
   ``strategy_instances.user_id``), so GDPR export must include them.

---

## 2. ``default_params`` JSONB shape

Stored in ``strategies.default_params`` for ``code = 'tv_signal'``.

```json
{
  "symbols": [],
  "intervals": ["1h", "4h", "1d"],
  "long_threshold": 0.5,
  "short_threshold": -0.5,
  "atr_period": 14,
  "sl_atr_mult": 1.5,
  "tp_atr_mult": 3.0,
  "cool_down_min": 60,
  "risk_per_trade_pct": 1.0,
  "max_trades_per_day": 6,
  "spread_filter_pts": 30,
  "enabled": true
}
```

### Field semantics

| Key                   | Type            | Meaning |
|-----------------------|-----------------|---------|
| ``symbols``           | ``string[]``    | Subset of ``tradingview.symbols.SUPPORTED_SYMBOLS`` keys this instance may follow. Empty = ALL supported. |
| ``intervals``         | ``string[]``    | TV intervals to query and combine. Allowed by ``tradingview.client``: ``1m``, ``5m``, ``15m``, ``1h``, ``4h``, ``1d``, ``1W``. |
| ``long_threshold``    | ``float``       | Combined score (range ``[-1.0, +1.0]``) at-or-above which a LONG signal fires. |
| ``short_threshold``   | ``float``       | Combined score at-or-below which a SHORT signal fires. Must be ``< long_threshold``. |
| ``atr_period``        | ``int``         | Periods for ATR calculation used by SL/TP sizing. |
| ``sl_atr_mult``       | ``float``       | Stop-loss distance in ATR multiples. |
| ``tp_atr_mult``       | ``float``       | Take-profit distance in ATR multiples. |
| ``cool_down_min``     | ``int``         | Minutes between consecutive signals for the same symbol. Damps whipsaw around threshold boundaries. |
| ``risk_per_trade_pct``| ``float``       | Account-equity % risked per trade. |
| ``max_trades_per_day``| ``int``         | Cap across ALL symbols this instance follows. |
| ``spread_filter_pts`` | ``int``         | Reject when spread > N points (forex/gold only; ignored for crypto symbols). |
| ``enabled``           | ``bool``        | Soft kill — when ``false`` the worker still loops but never emits a signal. |

### Validation contract

Atlas's API layer is the authoritative validator (Pydantic schema), but
the DB also enforces:

- ``default_params`` is ``NOT NULL`` and ``jsonb`` (already in 0001).
- ``risk_percent`` on ``strategy_instances`` is bounded ``[0, 10]`` (0001).
- The JSON keys above are **not** enforced at the DB layer — schema
  drift between Kairos's engine and Atlas's validator is caught by
  integration tests in CI.

---

## 3. ``strategies.requires_external_service``

Added by migration 0005. ``BOOLEAN NOT NULL DEFAULT FALSE``.

**Semantics:**
- ``TRUE`` → enabling/starting an instance of this strategy requires the
  external service to be reachable + the user to have accepted the
  external-service disclosure (see UI gate in ``tradingview/__init__.py``).
- ``FALSE`` → no external dependency; rows behave like the six original
  catalog strategies.

**Read patterns:**

```sql
-- 1. Health check: any required external service in use?
SELECT EXISTS (
    SELECT 1 FROM strategies s
    JOIN strategy_instances si ON si.strategy_id = s.id
    WHERE s.requires_external_service = TRUE
      AND si.status IN ('live','paper')
      AND si.deleted_at IS NULL
);

-- 2. Catalog browsing (frontend dropdown):
SELECT code, display_name, asset_class, risk_rating,
       requires_external_service
  FROM strategies
 WHERE is_enabled = TRUE
 ORDER BY requires_external_service ASC, code ASC;
```

The first query is hit by ``/readyz/full`` (Atlas's health endpoint
when the deeper check is requested). It's cheap — six-ish rows in
``strategies``, the planner uses the existing
``strategies_enabled_idx`` partial index for the JOIN.

---

## 4. ``strategy_instances.external_signal_provider``

Added by migration 0005. ``VARCHAR(32) NULL``.

**Semantics:**
- ``NULL`` → no external provider (default for the original six).
- ``'tradingview'`` → signals for this instance originate from TV.
- Reserved for future providers (``'finnhub'``, ``'alpaca_news'`` etc.).

**Why a string and not a FK to a ``signal_providers`` table:**
- We only have one external provider today.
- The set of providers is small + slow-changing.
- The CHECK constraint can grow as new providers ship — same pattern
  as ``strategies.code``.

When we hit 3+ providers we'll promote this to a real lookup table.
Tracked as Phase-3 follow-up.

**Audit query — "which trades were influenced by an external feed?":**

```sql
SELECT t.id, t.symbol, t.side, t.entry_at, t.net_pnl_cents,
       si.external_signal_provider
  FROM trades t
  JOIN strategy_instances si ON si.id = t.strategy_instance_id
 WHERE si.external_signal_provider IS NOT NULL
   AND t.entry_at >= now() - INTERVAL '30 days'
 ORDER BY t.entry_at DESC;
```

Hits the partial index ``strategy_instances_external_provider_idx`` for
the join filter, then ``trades_instance_status_entry_idx`` for the
time-range scan on trades.

---

## 5. CHECK constraint expansion

Migration 0005 widens two CHECK constraints on ``strategies``:

| Constraint | Before (rev 0001-0004) | After (rev 0005) |
|---|---|---|
| ``strategies_code_check`` | ``code IN ('london_breakout','ny_killzone','ema_adx','ema_rsi','donchian','grid')`` | adds ``'tv_signal'`` |
| ``strategies_asset_class_check`` | ``asset_class IN ('gold','btc')`` | adds ``'multi'`` |

Implementation note: the original constraints in ``0001_initial.py`` use
Postgres-auto-named CHECKs (``strategies_check`` / ``strategies_check1``).
``0005`` uses a discovery DO block to drop them by definition match, then
re-creates with **stable names** (``strategies_code_check`` /
``strategies_asset_class_check``) so future migrations can refer to them
by name.

Lock impact: ``ACCESS EXCLUSIVE`` for the duration of the DROP+ADD pair,
typically < 5 ms on the (tiny) ``strategies`` table.

---

## 6. ``signals`` table — TV-specific payload

No schema change. Existing ``signals.reason`` JSONB carries the TV-specific
breakdown:

```json
{
  "source": "tradingview",
  "symbol": "XAUUSD",
  "tv_symbol": "OANDA:XAUUSD",
  "score": 0.72,
  "by_interval": {
    "1h":  {"recommendation": "BUY",        "score": 0.5},
    "4h":  {"recommendation": "STRONG_BUY", "score": 1.0},
    "1d":  {"recommendation": "BUY",        "score": 0.5}
  },
  "atr": 14.2,
  "fetched_at": "2026-06-16T10:15:33Z"
}
```

This is stored in ``signals.reason`` per the existing schema. Partitioning
is unchanged — TV-sourced signals flow into the same monthly partitions
(``signals_y2026_m06``, etc.) as the six original strategies. See
``backend/scripts/maintain_partitions.py``.

**No PII** — only ticker + price + score + ATR. But the row IS tied to
a user via ``signals.strategy_instance_id -> strategy_instances.user_id``,
so it counts as personal data for GDPR purposes and MUST appear in
``GET /me/export`` (Argus's GDPR export endpoint).

---

## 7. GDPR / PDPA implications

### 7.1 Personal data classification

| Field                              | Class                  | Notes |
|------------------------------------|------------------------|-------|
| ``signals.reason.symbol``          | non-PII (market data)  | Public ticker. |
| ``signals.reason.score``           | non-PII                | Aggregated market opinion. |
| ``signals.reason.by_interval``     | non-PII                | Multi-TF breakdown. |
| ``signals.strategy_instance_id``   | quasi-PII via FK chain | Links to ``users.id``. |
| ``strategy_instances.external_signal_provider`` | non-PII | Audit flag. |

### 7.2 Export requirements

The DSAR export (``account_exports`` workflow,
``docs/database/gdpr-export-spec.md``) MUST include:

- ``signals`` rows for the user (already covered by the per-user JOIN).
- The ``reason`` JSONB as-is — it tells the user **why** a trade fired
  on their account.
- The ``external_signal_provider`` value (transparency: "your trades
  used TradingView signals").

### 7.3 Deletion / de-identification

- On hard-purge (T+30d), ``signals.reason`` does NOT need scrubbing —
  the contents are non-PII. The FK to ``strategy_instances`` (and hence
  ``users.id``) is already de-identified by the time the user is purged.
- ``strategy_instances.external_signal_provider`` is non-PII; no
  scrubbing needed.

This matches the existing purge logic in
``scripts/purge_soft_deleted.py`` — no code change required for round 4.

---

## 8. Retention

TV-sourced signals follow the same retention as all other signals:

- Online: **18 months** (per ``maintain_partitions.py`` config).
- Archive: optional cold storage move at 18m (operational decision).

Trades derived from ``tv_signal`` follow the 7-year regulatory retention
on ``trades`` — same as any other strategy. No tv-specific treatment.

See ``docs/database/data-retention.md`` Section 11.x for the cross-table
summary updated in this round.

---

## 9. Operational queries — quick reference

```sql
-- A. Live tv_signal instance count
SELECT COUNT(*)
  FROM strategy_instances si
  JOIN strategies s ON s.id = si.strategy_id
 WHERE s.code = 'tv_signal'
   AND si.status IN ('live','paper')
   AND si.deleted_at IS NULL;

-- B. Per-symbol signal volume last 7d (TV only)
SELECT s.reason ->> 'symbol' AS symbol,
       COUNT(*)              AS signal_count
  FROM signals s
  JOIN strategy_instances si ON si.id = s.strategy_instance_id
 WHERE si.external_signal_provider = 'tradingview'
   AND s.ts >= now() - INTERVAL '7 days'
 GROUP BY 1
 ORDER BY 2 DESC;
   -- Uses signals_instance_ts_idx for the time range; JSONB ->> on symbol
   -- is a runtime extraction (acceptable — group cardinality is small).

-- C. P&L attribution to TV
SELECT date_trunc('day', t.entry_at) AS d,
       SUM(t.net_pnl_cents)::float / 100 AS net_pnl_usd
  FROM trades t
  JOIN strategy_instances si ON si.id = t.strategy_instance_id
 WHERE si.external_signal_provider = 'tradingview'
   AND t.status = 'closed'
   AND t.entry_at >= now() - INTERVAL '90 days'
 GROUP BY 1
 ORDER BY 1;
```

---

## 10. References

- ``backend/alembic/versions/0005_tv_signal.py`` — the migration.
- ``backend/scripts/seed_strategies.sql`` — dev seed mirror.
- ``trading-engine/tradingview/`` — Kairos's TV client + scorer.
- ``docs/database/data-retention.md`` — retention windows (updated).
- ``docs/database/gdpr-export-spec.md`` — DSAR export schema.
