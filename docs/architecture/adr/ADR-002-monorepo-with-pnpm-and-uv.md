# ADR-002 — Monorepo with pnpm workspaces + uv

**Status:** Accepted
**Date:** 2026-06-14
**Decider:** Daedalus Souta (with input from Hestia Kaoru)
**Related:** ADR-003 (Tech Stack), ADR-006 (Monolith-first)

---

## Context

โปรเจกต์มีหลาย logical components:
- `frontend/` — Next.js 15 (TypeScript)
- `backend/` — FastAPI (Python)
- `trading-engine/` — Python (รันบน Windows VPS + parts บน Linux)
- `infra/` — Docker, Terraform, scripts
- `docs/` — Markdown documentation
- (future) `shared-types/` — OpenAPI generated types สำหรับ frontend จาก backend schema

**Constraints:**
- ทีม 10 specialists, 1 codebase, atomic feature ส่วนใหญ่ครอบหลาย layer
- ต้องการ atomic refactor ข้าม language (เช่น เปลี่ยน API contract → frontend type ต้อง regen ทันที)
- CI ต้องรู้ว่า PR เปลี่ยน frontend อย่างเดียวก็ไม่ต้องรัน backend tests
- Onboard new dev — checkout เดียวจบ

---

## Decision

**Monorepo ที่ `projects/forex-bot/` ใช้:**
- **pnpm workspaces** สำหรับ JS/TS (`frontend/`, future `shared-types/`, future `eslint-config/`)
- **uv** สำหรับ Python (`backend/`, `trading-engine/`)
- **Make** + **Just** (taskfile) เป็น cross-language task runner ที่ root
- **GitHub Actions** ใช้ **path filter** เพื่อรัน job เฉพาะที่กระทบ

โครงสร้าง:
```
projects/forex-bot/
├── pnpm-workspace.yaml          # JS workspace root
├── package.json                 # root deps (turbo? prettier? lint-staged?)
├── pyproject.toml               # uv workspace root (optional)
├── uv.lock
├── Justfile                     # cross-language tasks (dev, test, fmt)
├── frontend/
│   ├── package.json
│   └── ...
├── backend/
│   ├── pyproject.toml
│   ├── src/
│   └── tests/
├── trading-engine/
│   ├── pyproject.toml
│   ├── src/
│   └── tests/
├── infra/
├── docs/
└── .github/workflows/
    ├── frontend.yml             # triggers on frontend/**
    ├── backend.yml              # triggers on backend/**
    ├── trading-engine.yml       # triggers on trading-engine/**
    └── shared.yml               # docs, lint
```

**Tooling rationale:**
- **pnpm** > npm/yarn: content-addressable store ประหยัด disk, workspace native, fast
- **uv** > pip/poetry: 10-100x faster install, lockfile cross-platform, Astral team momentum
- **Just** > Make: clearer syntax, named recipes, ทำงานบน Windows ได้ดี

---

## Alternatives Considered

### Alt 1 — Polyrepo
แยก repo: `forex-bot-frontend`, `forex-bot-backend`, `forex-bot-engine`, `forex-bot-infra`

**Rejected เพราะ:**
- Atomic refactor ข้าม repo ลำบาก (เปลี่ยน API → 3 PR, ลืม 1 = drift)
- Onboard ต้อง clone หลาย repo
- CI ข้าม repo (dispatch event) ซับซ้อนกว่า path filter
- Team เดียว — ไม่มี ownership boundary ที่จะ justify การแยก
- Polyrepo ดีเมื่อมีหลายทีม / มี shared library ที่ใช้กว้าง — ยังไม่ใช่ตอนนี้

### Alt 2 — Nx / Turborepo Full-stack
ใช้ Nx/Turborepo จัดการ task graph ทั้ง JS + Python

**Rejected ตอนนี้ เพราะ:**
- Nx/Turbo เน้น JS, Python support เป็น 2nd class
- เพิ่ม learning curve โดยที่ benefit ยังไม่ชัด (เรามี ~3 packages)
- Just + path filter ใน GH Actions ก็พอแล้วในระดับ Phase 1–2
- กลับมาพิจารณาเมื่อมี >10 packages หรือ build time >5min

### Alt 3 — Single uv workspace ทุก Python project
แทนที่จะแยก `backend/pyproject.toml` กับ `trading-engine/pyproject.toml`, ใช้ workspace กลาง

**Partial accept:** จะใช้ uv workspace ใน root `pyproject.toml` เพื่อ shared dev deps (ruff, mypy, pytest) แต่แต่ละ package ยังคงมี `pyproject.toml` ของตัวเองเพื่อแยก runtime dependency (trading-engine มี MetaTrader5 ที่ Windows-only ไม่ควรอยู่ใน backend)

---

## Consequences

### Positive
- Single PR สำหรับ end-to-end feature
- Onboard: `git clone` + `just bootstrap` ครั้งเดียว
- Shared tooling: 1 set ของ ruff/mypy config, 1 set ของ eslint/prettier
- CI path filter — feedback loop เร็ว
- Refactor + rename ข้าม language ทำได้ใน IDE เดียว

### Negative / Trade-off
- **Repo size โต** — clone นานขึ้น (mitigation: partial clone, sparse checkout ถ้าจำเป็น)
- **CI complexity** — ต้อง maintain path filter rules
- **Permissioning หยาบ** — ถ้าวันหนึ่งอยาก open-source frontend แต่ keep backend private จะลำบาก (mitigation: ใช้ `git filter-repo` แยกตอนนั้น)
- **Cross-cutting concern ระเบิด** — เปลี่ยน root config กระทบทั้ง repo (mitigation: code owners + protected files)
- **Tooling fragmentation** — Python uses uv, JS uses pnpm, glue ด้วย Just (mitigation: document คน onboard)

### CI Implications
```yaml
# .github/workflows/backend.yml (simplified)
on:
  pull_request:
    paths:
      - 'backend/**'
      - 'pyproject.toml'
      - 'uv.lock'
      - '.github/workflows/backend.yml'
jobs:
  test:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: cd backend && uv sync --frozen
      - run: cd backend && uv run pytest -q
```

- `trading-engine.yml` ต้องการทั้ง ubuntu (linux unit tests) + windows runner (integration กับ `MetaTrader5` package)
- `frontend.yml` รัน type-check + e2e (Playwright) + Lighthouse budget
- `shared.yml` รัน lint markdown, mermaid syntax check, link check

### Code Ownership (`.github/CODEOWNERS`)
```
/frontend/                 @eos-hinata @iris-kaguya
/backend/                  @atlas-goro @daedalus-souta
/trading-engine/           @kairos-toki @daedalus-souta
/infra/                    @hestia-kaoru
/docs/architecture/        @daedalus-souta
/docs/strategies/          @kairos-toki
/docs/database/            @mnemosyne-rin
/docs/security/            @argus-hayato
```

---

## References
- pnpm workspaces: https://pnpm.io/workspaces
- uv: https://docs.astral.sh/uv/
- Monorepo at scale (Google): "Why Google Stores Billions of Lines of Code in a Single Repository" (Potvin & Levenberg, 2016)
- Turborepo path filter pattern (for inspiration on CI strategy)
