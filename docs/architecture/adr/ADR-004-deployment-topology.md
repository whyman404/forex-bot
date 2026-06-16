# ADR-004 — Deployment Topology

**Status:** Accepted
**Date:** 2026-06-14
**Decider:** Daedalus Souta (with Hestia Kaoru, Zeus Ryujin)
**Related:** ADR-001 (MT5), ADR-005 (Secrets)

---

## Context

ต้อง deploy:
- App plane: Next.js + FastAPI + Postgres + Redis + observability
- Trading plane: MT5 Bridge + Trading Engine + MT5 terminal pool (Windows-only)
- Crypto path (Binance via ccxt) — Linux compatible

**Constraints:**
- Phase 1–2 budget: $50/mo infra
- Target users: <50 active
- ต้อง latency MT5 → Exness ต่ำ (Exness server มักอยู่ EU)
- ทีมไม่มี K8s ops experience — keep it simple

---

## Decision

### Phase 1–2 Topology

```
┌─────────────────────────────────────────────────────────┐
│ Linux VPS — Hetzner CX31 (Falkenstein/Helsinki)         │
│ 2 vCPU, 8 GB RAM, 80 GB SSD, ~$15/mo (€14.80)           │
│                                                         │
│  Caddy ──► Next.js (3000)                               │
│         ──► FastAPI (8000, uvicorn × 4 workers)         │
│                                                         │
│  arq Worker, Backtest Runner (on-demand)                │
│  Postgres 16, Redis 7                                   │
│  Prometheus + Grafana + Loki                            │
│  Caddy provides auto-TLS via Let's Encrypt              │
└──────────────┬──────────────────────────────────────────┘
               │ WireGuard tunnel (10.42.0.0/24)
               │ + mTLS on app layer
               ▼
┌─────────────────────────────────────────────────────────┐
│ Windows VPS — Contabo VPS M (EU)                        │
│ 6 vCPU, 16 GB RAM, 400 GB SSD, ~$20/mo                  │
│                                                         │
│  MT5 Bridge Service (FastAPI, port 9100 over VPN)       │
│  Trading Engine Worker (collocated for latency)         │
│  MT5 terminal pool — up to ~50 instances                │
│  NSSM = service manager for terminals + bridge          │
└─────────────────────────────────────────────────────────┘
                  │
                  ▼
            Exness MT5 Server (broker network)
```

**Region choice:** ทั้ง Linux + Windows VPS ใน EU เพื่อให้ใกล้ Exness server (มัก EU/Cyprus) → ลด order latency

**Domain:**
- `app.<domain>` → Next.js (via Caddy)
- `api.<domain>` → FastAPI (via Caddy)
- `grafana.<domain>` → Grafana (basic auth)
- Bridge — **ไม่มี public DNS**; VPN-only

### Phase 3 Scale Plan (>20 active users)
- Linux VPS: upgrade Hetzner CX41 (4 vCPU, 16 GB) ~$30/mo
- Windows VPS: add 2nd Contabo (sharding by user_id % 2)
- DB: keep on Linux primary; add read replica เมื่อ p95 query > 50ms
- Cloudflare in front (CDN + WAF + DDoS) — free tier

### Phase 4 (>150 users)
- Re-evaluate: Hetzner dedicated, managed Postgres (Crunchy Data), K8s only ถ้ามี SRE

---

## Alternatives Considered

### Alt 1 — Exness Free VPS
Exness ให้ free VPS แก่ลูกค้าที่มี balance >$500 หรือ deposit เกินกำหนด

**Rejected เพราะ:**
- Free VPS เป็น **per-user** (user แต่ละคนได้ของตัวเอง) — เราต้องการ central infrastructure
- Free VPS ผูกบัญชี — user ต้องเป็นคน setup → ไม่ scale, UX แย่
- เราไม่มีสิทธิ์ admin ระดับ root → install monitoring/agent ลำบาก
- ถ้า user ถอนเงินต่ำกว่า threshold → Free VPS ถูกตัด → trading หยุด
- **อาจเหมาะกับ EA-only model (ADR-001 Alt 1)** ซึ่งเรา reject ไปแล้ว

### Alt 2 — AWS / GCP / Azure
Managed cloud

**Rejected ตอนนี้ เพราะ:**
- Linux equivalent ~$30-40/mo (EC2 t3.medium + EBS + bandwidth) = 2x cost
- Windows EC2 ~$60-80/mo for similar spec = 3-4x cost
- ทีมไม่มี FinOps experience — surprise bill risk
- เก็บไว้เป็น option Phase 4 เมื่อต้องการ managed RDS, S3, IAM-grade security
- **Reversible**: docker-compose + Terraform → migrate ได้ภายหลัง

### Alt 3 — Vercel + Supabase + Windows VPS
Vercel host Next.js, Supabase host Postgres + auth + storage, Windows VPS only for MT5

**Rejected ตอนนี้ เพราะ:**
- Vercel function timeout ไม่เหมาะ backtest job
- Supabase free tier จำกัด (500MB DB, 2GB transfer) — bump to Pro = $25/mo
- รวมแล้ว ~$45/mo + Windows VPS = ใกล้เคียง self-host แต่ lock-in สูงกว่า
- ตัด option ถ้าวันหนึ่ง user data ต้องอยู่ TH (PDPA compliance)

### Alt 4 — Kubernetes (DO, Linode LKE)
K8s managed cluster + Windows node

**Rejected ตอนนี้ เพราะ:**
- Managed K8s + Windows worker = ~$80-150/mo
- Operational overhead (Helm, ingress, secrets) — ไม่คุ้มที่ <50 users
- Premature distribution
- Path มี: dockerize ทุกอย่างใน Phase 1 → migrate K8s ได้ภายหลัง

---

## Consequences

### Positive
- Total infra cost Phase 1–2: **~$35/mo** ($15 Linux + $20 Windows)
- Simple mental model — 2 VPS, ssh-able
- ทีมมีของจริงไม่ใช่ abstraction หลายชั้น
- Backup เป็น file/snapshot — ง่ายต่อ recovery test

### Negative / Trade-off
- **Single Linux VPS = single point of failure** for app plane (mitigation: snapshot + provider-level migration plan documented; commit to upgrade path ที่ Phase 3)
- **No autoscale** — manual upgrade VPS เมื่อ load สูง
- **Snowflake risk** — config drift บน VPS (mitigation: Ansible playbook ใน `infra/`)
- **Backup ความรับผิดชอบเอง** — pg_dump nightly → Backblaze B2 ($0.005/GB/mo)
- **Windows VPS == manual-feeling** — Hestia ต้อง expertise ใน Win Server ops

### Cost Projection
| Phase | Linux | Windows | Backup/Storage | DNS/CDN | Total |
|-------|-------|---------|----------------|---------|-------|
| 1 | $15 | $20 | ~$2 | $0 (CF free) | **~$37/mo** |
| 2 | $15 | $20 | ~$3 | $0 | **~$38/mo** |
| 3 | $30 | $40 (×2) | ~$5 | $0 | **~$75/mo** |
| 4 | $80 | $80-150 | $20 | $20 | **~$200+/mo** |

### Backup & DR
- **RPO 1h** — Postgres WAL archive every 5 min → B2 (Phase 2+)
- **RTO 4h** — runbook: provision new VPS (Ansible) + restore B2 backup
- Quarterly DR drill — `infra/runbooks/dr-drill.md`

### Monitoring
- Prometheus scrape — node_exporter, postgres_exporter, redis_exporter, FastAPI `/metrics`
- Alertmanager → Discord webhook (Hestia + on-call)
- Grafana dashboards: system, business KPI, MT5 bridge health

### Network Security
- Linux VPS firewall (ufw): ports 22, 80, 443 only; 22 from admin IPs
- Windows VPS firewall: RDP only from admin IP; bridge port 9100 only from VPN
- WireGuard tunnel: 10.42.0.0/24, Linux = 10.42.0.1, Windows = 10.42.0.2
- mTLS on bridge — backend client cert required

---

## Open Items
- [ ] Choose B2 vs Cloudflare R2 for backup (R2 free egress > 0 but B2 cheaper at-rest) — Hestia decide
- [ ] Pick Contabo region (Düsseldorf vs Munich) — measure ping to Exness from each
- [ ] Cloudflare account setup (whyman404@gmail.com) — Zeus

---

## References
- Hetzner Cloud: https://www.hetzner.com/cloud
- Contabo Windows VPS: https://contabo.com/en/vps/windows-vps/
- Caddy: https://caddyserver.com/
- WireGuard: https://www.wireguard.com/
