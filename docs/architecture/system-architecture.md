# System Architecture — Forex/Crypto Trading Bot Platform

> Architect: Daedalus Souta
> Version: 1.0
> Status: Draft (Phase 1 — Foundation)
> Last updated: 2026-06-14

---

## 1. Executive Summary

SaaS platform ที่ให้ paid members เชื่อม Exness MT5 account ของตัวเอง และเปิด/ปิด 6 automated strategies (Gold + BTC) ผ่าน UI ที่ใช้งานง่าย พร้อม backtest, live monitoring, billing

**Style:** Modular monolith (FastAPI) + dedicated Trading Engine workers + headless MT5 terminal pool on Windows VPS
**Trade-off ที่กำหนด architecture นี้:**
- 1 team, <50 active users (Phase 1–2) → monolith ก่อน, split later (ADR-006)
- MT5 Python = Windows-only → ต้องมี Windows VPS แยกต่างหาก (ADR-001)
- Boring tech wins → choose proven stack (ADR-003)

---

## 2. C4 Model

### 2.1 C1 — System Context

ใครคุยกับระบบเราบ้าง?

```mermaid
flowchart LR
    User([Member / Trader])
    Admin([Admin / Ops])

    subgraph Our["Forex Bot Platform"]
        Sys[Trading Bot SaaS]
    end

    Stripe[(Stripe Billing)]
    Exness[(Exness Broker<br/>MT5 Server)]
    Binance[(Binance<br/>via ccxt)]
    Email[(SMTP / Postmark)]
    Sentry[(Sentry)]

    User -- web UI / dashboard --> Sys
    Admin -- admin console --> Sys
    Sys -- subscribe / webhook --> Stripe
    Sys -- order / market data --> Exness
    Sys -- crypto order / data --> Binance
    Sys -- alerts / receipts --> Email
    Sys -- errors --> Sentry
```

**Actors:**
- **Member** — paid subscriber, เชื่อม MT5 ของตัวเอง, เลือก strategy, ดู PnL
- **Admin** — ops team, ดู system health, จัดการ user, refund
- **Exness MT5** — broker server (login/server/password); access ผ่าน MT5 terminal บน Windows
- **Binance** — crypto exchange; access ผ่าน ccxt + API key ของ user
- **Stripe** — subscription billing; webhook back to us
- **Email** — transactional (welcome, receipt, risk alert)
- **Sentry** — error tracking

---

### 2.2 C2 — Container Diagram

```mermaid
flowchart TB
    User([Member])

    subgraph Linux["Linux VPS (Hetzner CX31) — App Plane"]
        Web["Web Frontend<br/>Next.js 15 SSR<br/>port 3000"]
        API["API Gateway / Backend<br/>FastAPI 0.110+<br/>port 8000<br/>(modular monolith)"]
        Worker["Background Worker<br/>APScheduler + arq<br/>(scheduled jobs)"]
        BTRunner["Backtest Runner<br/>vectorbt + Backtrader<br/>(stateless, fan-out)"]
        Redis[("Redis 7<br/>cache, queue, session")]
        Postgres[("PostgreSQL 16<br/>main DB + pgcrypto")]
        Prom["Prometheus + Grafana + Loki<br/>(observability)"]
    end

    subgraph Win["Windows VPS (Contabo VPS M) — Trading Plane"]
        Bridge["MT5 Bridge Service<br/>Python FastAPI<br/>port 9100 (mTLS, VPN)"]
        Pool["MT5 Terminal Pool<br/>(N terminals, 1 per active user)"]
        Exec["Trading Engine Worker<br/>(strategy runner + executor)"]
    end

    Exness[(Exness MT5 Server)]
    Binance[(Binance API)]
    Stripe[(Stripe)]

    User -- HTTPS --> Web
    Web -- REST / SSE --> API
    API <--> Redis
    API <--> Postgres
    API -- enqueue --> Worker
    Worker -- spawn --> BTRunner
    BTRunner --> Postgres
    API -- signed RPC (mTLS) --> Bridge
    Bridge -- Python MT5 API --> Pool
    Pool -- proprietary --> Exness
    Exec -- ccxt --> Binance
    Exec -- read strategy/config --> Postgres
    Exec -- order via --> Bridge
    Stripe -- webhook --> API
    API -- callback --> Stripe

    API -- metrics/logs --> Prom
    Bridge -- metrics/logs --> Prom
```

**Container responsibilities:**

| Container | Responsibility | Why separate |
|-----------|---------------|--------------|
| **Web (Next.js)** | UI, SSR, auth UI, SEO | Frontend stack independent of Python |
| **API (FastAPI)** | Public REST API, auth, billing, user/strategy CRUD, orchestration | Single entrypoint, modular monolith |
| **Background Worker** | scheduled jobs (rebalance, daily report, billing reconciliation) | offload long tasks from API |
| **Backtest Runner** | CPU-heavy backtest, isolated process | don't block API; fan-out parallel |
| **MT5 Bridge** | wrap `MetaTrader5` package; expose RPC; manage terminal pool | Windows-only; isolate from app |
| **Trading Engine Worker** | live strategy execution loop | latency-critical; runs near MT5 Bridge on Windows or Linux+RPC |
| **Postgres** | OLTP — users, strategies, orders, trades, billing | single source of truth |
| **Redis** | cache, rate limit, session token, BullMQ-style queue, last-price ticker cache | low-latency, ephemeral |

---

### 2.3 C3 — Component Diagram (Backend FastAPI Monolith)

```mermaid
flowchart TB
    subgraph FastAPI["FastAPI App (modular monolith)"]
        direction TB
        Router[HTTP Routers / OpenAPI]
        subgraph Modules["Domain Modules (bounded contexts)"]
            Auth["auth/<br/>JWT, NextAuth bridge,<br/>RBAC, password"]
            User["user/<br/>profile, preference,<br/>API key"]
            BrokerCred["broker_credential/<br/>encrypted store,<br/>connection test"]
            Strategy["strategy/<br/>catalog, params,<br/>enable/disable"]
            Backtest["backtest/<br/>queue, status, result"]
            Trading["trading/<br/>signal log, order log,<br/>position, PnL"]
            Billing["billing/<br/>Stripe sub, webhook,<br/>invoice"]
            Notify["notification/<br/>email, in-app,<br/>risk alert"]
            Admin["admin/<br/>user mgmt, audit log,<br/>kill switch"]
        end
        subgraph Infra["Infra Layer"]
            DB["SQLAlchemy 2 / Alembic"]
            Cache["Redis client"]
            BridgeClient["MT5 Bridge client<br/>(mTLS)"]
            StripeSDK["Stripe SDK"]
        end
        Router --> Modules
        Modules --> Infra
    end
```

**Trading Engine components (Windows VPS):**

```mermaid
flowchart TB
    subgraph TE["Trading Engine Worker"]
        Sched["scheduler<br/>(APScheduler)"]
        StratRunner["strategy_runner<br/>loads user's enabled strategies"]
        Strats["strategies/<br/>(london_breakout,<br/>ny_killzone, ema_adx,<br/>btc_breakout,<br/>gold_scalp, grid)"]
        Risk["risk_manager<br/>(per-account limits,<br/>drawdown circuit breaker,<br/>position sizing)"]
        OMS["OMS<br/>(order state machine,<br/>idempotency,<br/>reconciliation)"]
        Adapter["broker_adapter<br/>(MT5 / ccxt)"]
    end
    Sched --> StratRunner
    StratRunner --> Strats
    Strats -- signal --> Risk
    Risk -- approved order --> OMS
    OMS --> Adapter
    Adapter -- MT5 Bridge RPC --> MT5
    Adapter -- ccxt HTTP --> Binance
    MT5[(MT5 Pool)]
    Binance[(Binance)]
```

---

### 2.4 Deployment Topology

```
┌────────────────────────────────────────────────────────────────┐
│  Internet (HTTPS / WSS)                                        │
└──────────────────┬─────────────────────────────────────────────┘
                   │
        ┌──────────┴──────────┐
        │  Cloudflare         │ TLS termination, WAF, DDoS
        │  (CDN + DNS)        │
        └──────────┬──────────┘
                   │
┌──────────────────┴─────────────────────────────────────────────┐
│  LINUX VPS — Hetzner CX31 ($15/mo, 2vCPU, 8GB, 80GB SSD)       │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  Caddy (reverse proxy, TLS, gzip)                          │ │
│  └─────┬───────────────────────────────────────┬──────────────┘ │
│        │                                       │                │
│  ┌─────┴────┐ ┌─────────┐ ┌────────┐ ┌──────┴─────┐           │
│  │ Next.js  │ │ FastAPI │ │ Worker │ │ Backtest    │           │
│  │ (PM2/    │ │ (uvicorn│ │ (arq)  │ │ Runner      │           │
│  │  systemd)│ │  4 procs)│ │        │ │ (on demand) │           │
│  └──────────┘ └────┬────┘ └───┬────┘ └─────┬──────┘           │
│                   │           │              │                  │
│              ┌────┴───────────┴──────────────┘                  │
│              ▼                                                  │
│  ┌────────────────┐  ┌──────────────┐  ┌─────────────────┐    │
│  │ PostgreSQL 16  │  │  Redis 7     │  │ Prom+Grafana+Loki│    │
│  │ (data volume)  │  │  (RAM)       │  │  (observability) │    │
│  └────────────────┘  └──────────────┘  └─────────────────┘    │
└─────────────────────────────────┬──────────────────────────────┘
                                  │ WireGuard VPN (private link)
                                  │ + mTLS on app layer
                                  ▼
┌────────────────────────────────────────────────────────────────┐
│  WINDOWS VPS — Contabo VPS M ($20/mo, 6vCPU, 16GB, 400GB)      │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  MT5 Bridge Service (Python FastAPI on port 9100)          │ │
│  │   - RPC endpoints (open_order, close, get_positions, ...)  │ │
│  │   - terminal pool manager (N=~50 max)                      │ │
│  └─────┬──────────────────────────────────────────────────────┘ │
│        │                                                        │
│  ┌─────┴─────────────────────────────────────────────────────┐ │
│  │  Trading Engine Worker (collocated for latency)           │ │
│  │   - scheduler, strategy_runner, risk_manager, OMS         │ │
│  └─────┬─────────────────────────────────────────────────────┘ │
│        │                                                        │
│  ┌─────┴─────┐ ┌─────────┐ ┌─────────┐  ... up to ~50          │
│  │ MT5 #1    │ │ MT5 #2  │ │ MT5 #3  │   terminals             │
│  │ user_A    │ │ user_B  │ │ user_C  │                         │
│  └─────┬─────┘ └────┬────┘ └────┬────┘                         │
└────────┼────────────┼───────────┼───────────────────────────────┘
         │            │           │   each terminal logs into
         ▼            ▼           ▼   different Exness account
                  Exness MT5 Server (broker)
```

**Notes:**
- Linux VPS หนึ่งตัวพอใน Phase 1–2 (snapshot รายวัน → S3-compatible backup)
- Windows VPS แยก 1 ตัวก่อน, scale ออกเป็น 2+ เมื่อใกล้ 50 active users (sharding by user_id)
- VPN tunnel + mTLS — MT5 Bridge ไม่เคยเปิดสู่ public internet
- Crypto path (ccxt → Binance) ไม่ต้องผ่าน Windows; รันบน Linux โดยตรง

---

## 3. Data Flow

### 3.1 Backtest Run

```mermaid
sequenceDiagram
    actor U as User (Browser)
    participant W as Next.js
    participant API as FastAPI
    participant Q as Redis Queue
    participant R as Backtest Runner
    participant DB as Postgres

    U->>W: POST /backtest (strategy_id, range, params)
    W->>API: forward (JWT)
    API->>DB: insert backtest_job (status=queued)
    API->>Q: enqueue(backtest_id)
    API-->>W: 202 Accepted + job_id
    W-->>U: show "running" + poll

    R->>Q: dequeue
    R->>DB: read strategy spec + params
    R->>R: vectorbt run<br/>(3y daily ~3-15s)
    R->>DB: update job (status=done, metrics, equity_curve_blob)

    loop polling (or SSE)
        W->>API: GET /backtest/{id}
        API->>DB: read job
        API-->>W: status=done + result URL
    end
    W->>API: GET /backtest/{id}/equity-curve
    API->>DB: stream
    API-->>W: JSON / Parquet
    W-->>U: render lightweight-charts
```

**SLA:** UI ต้องคืนผล ≤ 30s สำหรับ 3-year window (NFR-3)

---

### 3.2 Live Signal → Order Execution

```mermaid
sequenceDiagram
    participant S as Scheduler (tick)
    participant SR as Strategy Runner
    participant RM as Risk Manager
    participant OMS as OMS
    participant BR as MT5 Bridge
    participant MT5 as MT5 Terminal
    participant EX as Exness
    participant DB as Postgres

    S->>SR: tick (e.g. every 5s for M5 strat)
    SR->>BR: get_market_data(symbol, timeframe)
    BR->>MT5: copy_rates_from_pos
    MT5-->>BR: bars
    BR-->>SR: DataFrame

    SR->>SR: compute signal<br/>(EMA cross, breakout, ...)
    alt signal != NONE
        SR->>RM: validate(order_intent)
        RM->>DB: read account state, open positions, daily PnL
        alt within risk budget
            RM-->>SR: approved
            SR->>OMS: place(order_intent)
            OMS->>DB: insert order (status=pending, idempotency_key)
            OMS->>BR: open_order(symbol, vol, sl, tp, magic)
            BR->>MT5: order_send
            MT5->>EX: order
            EX-->>MT5: ticket / error
            MT5-->>BR: result
            BR-->>OMS: ticket
            OMS->>DB: update order (status=filled, ticket)
        else risk breached
            RM-->>SR: rejected (reason)
            SR->>DB: log signal_rejected
            SR->>Notify: alert user (drawdown / overexposure)
        end
    end
```

**SLA:** signal → order acknowledged ≤ 2s (NFR-2)

---

### 3.3 Manual Stop (Kill Switch)

```mermaid
sequenceDiagram
    actor U as User
    participant W as Next.js
    participant API as FastAPI
    participant DB as Postgres
    participant Cache as Redis
    participant SR as Strategy Runner

    U->>W: click "Stop strategy X" (require 2FA reconfirm)
    W->>API: POST /strategies/{id}/stop
    API->>DB: update strategy (enabled=false, stopped_at=now)
    API->>Cache: PUBLISH strategy.stopped {user_id, strat_id}
    API->>DB: insert audit_log
    API-->>W: 200 OK
    W-->>U: "Stopped" toast

    Note over SR: Strategy Runner subscribes to channel
    Cache-->>SR: event
    SR->>SR: drop strategy from active loop
    SR->>OMS: optionally close_open_positions(strat_id) [user choice]
```

**Latency:** stop takes effect ≤ 5s (cache pub/sub propagation)
**Safety:** kill switch ที่ admin (global stop_all) ไม่ต้อง 2FA

---

## 4. Domain Model (Bounded Contexts)

| Bounded Context | Aggregate | Stewardship |
|-----------------|-----------|-------------|
| **Identity** | User, Session, ApiKey | Atlas / Argus |
| **Broker** | BrokerCredential, ConnectionTest | Argus + Kairos |
| **Strategy Catalog** | Strategy, StrategyVersion, Param | Kairos |
| **Backtest** | BacktestJob, BacktestResult | Kairos |
| **Trading** | StrategyAssignment, Signal, Order, Position, Trade | Kairos + Atlas |
| **Billing** | Subscription, Invoice, Payment | Atlas |
| **Notification** | NotificationPreference, NotificationEvent | Atlas |
| **Admin / Audit** | AuditLog, KillSwitch | Argus |

**Ubiquitous language pitfalls (define explicitly in glossary):**
- **Signal** ≠ **Order** ≠ **Trade** ≠ **Position**
- **Strategy** (catalog template) ≠ **StrategyAssignment** (user enables one)
- **Lot** vs **Volume** — เลือก 1 ชื่อ stick กับมัน

---

## 5. Key Architectural Decisions (ดู ADR เต็ม)

| # | Decision | Rationale |
|---|----------|-----------|
| 001 | MT5 ผ่าน Python package, 1 terminal/user pool บน Windows VPS | ทีมต้องการ central UI; MQL5 EA ไม่รองรับ |
| 002 | Monorepo + pnpm workspaces + uv | 1 team, atomic refactor, simpler CI |
| 003 | Stack: FastAPI + Next.js 15 + Postgres + Redis (full list) | boring, mature, fits team skill |
| 004 | Linux VPS (Hetzner) + Windows VPS (Contabo) | cost-effective, separate failure domain |
| 005 | Broker credential: app-level AES-256-GCM envelope encryption, pgcrypto KV | secrets are the highest blast-radius |
| 006 | Monolith first; consider split at Phase 3 if >50 users or team grows | Conway's Law; YAGNI |

---

## 6. Cross-cutting Concerns

### 6.1 Observability
- **Metrics:** Prometheus scrape from FastAPI (`/metrics`), MT5 Bridge, system_exporter
- **Logs:** structured JSON → Loki; correlation ID ผ่านทุก request/order
- **Traces:** OpenTelemetry SDK in FastAPI; consider Tempo later
- **Dashboards:** Grafana — system, business KPI, per-user PnL summary, error budget

### 6.2 Security (ส่งต่อ Argus เต็ม)
- TLS everywhere (Caddy + mTLS for bridge)
- Argon2id password, JWT short-lived + rotate refresh
- Per-user rate limit, broker credential encrypted, audit log immutable
- 2FA required for: change broker cred, enable real-money strategy, withdraw-equivalent action
- Kill switch ที่ admin level

### 6.3 Failure Modes (ทำก่อน happy path)
| What fails | Detection | Mitigation |
|------------|-----------|------------|
| MT5 terminal crash | health check fail | bridge restart terminal; mark assigned user "paused", alert |
| Windows VPS down | bridge no heartbeat 30s | mark all assigned strategies paused; notify users; spin standby |
| Exness API reject (e.g. requote) | error code in result | OMS retry with backoff (max 3), log signal_rejected |
| Postgres down | health probe | API returns 503; restore from latest snapshot (RPO ≤ 1h) |
| Redis down | catch exception | degrade to direct DB; throttle non-critical features |
| Stripe webhook failure | webhook signature check + retry | idempotent; reconcile via daily job |
| Strategy bug causes runaway orders | risk_manager + per-strategy max orders/day cap | hard stop; alert + auto-disable strategy |
| Drawdown breach | risk_manager monitors PnL | auto-disable strategy at user's set DD limit |

### 6.4 Data
- See `docs/database/schema.md` (Mnemosyne)
- Backups: pg_dump nightly → S3-compat (Backblaze B2); 30-day retention; quarterly restore test

---

## 7. Open Questions (escalate to Zeus)
1. Phase 2 — เปิดให้สมัครจ่ายเงินสูงสุดกี่ users? ใช้ตอบ Windows VPS sizing
2. Refund policy? affects billing module + dispute handling
3. KYC requirement? (กฎหมาย TH สำหรับ trading-related SaaS)
4. ต้อง support broker อื่นนอก Exness ใน Phase 1 ไหม? (affect broker_adapter abstraction urgency)

---

## 8. Glossary
- **MT5** — MetaTrader 5, retail trading platform/API
- **EA** — Expert Advisor (MQL5 script ที่รันใน MT5 terminal)
- **OMS** — Order Management System
- **NFR** — Non-functional Requirement
- **RPO** — Recovery Point Objective (data loss tolerance)
- **RTO** — Recovery Time Objective (downtime tolerance)
- **PF** — Profit Factor (gross profit / gross loss)
- **DD** — Drawdown
- **bounded context** — DDD term, ขอบเขตของ model ที่ consistent
