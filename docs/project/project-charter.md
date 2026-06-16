# Project Charter — Forex/Crypto Trading Bot Platform

**Project Code:** FBP-2026
**Charter Owner:** Zeus Ryujin (PM)
**Sponsor:** whyman404@gmail.com
**Charter Date:** 2026-06-14
**Status:** APPROVED — execution starts 2026-06-15
**Version:** 1.0

---

## 1. Vision

> "ให้คนทั่วไปเข้าถึง systematic trading ที่มี edge ทาง statistics อย่างมืออาชีพ โดยไม่ต้องเขียนโค้ดเอง — ผ่าน UI ใช้งานง่าย + กลยุทธ์ที่ผ่าน rigorous backtest + ความโปร่งใส 100%"

เราไม่ขายฝัน "รวยเร็ว" เราขาย **discipline + execution + transparency** ที่นักเทรดรายย่อยทำเองได้ยาก.

---

## 2. Problem Statement

**Pain Points ที่เราแก้:**
1. นักเทรดรายย่อย ~80% ขาดทุนเพราะ emotion + ไม่มี edge ที่ backtest แล้ว
2. การสร้าง bot เองต้องใช้เวลา 6-12 เดือนเรียน Python/MQL5 + statistics
3. Bot ที่ขายในตลาด overfit / hide drawdown / ไม่เปิดเผย metric จริง
4. คนใช้ Exness + MT5 อยู่แล้ว แต่ไม่อยากจ่ายค่า signal service ที่ไม่มี audit

**Opportunity:** ตลาด retail algo trading ใน SEA โต > 30% YoY (2024-2026). ผู้ใช้ Exness ใน TH/MY/VN/PH > 500K active.

---

## 3. Success Metrics

### 3.1 Technical Success (Bot Performance) — **COMMITTED**

| Metric | Target | Rationale |
|--------|--------|-----------|
| **Profit Factor (PF)** | **> 1.5** | Professional baseline. PF = gross profit / gross loss |
| **Max Drawdown (MaxDD)** | **≤ 20%** | Account survival ceiling. Above 25% → margin call risk |
| **Sharpe Ratio (annualized)** | **> 1.0** | Risk-adjusted return must beat passive index |
| **Positive expectancy** | **> 0 per trade** | (avg win × win%) − (avg loss × loss%) must be positive |
| **Calmar Ratio** | **> 0.5** | Annualized return / MaxDD — ensures DD compensated |

### 3.2 IMPORTANT — Win Rate Education

> ผู้ใช้เดิมขอ **win rate 95%** — ทีมไม่สามารถ commit ได้ และนี่คือเหตุผล:

**ข้อเท็จจริงจาก data:**
- กลยุทธ์ breakout / momentum (London Breakout, NY Killzone, EMA+ADX, Donchian, EMA Cross+RSI) มี **natural win rate 35-55%** — แต่ profitable ได้เพราะ **Risk:Reward > 1:1.5 ถึง 1:3**
- กลยุทธ์ Grid Bot สามารถมี win rate > 90% **เฉพาะถ้าไม่มี Stop Loss** — แต่ 1 ครั้งที่ตลาด trend แรง (เช่น BTC dump 30% ใน 1 วัน, USD shock) จะ **wipe out account ทั้งหมด** = "picking pennies in front of a steamroller"
- Bot ที่อ้าง win rate 95% บนเว็บคือ scam หรือ hide DD

**สิ่งที่ทีม commit:**
- เรา **report ทุก metric** (win rate, PF, Sharpe, MaxDD, RR, expectancy) ในทุก backtest + live report ให้ user เห็นด้วยตาตัวเอง
- เป้าหมายจริงคือ **profit factor + risk control** ไม่ใช่ winrate
- ถ้า user ต้องการ winrate สูงโดยรับ DD risk สูง — เปิด Grid Bot โหมด "no SL" ได้ แต่ต้องเซ็น **risk acknowledgment** ในแอป

**Decision (Zeus):** ใช้ PF/Sharpe/DD เป็น KPI หลักทั้งโปรเจกต์. Winrate แสดงเป็น informational metric เท่านั้น.

### 3.3 Business Success (SaaS Metrics) — Phase 2+

| Metric | Phase 2 Target | Phase 3 Target |
|--------|----------------|----------------|
| Active subscribers | 50 (paid trial) | 500 paid |
| MRR | $2,500 | $25,000 |
| Churn (monthly) | < 15% | < 8% |
| NPS | > 30 | > 50 |
| CAC payback | < 6 mo | < 4 mo |

### 3.4 Delivery Success (Phase 1)

- M1 (W2): Design freeze, all ADRs signed
- M2 (W4): Backtest of 6 strategies passes PF>1.5 on 3yr OOS data
- M3 (W6): Paper trading running 7 consecutive days, zero P1 incident

---

## 4. Scope

### 4.1 IN SCOPE (Phase 1 — 6 weeks)

**Trading Engine**
- 6 mechanical strategies wired:
  - Gold: London Breakout, NY Killzone Reversal, EMA50+ADX trend
  - BTC: EMA Cross+RSI, Donchian Breakout, Grid Bot (with SL)
- Backtest framework (vectorbt + backtrader)
- Walk-forward analysis + out-of-sample validation
- MT5 broker adapter (Exness)
- Binance adapter (ccxt) for crypto
- Order management system (OMS) — position sizing, SL/TP, partial close
- Paper trading mode

**Backend**
- FastAPI service skeleton
- User auth (NextAuth.js + JWT)
- Strategy config CRUD
- Backtest job runner (async with Redis queue)
- Trade event store (PostgreSQL)
- Webhook receiver for MT5 events

**Frontend**
- Landing page
- Login / register
- Dashboard: equity curve, open positions, P&L
- Strategy config UI (start/stop, params)
- Backtest report viewer

**Infra**
- Docker compose (dev)
- Windows VPS provisioned for MT5
- Linux VPS for backend + frontend
- GitHub Actions CI
- Sentry + Prometheus + Grafana skeleton

**Compliance & Risk**
- Risk acknowledgment flow (user must accept before live trading)
- Terms of Service + Privacy Policy draft
- Disclaimer page

### 4.2 OUT OF SCOPE (Phase 1)

- ❌ Live trading with real money (Phase 2)
- ❌ Stripe / Omise payment integration (Phase 2)
- ❌ Multi-broker beyond Exness (Phase 3+)
- ❌ Mobile app (Phase 3+)
- ❌ Social / copy trading (Phase 4)
- ❌ ML-based strategies (Phase 4)
- ❌ Multi-language UI (Phase 3) — English + Thai only at launch
- ❌ Tax reporting export (Phase 3)
- ❌ Broker license / IB partnership negotiation (separate workstream)
- ❌ Custom strategy builder for end users

---

## 5. Assumptions

1. User provides Exness real / demo account credentials (testing in Phase 1 uses demo only)
2. Windows VPS budget approved up to $40/mo for MT5 hosting
3. Linux VPS budget approved up to $30/mo for backend+frontend (Hetzner CPX21 class)
4. Historical tick data for Gold + BTC last 3 years is sourceable (Dukascopy or broker history)
5. User is sole decision authority — no committee approval needed for technical decisions
6. Team works async, 7-day sprint cadence
7. No regulatory blocker exists for **personal automation of own account** in Thailand (Phase 1)
8. SaaS launch (Phase 2+) will trigger legal review — not blocking Phase 1

---

## 6. Constraints

| Type | Constraint |
|------|-----------|
| **Time** | Phase 1 = 6 weeks hard ceiling (ends 2026-07-26) |
| **Budget** | Hosting ≤ $100/mo Phase 1; ≤ $500/mo Phase 2 |
| **Tech** | MT5 = Windows only → Windows VPS mandatory |
| **Tech** | Exness rate limit on tick API (assume 5 req/sec safe) |
| **Tech** | MetaTrader5 Python pkg only runs on Windows |
| **Legal** | Cannot custodial-hold user funds (broker keeps funds) |
| **Legal** | Must include investment risk disclaimer per Thai SEC guideline |
| **Team** | 10 specialists + 1 mentor, all async |

---

## 7. Stakeholders

| Stakeholder | Role | Interest | Influence | Communication Cadence |
|-------------|------|----------|-----------|----------------------|
| whyman404 | Project owner / sponsor / first user | HIGH | HIGH (final say) | Weekly status report + ad-hoc decisions |
| Zeus Ryujin | PM | HIGH | HIGH | Daily standup |
| Daedalus | Architect | HIGH | HIGH | Daily standup + ADR review |
| Kairos | Quant | HIGH | HIGH | Daily + strategy review |
| Other specialists | Build team | HIGH | MEDIUM | Daily standup |
| Hephaestus | Mentor | MEDIUM | MEDIUM | Weekly code review |
| End users (future) | SaaS customers | HIGH | LOW (Phase 1) | N/A Phase 1, beta survey Phase 2 |
| Exness | Broker (counterparty) | LOW | MEDIUM | Email if rate limit / ToS question |
| Thai SEC | Regulator | LOW | HIGH (future) | Monitor announcements |

---

## 8. Top 5 Risks (preview — see risk-register.md for full)

| # | Risk | Prob | Impact | Mitigation Summary |
|---|------|------|--------|---------------------|
| R1 | Strategy overfit → live ≠ backtest | HIGH | HIGH | Walk-forward + OOS + paper trading gate |
| R2 | MT5 Windows VPS instability / disconnects | MEDIUM | HIGH | Heartbeat + auto-reconnect + alert + backup VPS |
| R3 | User real-money loss → lawsuit / reputation | MEDIUM | CRITICAL | Disclaimer + risk ack + demo-first + DD cap |
| R4 | Exness ToS violation (algo / IP blocking) | LOW | HIGH | Read ToS day 1; rate limit; allowed |
| R5 | Regulatory shift in TH (algo trading restriction) | LOW | CRITICAL | Monitor SEC, ready to geo-block, Phase 2 legal review |

---

## 9. Decision Authority (RACI summary)

| Decision Type | Authority |
|---------------|-----------|
| Project scope change | Zeus (consult sponsor if > 1 week impact) |
| Tech architecture | Daedalus (Zeus arbitrates conflict) |
| Strategy parameters | Kairos (Zeus arbitrates if affects timeline) |
| UI/UX | Iris (Zeus arbitrates if affects scope) |
| Security baseline | Argus (NON-NEGOTIABLE — Argus can veto release) |
| Database schema | Mnemosyne |
| Infra spend | Hestia ≤ $50/mo; > $50 → Zeus |
| Sprint priority | Zeus |
| Release Go/No-Go | Zeus + Themis + Argus (unanimous) |
| Sponsor escalation | Zeus only |

**Sponsor (whyman404)** retains veto on: scope change > 1 week, budget > $500/mo, public launch decision.

---

## 10. Kill Criteria (when to stop or pivot)

Project will be **paused for sponsor decision** if ANY of these triggers:

1. **K1 — Strategy fail:** After M2 (W4), no strategy hits PF>1.5 on OOS 3yr data even after Kairos iteration
2. **K2 — Tech blocker:** MT5 integration cannot achieve < 500ms latency or > 99% uptime on test VPS by W3
3. **K3 — Regulatory:** Thai SEC publishes binding rule that prohibits retail algo SaaS without broker license
4. **K4 — Budget overrun:** Phase 1 hosting > 150% of $100/mo budget
5. **K5 — Team capacity:** Any 2 critical specialists (Daedalus, Kairos, Atlas, Hestia) become unavailable simultaneously > 1 sprint
6. **K6 — Sponsor loss of confidence:** Sponsor explicitly requests halt

**Pivot options if killed:**
- A) Pivot to manual signal service (no auto-execution) — easier compliance
- B) Pivot to "indicator library + alerts" only (no order placement)
- C) Open-source the engine, monetize through education

---

## 11. Definition of Done — Phase 1

Phase 1 is DONE when:
- [ ] 6 strategies implemented + unit tested
- [ ] Backtest passes PF>1.5, MaxDD≤20%, Sharpe>1.0 on 3yr OOS for at least 4 of 6 strategies
- [ ] Paper trading runs 7 consecutive days with zero P1 incident
- [ ] Frontend dashboard shows live equity, positions, P&L
- [ ] User can configure + start/stop strategy from UI
- [ ] CI green on main branch
- [ ] Disclaimer + ToS + Risk Acknowledgment flow shipped
- [ ] All ADRs signed by Daedalus + Zeus
- [ ] Themis acceptance test pack green
- [ ] Argus security baseline checklist green (no critical findings)

---

## 12. Sign-off

| Role | Name | Decision | Date |
|------|------|----------|------|
| PM | Zeus Ryujin | APPROVED | 2026-06-14 |
| Sponsor | whyman404 | AUTHORIZED (autonomous execution) | 2026-06-14 |
| Architect | Daedalus | (to sign after first ADR review) | TBD W1 |
| Quant | Kairos | (to sign after strategy specs ratified) | TBD W1 |

---

**Charter Authority:** This charter is the source of truth for Phase 1. Changes require change request approved by Zeus. Sponsor will be notified within 24h of any approved scope change.

_— Zeus Ryujin, 2026-06-14_
