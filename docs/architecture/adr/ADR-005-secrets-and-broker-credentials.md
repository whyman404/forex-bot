# ADR-005 — Secrets & Broker Credentials Management

**Status:** Accepted
**Date:** 2026-06-14
**Decider:** Daedalus Souta + **Argus Hayato (security)**
**Related:** ADR-001 (MT5), ADR-004 (Deployment)

---

## Context

ต้องเก็บ broker credential ของ user (MT5 login/server/password + Binance API key/secret) เพื่อใช้เปิด terminal/place order

**ข้อมูลที่ต้องเก็บ:**
- MT5: `login` (account number), `server` (e.g. `Exness-MT5Real8`), `password` (investor / master)
- Binance / ccxt: `api_key`, `api_secret`, `passphrase?` (per exchange)
- Stripe customer ID, subscription ID (less sensitive, but PII)

**Threat surface:**
- DB dump → credential exposed → trade attacker accounts
- Log accidentally writes password → leaked through Loki/Sentry
- Backup file leaked → broker accounts compromised
- Insider — admin DB read → see plaintext

**Compliance:** PDPA (Thailand), GDPR (EU users). ไม่ใช่ PCI scope (Stripe handles cards).

---

## Decision

**App-level envelope encryption (AES-256-GCM) with KEK in env, DEK per record, stored in Postgres via pgcrypto for at-rest defense-in-depth.**

### Cryptographic Design
```
┌──────────────────────────────────────────────────────────┐
│  KEK (Key Encryption Key) — 256-bit AES                  │
│   stored in: systemd env file (root-only, 0600)          │
│              + secondary in 1Password vault              │
│              + sops-encrypted backup with age key        │
│   rotated: quarterly                                     │
└──────────────────────┬───────────────────────────────────┘
                       │ wraps
                       ▼
┌──────────────────────────────────────────────────────────┐
│  DEK (Data Encryption Key) — 256-bit AES per credential  │
│   generated: at credential save (os.urandom)             │
│   stored: in DB as ciphertext (wrapped by KEK)           │
└──────────────────────┬───────────────────────────────────┘
                       │ encrypts
                       ▼
┌──────────────────────────────────────────────────────────┐
│  Plaintext: {login, server, password} JSON               │
│  Output: nonce (12B) || ciphertext || auth_tag (16B)     │
└──────────────────────────────────────────────────────────┘
```

### Storage Schema (Postgres)
```sql
CREATE TABLE broker_credentials (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    broker          TEXT NOT NULL CHECK (broker IN ('mt5_exness','binance','bybit')),
    label           TEXT NOT NULL,                -- user-friendly name
    -- envelope encryption fields
    dek_wrapped     BYTEA NOT NULL,               -- DEK encrypted by KEK
    dek_nonce       BYTEA NOT NULL,               -- nonce for KEK wrap
    ciphertext      BYTEA NOT NULL,               -- credential JSON encrypted by DEK
    cipher_nonce    BYTEA NOT NULL,               -- nonce for DEK encrypt
    cipher_tag      BYTEA NOT NULL,               -- GCM auth tag
    kek_version     SMALLINT NOT NULL,            -- support KEK rotation
    -- non-secret metadata (display)
    masked_login    TEXT,                          -- e.g. "1234****"
    server          TEXT,                          -- broker server hostname (not secret)
    status          TEXT NOT NULL DEFAULT 'unverified',  -- unverified | verified | failed | revoked
    last_verified_at TIMESTAMPTZ,
    last_used_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, broker, label)
);

CREATE INDEX idx_broker_creds_user ON broker_credentials(user_id);
```

### Why pgcrypto?
- เราใช้ **app-layer encryption เป็นหลัก** (defense in depth, language-portable)
- `pgcrypto` ใช้สำรองสำหรับ field-level encryption ของ PII อื่น ๆ ที่ไม่ใช่ credential (เช่น tax_id, phone) — encrypt-at-rest in DB transparent
- **ไม่** เก็บ KEK ไว้ใน DB (โดน dump = แตกเลย)

### KEK Storage & Rotation
- Production: systemd `EnvironmentFile=/etc/forex-bot/secrets.env` (0600, root)
- Backup: sops-encrypted file in private repo, age key ที่ Argus + Daedalus
- **Rotation quarterly** (or immediately on incident):
  1. Generate KEK_v(n+1)
  2. Background job iterate `broker_credentials WHERE kek_version = n`:
     - decrypt DEK with KEK_v(n)
     - re-wrap DEK with KEK_v(n+1)
     - update row, set `kek_version = n+1`
  3. After 100% migrated → remove KEK_v(n) from env (keep in vault for 30 days disaster window)

### Access Pattern
```python
# Pseudo: place order flow
cred = repo.get_credential(user_id, broker='mt5_exness')   # returns ciphertext
plaintext = vault.decrypt(cred)                            # in-memory only
try:
    bridge.open_order(plaintext, order_intent)
finally:
    secure_zero(plaintext)                                  # zero buffer
```

- **Never log credential** — explicit `LogFilter` on `password`, `api_secret`, `dek*`, `cipher*` fields
- **Never include in error trace** — Sentry `before_send` hook scrubs known sensitive keys
- **Use SecretStr (Pydantic)** for in-process passing → str(SecretStr) returns `**********`

---

## Alternatives Considered

### Alt 1 — HashiCorp Vault (self-hosted)
Centralized secret store with dynamic secrets, audit log

**Rejected ตอนนี้ เพราะ:**
- Vault HA = 3+ nodes infra overhead
- ทีมไม่มี Vault ops experience
- Static credentials (broker login/password) ไม่ใช้ Vault's dynamic feature
- เก็บไว้เป็น option Phase 4 (>500 users หรือ enterprise audit)

### Alt 2 — Cloud KMS (AWS KMS / GCP KMS)
KEK ที่ managed service, decrypt via API

**Partial accept later:** Phase 3 ถ้าย้ายไป cloud
**Reject for Phase 1–2:** ต้อง cloud account + IAM setup; เพิ่ม external dependency บน critical path

### Alt 3 — Database-only (pgcrypto symmetric)
ใช้ `pgp_sym_encrypt(plaintext, key)` ของ pgcrypto, ส่ง key มาจาก app

**Rejected เพราะ:**
- key transit ผ่าน SQL = อาจติด query log
- Key rotation ลำบาก (ต้อง re-encrypt ทุก row ผ่าน SQL)
- ไม่มี per-record DEK (envelope pattern เป็น best practice)

### Alt 4 — Browser-side encryption + zero-knowledge
User-derived key, server never sees plaintext

**Rejected เพราะ:**
- เราต้องใช้ credential เพื่อ login MT5 — ต้องการ plaintext at trading time
- ผู้ใช้ไม่ online ตลอด → ต้องเก็บ key บน server อยู่ดี (encrypted) = กลับมาเหมือนเดิม
- เพิ่ม UX friction (passphrase ทุกครั้ง)

---

## Consequences

### Positive
- Defense in depth: DB dump alone = useless (no KEK)
- Per-record DEK = compromise of one row doesn't expose others
- KEK rotation supported by `kek_version` column
- No external dependency (no Vault/KMS in critical path)
- Standard primitive (AES-256-GCM via `cryptography` library)

### Negative / Trade-off
- **KEK loss = total data loss** of broker credentials (mitigation: KEK backup in 2 locations, documented recovery in runbook)
- **App is responsible for crypto correctness** — review by Argus + external security audit before Phase 2 launch
- **Rotation job is critical** — must be idempotent + tested
- **GCM nonce reuse = catastrophic** — use random 96-bit nonce per encrypt; documented in `crypto.py` with test

### Operational Procedures (runbook to write)
- `crypto-rotate-kek.md` — quarterly KEK rotation steps
- `crypto-incident-response.md` — what to do if KEK compromise suspected
- `broker-cred-revoke.md` — user requests deletion → tombstone + crypto-shred

### Audit & Logging
- Every read of `broker_credentials` → emit `audit_log` row with `user_id`, `action='credential.read'`, `caller_service`, `request_id`
- Every write → audit + signed hash chain (Phase 2)
- Quarterly review by Argus

### User Rights (PDPA/GDPR)
- **Right to delete** — `DELETE` cascades + audit log retained 90 days then anonymized
- **Right to access** — UI shows masked credential + last_used_at; password never displayed back
- **Data portability** — not applicable for broker credentials (security risk)

---

## Implementation Notes (for Atlas + Argus)
- Library: `cryptography` (pyca) — well-vetted
- Implement in `backend/src/forex_bot/crypto/vault.py`
- Unit tests: vectors from NIST AES-GCM test suite
- Pen-test: include in security audit gate before Phase 2 launch

---

## References
- NIST SP 800-57 — Key Management
- OWASP Cryptographic Storage Cheat Sheet
- pyca/cryptography: https://cryptography.io/
- sops + age: https://github.com/getsops/sops
