# Forex Bot Backend

FastAPI backend for the Forex/Crypto trading bot SaaS.

**Owner:** Atlas Goro
**Stack:** Python 3.12, FastAPI 0.110+, SQLAlchemy 2.0 (async), Alembic, Pydantic v2, structlog, OpenTelemetry, pytest.

---

## Local Development

### Prerequisites
- Python 3.12+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- PostgreSQL 16
- Redis 7

### Quick start

```bash
# 1. Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Sync dependencies
cd backend
uv sync --extra dev

# 3. Copy env file
cp .env.example .env
# edit .env with real values (DATABASE_URL, REDIS_URL, secrets)

# 4. Start dependencies (Postgres + Redis) — see infra/docker-compose.dev.yml
docker compose -f ../infra/docker-compose.dev.yml up -d postgres redis

# 5. Run migrations
uv run alembic upgrade head

# 6. Run the server (auto-reload)
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open [http://localhost:8000/docs](http://localhost:8000/docs) for interactive API docs.

---

## Tests

```bash
# All tests
uv run pytest

# Unit only
uv run pytest -m unit

# Integration (needs Postgres + Redis up)
uv run pytest -m integration

# Coverage
uv run pytest --cov=app --cov-report=term-missing
```

---

## Linting / Type Check

```bash
uv run ruff check .
uv run ruff format .
uv run mypy app/
```

---

## Project Layout

```
backend/
├── app/
│   ├── api/            ← HTTP routers (one file per resource)
│   ├── core/           ← config, security, logging, encryption
│   ├── db/             ← SQLAlchemy engine + session
│   ├── middleware/     ← request_id, auth, rate_limit, audit
│   ├── models/         ← SQLAlchemy ORM models
│   ├── schemas/        ← Pydantic request/response DTOs
│   ├── services/       ← business logic (use case layer)
│   └── main.py         ← FastAPI app factory
├── tests/
├── Dockerfile
├── pyproject.toml
└── .env.example
```

### Layered architecture (rough rule)

```
api router ──> service ──> repository / external client ──> db / redis / broker
```

- Router: validate input, call service, format response.
- Service: orchestrate business logic, transaction boundary.
- Model: SQLAlchemy ORM only — no business logic.

---

## Observability

- Logs: structured JSON via `structlog` → stdout → collected by Loki.
- Traces: OpenTelemetry → OTLP exporter → Tempo/Jaeger.
- Errors: Sentry SDK.
- Metrics: exposed at `/metrics` (Prometheus format) — TODO.

Every request gets a `request_id` (also surfaced as `traceId` in errors).

---

## Security Notes

- Passwords hashed with Argon2id.
- Access tokens: 15 min, refresh tokens: 7 days, stored hashed.
- Broker credentials: envelope encrypted (AES-256-GCM) — see `app/core/encryption.py` + ADR-005.
- TOTP MFA mandatory for live-trading actions.
- Rate limit: Redis-backed sliding window.

---

## API Spec

OpenAPI 3.1 source-of-truth: [`../docs/api/openapi.yaml`](../docs/api/openapi.yaml).
FastAPI auto-generates a runtime spec at `/openapi.json` — keep them aligned (CI lint check planned).

---

## Coordinators

- Schema / migrations: Mnemosyne Rin → `docs/database/`
- Architecture / ADR: Daedalus Souta → `docs/architecture/`
- Auth / secrets / threat model: Argus Hayato → `docs/security/`
- Trading engine contract: Kairos Toki → `docs/strategies/`
