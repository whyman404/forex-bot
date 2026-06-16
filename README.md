# 🤖 Forex/Crypto Trading Bot Platform

> Automated trading bot platform — MT5 (Exness) + Binance — with web UI + membership

**Project Lead:** Zeus Ryujin
**Tech Lead / Architect:** Daedalus Souta
**Quant Engineer:** Kairos Toki
**Project Owner:** whyman404@gmail.com

---

## เป้าหมาย (ทีมเสนอ — ขอ user confirm)

### ✅ เป้าหมายธุรกิจ
- เป็น SaaS trading bot ที่ user paid subscription + เชื่อม Exness MT5 ของตัวเองได้
- สมาชิกเทรดอัตโนมัติ 6 strategies (Gold + BTC) โดยมี UI ใช้งานง่าย

### ✅ เป้าหมายเทคนิค (ตัวเลขที่ทีม commit ได้)
- **Profit Factor > 1.5** (เกณฑ์ professional)
- **Max Drawdown ≤ 20%**
- **Sharpe Ratio > 1.0** (annualized)
- **Positive expectancy** per trade

### ⚠️ เรื่อง win rate 95%
- กลยุทธ์ที่ user ให้มา (London Breakout, NY Killzone, EMA+ADX, etc.) **มี natural win rate 35-55%** แต่ profitable ได้ด้วย RR > 1:1.5
- 95% win rate เป็นเป้าที่เป็นไปได้เฉพาะ **Grid bot ที่ไม่มี SL** — ซึ่ง 1 ครั้งที่ตลาดเทรนด์แรงจะ wipe out
- **ทีมจะออกแบบให้ profitable consistently** + report ทั้ง win rate, PF, Sharpe, DD ให้ user ตัดสินใจเอง

---

## โครงสร้างโปรเจกต์

```
projects/forex-bot/
├── README.md               ← คุณอยู่ที่นี่
├── backend/                ← FastAPI backend
├── frontend/               ← Next.js frontend
├── trading-engine/         ← Python trading engine (strategies, backtest, broker, OMS)
├── infra/                  ← Docker, Terraform, CI/CD
├── docs/                   ← Documentation
│   ├── project/            ← Charter, roadmap (Zeus)
│   ├── architecture/       ← Architecture + ADR (Daedalus)
│   ├── design/             ← UI/UX wireframe + design system (Iris)
│   ├── database/           ← Schema + migrations (Mnemosyne)
│   ├── api/                ← OpenAPI spec (Atlas)
│   ├── strategies/         ← Strategy specs (Kairos)
│   ├── security/           ← Threat model (Argus)
│   ├── deployment/         ← Infra + deployment (Hestia)
│   └── testing/            ← Test strategy (Themis)
└── .github/workflows/      ← CI/CD
```

---

## Tech Stack (ทีมเลือกเอง — Daedalus ADR-003)

### Backend
- **Python 3.12** + **FastAPI** — type-safe, async, great for ML
- **PostgreSQL 16** — main DB
- **Redis 7** — cache, session, queue
- **SQLAlchemy 2.0** + **Alembic** — ORM + migration

### Trading Engine
- **Python 3.12**
- **MetaTrader5** package — MT5 integration (Windows only)
- **vectorbt** — fast backtesting
- **Backtrader** — event-driven backtest + live
- **ccxt** — crypto exchange (Binance)
- **pandas** + **numpy** + **TA-Lib** — analysis
- **APScheduler** — scheduled tasks

### Frontend
- **Next.js 15** (App Router)
- **TypeScript** strict
- **Tailwind CSS** + **shadcn/ui**
- **TanStack Query** — server state
- **Zustand** — client state
- **lightweight-charts** (TradingView) — chart
- **NextAuth.js** — auth

### Infra
- **Docker** + **docker-compose** (dev)
- **Windows VPS** (Contabo / Exness VPS) — for MT5 terminal
- **Linux VPS** (Hetzner / DO) — for backend + frontend
- **GitHub Actions** — CI/CD
- **Sentry** — error tracking
- **Prometheus + Grafana** — metrics
- **Loki** — logs

### Payment (Membership)
- **Stripe** — international
- **Omise** — Thailand fallback

---

## Phase Roadmap

| Phase | Duration | Goal |
|-------|----------|------|
| **Phase 1: Foundation** | 6 weeks | architecture, schema, UI, **backtest + paper trading** ของ 6 strategies |
| **Phase 2: MVP** | 4 weeks | live trading (small account), membership/billing, monitoring |
| **Phase 3: Scale** | 8 weeks | multi-user, performance, marketing, public launch |
| **Phase 4: Optimize** | continuous | strategy iteration, ML integration, more brokers |

---

## ทีมพัฒนา (10 specialists + Hephaestus mentor)

| # | Role | Agent | งานหลัก |
|---|------|-------|---------|
| 1 | PM | Zeus Ryujin | timeline, sprint, risk |
| 2 | Architect | Daedalus Souta | system design, ADR |
| 3 | UX/UI | Iris Kaguya | wireframe, design system |
| 4 | DB | Mnemosyne Rin | schema, migration |
| 5 | Backend | Atlas Goro | FastAPI, business logic |
| 6 | Frontend | Eos Hinata | Next.js, dashboard |
| 7 | Quant | **Kairos Toki** | strategy, backtest, broker integration |
| 8 | DevOps | Hestia Kaoru | Docker, VPS, CI/CD |
| 9 | QA | Themis Saori | test plan, automation |
| 10 | Security | Argus Hayato | threat model, audit |
| - | Senior mentor | Hephaestus Takumi | code review |

---

## ดูสถานะปัจจุบัน

- **Project Charter:** [docs/project/project-charter.md](docs/project/project-charter.md)
- **Roadmap:** [docs/project/roadmap.md](docs/project/roadmap.md)
- **Architecture:** [docs/architecture/system-architecture.md](docs/architecture/system-architecture.md)
- **ADRs:** [docs/architecture/adr/](docs/architecture/adr/)
- **Database Schema:** [docs/database/schema.md](docs/database/schema.md)
- **API Spec:** [docs/api/openapi.yaml](docs/api/openapi.yaml)
- **Strategy Specs:** [docs/strategies/](docs/strategies/)
- **Threat Model:** [docs/security/threat-model.md](docs/security/threat-model.md)
