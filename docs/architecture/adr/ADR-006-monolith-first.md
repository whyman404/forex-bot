# ADR-006 — Monolith First (Modular Monolith)

**Status:** Accepted
**Date:** 2026-06-14
**Decider:** Daedalus Souta
**Related:** ADR-002 (Monorepo), ADR-003 (Stack), ADR-004 (Deploy)

---

## Context

ต้องตัดสินใจ deployment style ของ backend logic — เป็น single service (monolith), หลาย service (microservices), หรือ serverless

**Constraints:**
- ทีม 1 unit (10 specialists) — Conway's Law: 1 service ตามชั้น
- Phase 1–2 target: <50 active users
- Phase 1 budget: $35/mo infra
- ต้องการความเร็วในการ ship + เปลี่ยน contract ได้ง่าย
- Trading Engine + MT5 Bridge ต้อง collocated บน Windows VPS อยู่แล้ว (ADR-001)

---

## Decision

**Backend = Modular Monolith.**
- ทุก domain context (auth, user, strategy, backtest, billing, broker_credential, trading, notification, admin) อยู่ใน FastAPI app เดียวกัน
- บังคับ **module boundary ที่ code level** — แต่ละ module = Python package แยก, สื่อสารผ่าน explicit interface (no cross-import internal)
- **Trading Engine + MT5 Bridge** = แยก process / VM (เพราะอยู่ Windows + collocate กับ MT5) — แต่นี่คือ "process boundary by hardware constraint" ไม่ใช่ premature microservice
- **Backtest Runner** = แยก process pool บน Linux (long-running CPU job) แต่ยัง share codebase + database

**Module structure (in `backend/src/forex_bot/`):**
```
forex_bot/
├── api/                     # FastAPI app + routers (composition layer)
├── modules/
│   ├── auth/                # bounded context
│   │   ├── __init__.py      # public interface exports
│   │   ├── domain/          # entities, value objects
│   │   ├── application/     # use cases
│   │   ├── adapters/        # repos, external clients
│   │   └── http/            # routers
│   ├── user/
│   ├── broker_credential/
│   ├── strategy/
│   ├── backtest/
│   ├── trading/
│   ├── billing/
│   ├── notification/
│   └── admin/
├── shared/                  # cross-cutting (logging, config, db session)
└── crypto/                  # vault (ADR-005)
```

**Boundary enforcement:**
- Import linter rule: `modules/X` ห้าม import `modules/Y/domain` หรือ `modules/Y/application` ตรง ๆ
- ใช้ `modules/Y/__init__.py` ที่ export เฉพาะ public API (service class)
- Cross-module call = dependency injection ของ service interface

---

## Alternatives Considered

### Alt 1 — Microservices from Day 1
แยก `auth-svc`, `strategy-svc`, `billing-svc`, etc.

**Rejected เพราะ:**
- 1 team — Conway's Law บอกว่าควรมี 1 deployable
- Distributed transaction = pain (saga, idempotency, eventual consistency overhead)
- Local dev loop ช้า (run 5+ services)
- Operational cost ↑ (deploy 5×, monitor 5×, networking 5×)
- เปลี่ยน API contract = cross-service migration ทุกครั้ง
- "Microservices premium" (Fowler) — pay cost for benefit we won't realize at this scale

### Alt 2 — Serverless (AWS Lambda + DynamoDB)
Function-per-endpoint + managed DB

**Rejected เพราะ:**
- Cold start kills trading latency
- Trading Engine คือ long-running loop ไม่ใช่ event-driven function
- DynamoDB ไม่เหมาะ analytical query (per-user PnL aggregation)
- Vendor lock-in สูงกว่า; cost predictability แย่
- ทีมไม่มี serverless ops experience

### Alt 3 — One Big File / Script
ไม่มี module structure, ทุกอย่างใน flat folders

**Rejected เพราะ:**
- AI assistant ช่วยเพิ่ม code volume → ต้องการ structure ชัดเจนยิ่งกว่า (insight Daedalus 2026-05-05)
- Refactor / find ownership ลำบาก
- Module boundary คือ option ที่ **ทำได้ฟรี ตั้งแต่วันแรก**

---

## When to Reconsider (Split Triggers)

แสดงเป็น **explicit gates** — ถ้าถึง trigger ค่อย propose ADR-XXX สำหรับ split

| Trigger | Threshold | Likely split |
|---------|-----------|--------------|
| Team scale | >2 distinct teams contributing to backend | extract their domain |
| User scale | >500 concurrent users | extract trading hot path |
| Deploy friction | merge conflicts > 3/week on monolith | extract isolated modules |
| Performance | backtest runner CPU starves API > 20% time | already separate process; ok |
| Compliance | PCI/SOC2 audit requires isolated billing | extract billing |
| Latency | one module's GC pause hurts another | extract latency-critical |

**Not triggers (don't split for these):**
- "Resume / microservices is cool"
- "Different language for this part" (push back; standardize)
- "We might scale someday" — YAGNI

### Likely Future Splits (when triggers hit)
- `trading-engine/` (already separate process by hardware) → could become true service
- `billing/` (compliance) → separate service when SOC2 in scope
- `notification/` (rate limit, retry, multi-channel) → fits as service early

---

## Consequences

### Positive
- **Single deploy** — atomic rollback, no cross-service version skew
- **Local dev**: `docker compose up` → entire stack in 30s
- **Refactor easy** — boundary at code level = move modules ระหว่าง folder ได้ free
- **One DB transaction** spans modules — no saga
- **Cheap** — 1 VPS, 1 process tree, 1 set of metrics
- **Fast onboarding** — new dev reads 1 codebase

### Negative / Trade-off
- **Coupled deploy** — bug in admin module = redeploy whole API (mitigation: tests + canary)
- **Module discipline** depends on team — without enforcement, monolith → big ball of mud (mitigation: import-linter, code review, ADR mention in PR template)
- **Scaling unit = whole app** — can't scale strategy module independent of admin (mitigation: most modules are I/O-bound; vertical scale ก่อน)
- **One language for backend** — ไม่ใช่ปัญหาที่นี่ (Python ทุก service อยู่แล้ว)

### Risk Mitigation
- **Import linter** in CI — prevent cross-module sneak imports
- **Module README** — each `modules/X/README.md` documents public interface + invariants
- **Quarterly review** — Daedalus + Hephaestus look at coupling map, propose split if needed
- **Trace IDs** — even monolith, structured logging with module label = easy to extract later

---

## Decision Record Update Trigger
Re-evaluate this ADR when:
- Active users > 100
- Team size > 15 contributors to backend
- Annual cloud bill > $500/mo
- Any compliance trigger above hits

---

## References
- Sam Newman — "Monolith to Microservices"
- Shopify engineering — modular monolith case study
- Martin Fowler — "MonolithFirst" (2015): https://martinfowler.com/bliki/MonolithFirst.html
- Simon Brown — "Modular Monolith" talks
- DHH — "The Majestic Monolith"
