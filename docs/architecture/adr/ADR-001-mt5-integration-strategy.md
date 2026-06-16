# ADR-001 — MT5 Integration Strategy

**Status:** Accepted
**Date:** 2026-06-14
**Decider:** Daedalus Souta (with input from Kairos Toki, Argus Hayato)
**Related:** ADR-004 (Deployment), ADR-005 (Secrets)

---

## Context

แพลตฟอร์มต้องเทรดผ่าน Exness ซึ่งเป็น broker ที่ใช้ MT5 (MetaTrader 5) เป็น platform หลัก ตัวเลือกสำหรับการเชื่อมระบบเราเข้ากับ MT5 ของ user มีจำกัด:

**Constraint:**
- Exness ไม่เปิด REST/FIX API trade ตรงสำหรับ retail tier (ต้องผ่าน MT5)
- เราต้องการ **central web UI** ให้ user คุม strategy จาก dashboard (ไม่ใช่ login เข้า MT5 ของตัวเองทุกครั้ง)
- ต้องการ **central backtest + signal generation** บน server เรา (ไม่กระจาย logic ไปแต่ละ MT5)
- ต้องการ **membership/billing** ผูกกับ flag enable/disable strategy
- Phase 1 target: <50 active live-trading users
- Team skill: Python heavy, MQL5 ไม่เคยทำ

---

## Decision

**ใช้ `MetaTrader5` Python package บน Windows VPS, แบบ pool of headless terminals — 1 terminal ต่อ active user (login ด้วย credential ของ user)**

โครงสร้าง:
- Windows VPS รัน **MT5 Bridge Service** (Python FastAPI ขนาดเล็ก) เป็นตัวกลาง expose RPC endpoint
- Bridge จัดการ "terminal pool" — โหลด `MetaTrader5` package ใน sub-process ต่อ user
- เมื่อ user เปิด strategy → bridge ensure terminal ของ user นั้น login อยู่ → strategy runner (collocated) ใช้ bridge ส่ง order
- Bridge เปิดเฉพาะ private VPN (WireGuard) + mTLS — backend FastAPI เป็น client เท่านั้น

**Per-user terminal mapping:**
```
user_id  →  MT5 terminal (sub-process / data dir)  →  Exness account (login/server/password)
```

ผูกความสัมพันธ์เป็น "affinity" — user_A จะ pinned กับ terminal slot บน VPS ตัวเดิม (sharding by user_id)

---

## Alternatives Considered

### Alt 1 — MQL5 EA Only (Distributed Logic)
แต่ละ user ลง EA (Expert Advisor) บน MT5 ของตัวเอง logic ทั้งหมดอยู่ใน MQL5

**Rejected เพราะ:**
- ไม่มี central UI — ต้องให้ user config ผ่าน MT5 input (UX แย่)
- ไม่มี membership gate — EA copied ออกไปได้ ไม่มี server-side enforce paid
- backtest, ML, optimization ทำใน MQL5 ลำบาก (ภาษาจำกัด)
- update strategy ต้อง push EA ใหม่ไปทุก user
- ทีมไม่มี MQL5 expertise → ramp-up cost สูง

### Alt 2 — Hybrid (Server signal + EA execute)
Server ส่ง signal ไปยัง EA ที่ user รัน, EA เป็นแค่ executor

**Rejected เพราะ:**
- 2x complexity (ทั้ง Python และ MQL5 codebase + integration layer)
- ยังต้องการ network/messaging ที่ user setup ได้เอง (webhook/HTTP จาก EA → MQL5 webRequest)
- failure mode เยอะ (EA crash, server-side replay, idempotency แย่)
- ROI ไม่ชัด — ได้แค่ลด VPS cost ฝั่งเรา แต่ขาดข้อมูล real-time state

### Alt 3 — Mac/Linux ผ่าน Wine
Run MT5 บน Linux ผ่าน Wine, ใช้ `MetaTrader5` Python ผ่าน Wine layer

**Rejected เพราะ:**
- ไม่ stable — Wine + MT5 มี reported issues หลายกรณี
- official MetaQuotes ไม่ support
- failure root-cause ยาก (Wine quirks หรือ MT5 หรือ Python?)
- production risk ไม่คุ้ม saving ~$20/mo

### Alt 4 — cTrader / Other Brokers
เปลี่ยน broker ที่มี REST API พื้นเมือง (เช่น OANDA, FXCM)

**Rejected ตอนนี้ เพราะ:**
- ลูกค้าเป้าหมาย (TH/SEA) ใช้ Exness เป็นหลัก
- spread / leverage ที่ Exness แข่งขันได้
- เก็บไว้เป็น option Phase 4 (broker_adapter abstraction รองรับ)

---

## Consequences

### Positive
- Central UI + membership control ได้เต็มที่ — paid gate enforce ที่ server เรา
- Logic เขียน Python ล้วน — team productive ตั้งแต่วันแรก
- Backtest + live ใช้ codebase เดียวกัน (Backtrader/vectorbt → MT5 adapter)
- Update strategy ทันที — แค่ deploy bridge/engine ใหม่
- Audit log central — กฎหมาย + dispute handling ง่ายกว่า EA

### Negative / Trade-off
- **ต้องการ Windows VPS** เพิ่ม cost ($20/mo, Contabo VPS M)
- **Scale ceiling:** ประมาณ 50 terminals ต่อ Windows VPS (6vCPU, 16GB) — แต่ละ terminal กิน ~150-250MB RAM idle, CPU spike เมื่อ tick
- **MetaQuotes ไม่ใช่ public API formal** — เปลี่ยนได้ในอนาคต (mitigation: pin MT5 build, monitor changelog)
- **Single point of failure** — Windows VPS down = trading ทั้งหมด pause (mitigation: standby VPS, alert, manual failover)
- **Credential ของ user อยู่บน VPS เรา** — เพิ่ม responsibility ด้าน security (ดู ADR-005)
- **Latency overhead** ~50-150ms ต่อ order (RPC + terminal call) — ยอมรับได้สำหรับ M5+ strategies, ไม่เหมาะ scalping <1min

### Scale Plan
| Stage | Users | Topology |
|-------|-------|----------|
| Phase 1 | <10 paper | 1 Windows VPS, shared dev terminal |
| Phase 2 (MVP) | <20 live | 1 Windows VPS (Contabo VPS M) |
| Phase 3 | 20-50 | 1 Windows VPS upgraded (Contabo XL) or add 2nd |
| Phase 3+ | 50-150 | sharded — 2-3 Windows VPS by user_id hash |
| Phase 4 | >150 | re-evaluate: consolidate to Windows Server Datacenter / managed hosting / broker direct API |

### Cost Projection
- Phase 1–2: $20/mo (1 VPS)
- Phase 3: $20-60/mo (1-3 VPS)
- Per-user marginal cost (VPS only) at scale: ~$0.40-1.00/mo/user

### Failover Strategy
1. **Bridge health check** every 10s from backend; alert if 3 fails
2. **Terminal-level heartbeat** — แต่ละ terminal report tick/sec; bridge restarts ถ้า silent >2min
3. **Standby VPS** — snapshot weekly; cold standby ใน region อื่น ($20/mo extra at Phase 3)
4. **User-side communication** — เมื่อ pause, in-app banner + email; user สามารถ disable strategy ของตัวเองก่อนที่จะ resume

---

## Operational Notes
- Pin MT5 build version; test new build in staging ก่อน rollout
- Credential ต้อง pull จาก KV ตอน login + zeroize buffer หลัง (ดู ADR-005)
- Log ห้ามมี password/server แม้แต่ครั้งเดียว — `LogFilter` ที่ bridge ระดับ Python logger
- Disaster recovery test — quarterly: simulate VPS loss, verify standby switchover < 30 min

---

## References
- MetaQuotes Python integration docs (official): https://www.mql5.com/en/docs/python_metatrader5
- Internal: `docs/strategies/` (Kairos)
- Internal: `docs/security/threat-model.md` (Argus)
