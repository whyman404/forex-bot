# ADR-003 — Tech Stack Lock-in

**Status:** Accepted
**Date:** 2026-06-14
**Decider:** Daedalus Souta (all specialists consulted)
**Related:** ADR-001 (MT5), ADR-002 (Monorepo), ADR-006 (Monolith)

---

## Context

ต้องเลือก stack สำหรับ Phase 1–3 (≈ 1 ปี) บนเกณฑ์:
- Team skill (Python + TS heavy, มี mixed ML/data background)
- Boring tech (ทดสอบแล้ว, community ใหญ่, มี ops experience)
- Reversible — ถ้าผิด เปลี่ยนได้
- Scope: SaaS trading bot + dashboard + backtest + billing + monitoring

## Decision — Stack Lock

### Backend
| Layer | Choice | Version | Reason |
|-------|--------|---------|--------|
| Language | Python | 3.12 | type hints mature, perf gains (PEP 709), wide ML/quant ecosystem |
| Web framework | FastAPI | 0.110+ | async, OpenAPI auto, Pydantic v2, team productivity |
| ORM | SQLAlchemy | 2.0 | mature, async support, raw SQL escape hatch |
| Migration | Alembic | latest | de-facto with SQLAlchemy |
| Queue | arq + Redis | latest | simple async queue, Redis เราใช้อยู่แล้ว |
| Scheduler | APScheduler | 3.x | in-process, ไม่ต้อง infra เพิ่ม |
| Validation | Pydantic | v2 | bundled with FastAPI, perf solid |
| Auth (BE) | python-jose + passlib (argon2) | latest | standard JWT + secure hashing |
| Stripe SDK | stripe-python | latest | official |
| HTTP client | httpx | latest | async, modern |

### Trading Engine
| Layer | Choice | Reason |
|-------|--------|--------|
| Language | Python 3.12 | unify with backend |
| MT5 | `MetaTrader5` package | only option (ADR-001) |
| Crypto | `ccxt` | unified API across exchanges |
| Backtest (fast) | `vectorbt` 2.x | vectorized, fast iterate (3y in <15s typical) |
| Backtest (event-driven) | `Backtrader` | realistic order sim, broker abstraction |
| Indicators | `TA-Lib` (Python wrapper) | C-backed perf, standard library |
| Data | `pandas` 2.x, `numpy` 1.26+, `pyarrow` (parquet) | standard |
| Time series cache | `parquet` files + Postgres | simple, no extra infra |

### Frontend
| Layer | Choice | Version | Reason |
|-------|--------|---------|--------|
| Framework | Next.js | 15 (App Router) | RSC, mature, hiring pool |
| Language | TypeScript | 5.4+ strict | safety + DX |
| Styling | Tailwind CSS | 3.x | utility, team velocity |
| UI kit | shadcn/ui (Radix + Tailwind) | latest | accessible, copy-in components (no lock-in to library updates) |
| Server state | TanStack Query | 5.x | proven, cache + sync |
| Client state | Zustand | 4.x | minimal, no boilerplate |
| Charts | lightweight-charts (TradingView) | latest | best perf for trading UI, native fit |
| Forms | react-hook-form + zod | latest | typed, perf |
| Auth (FE) | NextAuth.js (Auth.js v5) | latest | session + bridge to backend JWT |
| HTTP | fetch + TanStack Query | native | enough |
| Tables | TanStack Table | 8.x | flexible |

### Data
| Layer | Choice | Reason |
|-------|--------|--------|
| Primary DB | PostgreSQL | 16 | proven, JSON support, pgcrypto for ADR-005 |
| Cache / Queue / PubSub | Redis | 7 | LRU cache, arq queue, kill-switch pub/sub |
| File / blob | local FS (Phase 1), S3-compat (Backblaze B2 / R2) at Phase 2 | cheap, sufficient |

### Infrastructure / Ops
| Layer | Choice | Reason |
|-------|--------|--------|
| Container | Docker + docker-compose (dev) | standard |
| Reverse proxy | Caddy | auto-TLS, simple config |
| VPN | WireGuard | between Linux ↔ Windows VPS |
| CI/CD | GitHub Actions | already in ecosystem |
| Metrics | Prometheus + Grafana | de-facto, no SaaS lock-in |
| Logs | Loki | pairs with Grafana, cheap |
| Errors | Sentry (self-host or cloud free tier) | best DX |
| Uptime | UptimeRobot (free) | simplest external |
| Secrets (host) | systemd env + sops + age | no Vault overhead at this size |
| Process mgmt | systemd (Linux), NSSM (Windows) | OS-native |
| Backup | pg_dump → Backblaze B2 nightly | cheap, durable |

### Billing
| Layer | Choice | Reason |
|-------|--------|--------|
| International | Stripe | best DX, webhook reliability |
| Thailand fallback | Omise | local payment methods (Phase 2+) |

### Quality
| Layer | Choice | Reason |
|-------|--------|--------|
| Python format/lint | ruff | unified, fast |
| Python type | mypy strict | catch bugs early |
| Python test | pytest + pytest-asyncio + httpx test client | standard |
| Python coverage | coverage.py | standard |
| TS lint | eslint + @typescript-eslint | standard |
| TS format | prettier | standard |
| TS test | vitest + Testing Library | fast, Jest-compatible |
| E2E | Playwright | best multi-browser |
| Load test | k6 | scriptable, CI-friendly |
| Pre-commit | lefthook | fast, language-agnostic |

---

## Alternatives Considered (key ones)

| Slot | Considered | Why not chosen |
|------|------------|----------------|
| Backend lang | Go, TypeScript (Node) | TS/Node split ecosystem from quant; Go loses ML/quant libs |
| Web framework | Django, Flask, Litestar | Django heavy for our shape; Flask no async; Litestar less mature |
| ORM | SQLModel, Tortoise | SQLModel still wraps SQLAlchemy with quirks; Tortoise smaller community |
| Queue | Celery, RQ, Dramatiq | Celery overkill + ops heavy; RQ sync only; arq fits async story |
| Frontend | Remix, SvelteKit, Vue+Nuxt | Next.js ecosystem + hiring win |
| State | Redux Toolkit, Jotai | Zustand simpler, TanStack Query handles server state |
| DB | MySQL, SQLite, Mongo | Postgres = best JSON + extensions (pgcrypto, TimescaleDB later) |
| Auth | Auth0, Clerk, Supabase Auth | cost + vendor lock for what's not core differentiator yet |
| Charts | Chart.js, Recharts, Highcharts | lightweight-charts ออกแบบมาเพื่อ trading โดยตรง |
| Backtest | Zipline, QuantConnect Lean | Zipline maintenance-mode; QC heavy + cloud-bound |

---

## Consequences

### Positive
- Boring + mature → fewer surprises in production
- Hiring pool large for Python + Next.js
- Each piece has clear migration path if needed (FastAPI → Litestar, Next.js → Remix, etc.)
- No SaaS lock-in for core (Stripe is replaceable; DB self-hosted)

### Negative / Trade-off
- Python GIL — บาง workload (backtest) ต้อง process-based parallelism (mitigation: process pool, vectorbt vectorized)
- MetaTrader5 package = single-OS — แก้ไม่ได้ (ADR-001 explains)
- Self-hosted observability (Prom+Grafana+Loki) = ops burden (mitigation: docker-compose stack, alert minimum, escalate to managed if pain)

### Risk Register
| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| FastAPI breaks API on minor version | low | medium | pin version, integration tests |
| Pydantic v2 perf regression edge case | low | low | benchmark in load test |
| Next.js 15 App Router breaking change | medium | medium | hold one minor behind latest |
| TA-Lib install pain on Windows | medium | low | document install; pre-built wheels |
| vectorbt 2.x API churn | medium | low | abstract through internal interface |

### Version Pin Strategy
- **Major version:** pin (`fastapi = "~0.110"`, `next: "15.x"`)
- **Re-evaluate quarterly** — security patch immediately, feature upgrade planned
- **Lockfile committed** — `uv.lock`, `pnpm-lock.yaml`

---

## Out of Scope (Phase 1)
- gRPC, GraphQL — REST + OpenAPI ก่อน
- Kafka, NATS — Redis pub/sub พอ
- Kubernetes — VPS + systemd ก่อน (ADR-004, ADR-006)
- ML training pipeline — Phase 4

---

## References
- "Choose Boring Technology" — Dan McKinley
- FastAPI: https://fastapi.tiangolo.com/
- vectorbt: https://vectorbt.dev/
- shadcn/ui: https://ui.shadcn.com/
- TanStack Query: https://tanstack.com/query
