# Backtest API Contract

> Internal contract between **Atlas (backend)** and the **Trading Engine**.
> The engine exposes a small FastAPI surface; Atlas calls it directly in
> dev, and via RQ in prod (Phase 2).

**Owner:** Kairos Toki (trading-engine) + Atlas (backend).
**Status:** Phase 1 — dev/staging only. Production wiring lands in Phase 2.

---

## Base URL

| Env  | URL                                  |
| ---- | ------------------------------------ |
| Dev  | `http://localhost:8500`              |
| Stg  | `http://trading-engine.svc:8500`     |
| Prod | `http://trading-engine.internal:8500` |

The engine is **not** public — only Atlas (and ops) talk to it.

---

## Endpoints

### `GET /healthz`

Liveness probe.

**Response 200**
```json
{
  "status": "ok",
  "service": "trading-engine",
  "version": "0.1.0",
  "platform": "Linux"
}
```

---

### `POST /run-backtest`

Kick off a backtest. Returns immediately with `202 Accepted`. The engine
writes results back to Postgres (table `backtests`) and to a JSON artifact
on disk; Atlas polls `/backtest/{id}/equity-curve` for completion.

**Request body**

```json
{
  "strategy_code": "london_breakout",
  "asset": "XAUUSD",
  "timeframe": "M15",
  "start_date": "2025-05-05",
  "end_date": "2025-06-05",
  "params": {
    "buffer_pips": 5.0,
    "sl_pips": 40.0,
    "tp_pips": 60.0
  },
  "backtest_id": "0a9c…-uuid"
}
```

| Field           | Type                | Required | Notes                                         |
| --------------- | ------------------- | -------- | --------------------------------------------- |
| `strategy_code` | string              | yes      | One of the 6 codes below                      |
| `asset`         | string              | yes      | `XAUUSD`, `BTCUSDT`, …                        |
| `timeframe`     | string              | yes      | `M5`, `M15`, `H1`, `H4`                        |
| `start_date`    | string (YYYY-MM-DD) | yes      | UTC                                           |
| `end_date`      | string (YYYY-MM-DD) | yes      | UTC, inclusive                                |
| `params`        | object              | no       | Strategy params; missing keys use defaults    |
| `backtest_id`   | string (uuid)       | no       | If Atlas already inserted the DB row, pass it |

**Valid `strategy_code` values**

- `london_breakout`
- `ny_killzone`
- `ema_adx_trend`
- `ema_rsi_swing`
- `donchian_breakout`
- `grid_bot`

(Source of truth: `configs/strategies.yaml`.)

**Response 202**
```json
{
  "backtest_id": "0a9c…-uuid",
  "status": "accepted",
  "message": "Backtest started; poll /backtest/{id}/equity-curve"
}
```

**Errors**

- `409 Conflict` — `backtest_id` already running.
- `422 Unprocessable Entity` — schema mismatch (Pydantic).

---

### `GET /backtest/{backtest_id}/equity-curve`

Polled by Atlas / Eos until `status == "completed"`.

**Response 200 (completed)**
```json
{
  "backtest_id": "0a9c…-uuid",
  "status": "completed",
  "summary": {
    "total_trades": 18,
    "win_rate": 0.4444,
    "profit_factor": 1.62,
    "expectancy_r": 0.18,
    "total_return_pct": 4.23,
    "sharpe": 1.12,
    "sortino": 1.61,
    "max_drawdown_pct": -3.78
  },
  "equity_curve": [
    {"timestamp": "2025-05-05 00:00:00+00:00", "equity": 10000.0},
    {"timestamp": "2025-05-05 01:00:00+00:00", "equity": 10000.0},
    ...
  ]
}
```

**Response 202 (still running)**
```json
{ "backtest_id": "…", "status": "running", "error": null }
```

**Response 404** — unknown id.

---

### `POST /test-mt5-connection`

Verify a user's MT5 credentials before saving them.

**Request body**
```json
{
  "server": "Exness-MT5Real8",
  "login": 1234567,
  "password": "users-investor-password",
  "broker_account_id": "ba_abc123"
}
```

**Response 200**
```json
{
  "success": true,
  "platform": "Linux",
  "mock": true,
  "message": "Mocked OK — MT5 only runs on Windows; current platform=Linux.",
  "error": null
}
```

| Field           | Notes                                                              |
| --------------- | ------------------------------------------------------------------ |
| `success`       | `true` ⇒ accept credentials                                        |
| `platform`      | `"Windows" \| "Linux" \| "Darwin"`                                  |
| `mock`          | `true` off-Windows; `false` on Windows VPS                         |
| `message`       | Human-readable detail                                              |
| `error`         | Non-null on real failure (`mock=false` only)                       |

---

## Database side effects

The worker updates row `backtests` (Postgres, owned by Atlas):

```sql
UPDATE backtests
SET status            = 'running' | 'completed' | 'failed',
    metrics           = <summary jsonb>,
    equity_curve_url  = 'file:///var/data/equity-curves/{id}.json',
    error_message     = <nullable text>,
    updated_at        = NOW()
WHERE id = :backtest_id;
```

The artifact path is dev-local (`file://`). In prod, swap to an S3 URL by
overriding `EQUITY_CURVE_DIR` + adding an uploader.

---

## Failure modes (and how Atlas should handle them)

| Symptom                                  | Likely cause                            | Atlas action                                        |
| ---------------------------------------- | --------------------------------------- | --------------------------------------------------- |
| `202` but never flips to `completed`     | Worker crashed / OOM                    | After 30 min, mark `failed`; expose retry button    |
| `summary.total_trades == 0`              | Sample window too tame / params too strict | Surface as info, not error                          |
| `summary.profit_factor == "Infinity"`    | Zero losing trades (rare; suspicious)   | Display as `> 99`; warn user "verify with longer period" |
| `success: false` on `/test-mt5-connection` | Wrong creds / server unreachable        | Show `error` field verbatim; do NOT persist creds   |

---

## Phase-1 vs Phase-2 behavior

| Behavior             | Phase 1 (now)                 | Phase 2 (later)                  |
| -------------------- | ----------------------------- | -------------------------------- |
| Job execution        | In-process thread             | RQ worker pulling from Redis     |
| Concurrency          | 1 (per engine process)        | N workers, horizontally scalable |
| Status polling       | Memory + disk artifact        | Redis `rq.job` + DB              |
| `test-mt5-connection` (off-Windows) | Mocked success | Routed to dedicated Windows VPS  |

Frontend request shape does **not** change between phases.

---

## Reference client (Python)

```python
import httpx

ENGINE = "http://trading-engine.svc:8500"

resp = httpx.post(
    f"{ENGINE}/run-backtest",
    json={
        "strategy_code": "london_breakout",
        "asset": "XAUUSD",
        "timeframe": "M15",
        "start_date": "2025-05-05",
        "end_date": "2025-06-05",
        "params": {},
        "backtest_id": str(uuid.uuid4()),
    },
    timeout=10.0,
)
resp.raise_for_status()
backtest_id = resp.json()["backtest_id"]

# Later, when polling…
status = httpx.get(f"{ENGINE}/backtest/{backtest_id}/equity-curve").json()
```
