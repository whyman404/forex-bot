# Secrets Management Plan

> Concrete envelope-encryption design for broker credentials and platform secrets
> **Author:** Argus Hayato | **Date:** 2026-06-14
> **Coordinates with:** Daedalus (ADR-005), Mnemosyne (encryption columns), Atlas (auth/middleware)

---

## 1. Secret Inventory (what we hold)

| ID | Secret | Where | Sensitivity | Lifecycle |
|----|--------|-------|------------|-----------|
| SC-1 | MT5 login (server, login, password, investor pwd) | Postgres `broker_credentials` (encrypted) | **Critical** | User-managed, re-enter if leak |
| SC-2 | Stripe `sk_live` (restricted) | Backend env / secret manager | Critical | Quarterly rotate |
| SC-3 | Stripe webhook signing secret | Backend env | High | Rotate w/ key rotation |
| SC-4 | Omise secret key | Backend env | High | Quarterly |
| SC-5 | JWT RS256 private key | Backend secret mount | Critical | 6-month rotate, support N-1 via `kid` |
| SC-6 | KEK (data encryption master) | Env (interim) → KMS (Phase-2) | Critical | Quarterly with re-wrap |
| SC-7 | DB password (app role) | Backend env | High | Quarterly |
| SC-8 | Redis password | Backend env | High | Quarterly |
| SC-9 | Sentry DSN | Backend env (less sensitive) | Medium | Per-incident |
| SC-10 | OAuth secrets (Google, etc) | Backend env | High | Per-provider |
| SC-11 | Exness server name | Per-user table (not really a secret) | Low | Per-user |
| SC-12 | TOTP seed (per user) | Postgres encrypted (envelope w/ KEK) | High | User reset only |
| SC-13 | Internal mTLS certs | Secret mount | High | Yearly via cert-manager / step-ca |

---

## 2. Envelope Encryption Design (broker credentials)

### 2.1 Algorithm choice

- **AES-256-GCM** — AEAD, fast, well-audited (libsodium / cryptography.io).
- **Why not ChaCha20-Poly1305?** Equivalent security; AES-NI hardware = ~5x speed on cloud x86 — pick AES-GCM for perf.
- **Library:** Python `cryptography` (PyCA), NOT raw pycryptodome. NEVER roll-our-own.

### 2.2 Two-tier (envelope)

```
[ Plaintext MT5 password ]
        |
        | AES-256-GCM(DEK, nonce=12B)
        v
[ Ciphertext + 16B tag ]            <-- stored in DB
        ^
        |
[ DEK (32B random per row) ]
        |
        | AES-256-GCM(KEK, nonce=12B)
        v
[ wrapped_dek + 16B tag ]            <-- stored in DB
        ^
        |
[ KEK (32B) ]                        <-- env / KMS, NEVER in DB
```

- **DEK per row** (per credential entry). Compromise of one DEK exposes only that row.
- **KEK in env (Phase-1)** → migrate to **AWS KMS / GCP KMS / HashiCorp Vault transit** (Phase-2 per ADR-005).
- **KEK never touches DB**. Re-wrap on rotation, never decrypt-and-re-encrypt the secret (DEK rewrap only).

### 2.3 Database column schema (coordinate with Mnemosyne)

Table `broker_credentials`:

| Column | Type | Note |
|--------|------|------|
| `id` | uuid PK | |
| `user_id` | uuid FK | |
| `broker` | text | `exness`, `binance`, ... |
| `account_login` | text (encrypted) | login can be considered semi-sensitive |
| `account_login_nonce` | bytea | 12B |
| `account_login_tag` | bytea | 16B (or appended in ciphertext) |
| `account_password_ct` | bytea | ciphertext |
| `account_password_nonce` | bytea | 12B random per row |
| `account_password_tag` | bytea | 16B (AEAD tag) |
| `investor_password_ct` | bytea (nullable) | |
| `investor_password_nonce` | bytea (nullable) | |
| `investor_password_tag` | bytea (nullable) | |
| `server` | text | not secret |
| `wrapped_dek` | bytea | DEK encrypted with KEK |
| `dek_nonce` | bytea | 12B |
| `dek_tag` | bytea | 16B |
| `key_version` | int | KEK version used to wrap |
| `created_at` | timestamptz | |
| `updated_at` | timestamptz | |
| `last_used_at` | timestamptz | |

Indexes: `(user_id, broker)` unique.

**Alternative:** Concatenate `nonce || ciphertext || tag` into one `bytea` column. Pick this if Mnemosyne prefers fewer columns; just document format and stick to it.

### 2.4 Encryption flow (pseudo-code)

```python
# Encrypt on credential save
def encrypt_credential(plaintext: bytes, kek: bytes, key_version: int):
    dek = os.urandom(32)
    nonce = os.urandom(12)
    aesgcm = AESGCM(dek)
    aad = f"v={key_version}".encode()  # bind version
    ct = aesgcm.encrypt(nonce, plaintext, aad)  # ct includes 16B tag

    dek_nonce = os.urandom(12)
    kek_gcm = AESGCM(kek)
    wrapped_dek = kek_gcm.encrypt(dek_nonce, dek, aad)

    return {
        "ciphertext": ct,             # nonce||tag handled separately or appended
        "nonce": nonce,
        "wrapped_dek": wrapped_dek,
        "dek_nonce": dek_nonce,
        "key_version": key_version,
    }
```

```python
# Decrypt just-in-time (only when handing to engine)
def decrypt_credential(row, kek_for_version):
    aad = f"v={row.key_version}".encode()
    kek_gcm = AESGCM(kek_for_version)
    dek = kek_gcm.decrypt(row.dek_nonce, row.wrapped_dek, aad)
    aesgcm = AESGCM(dek)
    plaintext = aesgcm.decrypt(row.nonce, row.ciphertext, aad)
    # zero dek + plaintext after use; Python can't truly zero — minimize lifetime
    return plaintext
```

### 2.5 Operational rules

- **Decrypt only at point-of-use** (sending to MT5 terminal). Never decrypt on /me, never expose on UI.
- **No plaintext in logs** — see redaction list below.
- **No plaintext to Sentry** — scrubber pre-send.
- **No plaintext over UI after first save** — input-once, never display, "rotate" = re-enter.
- **AAD binds key version** — prevents downgrade between versions.

---

## 3. Key Rotation Policy

### 3.1 KEK rotation (quarterly)

1. Generate `kek_v(N+1)` (32 random bytes from `os.urandom`).
2. Add to KEK registry — app now accepts both `vN` and `v(N+1)`.
3. Background job re-wraps all DEKs:
   - For each row: decrypt `wrapped_dek` with `kek_vN` → re-encrypt with `kek_v(N+1)` → set `key_version=N+1`.
   - **Never** decrypt the actual credential during rotation. Only DEK rewrap.
4. Wait until 100% rows on `v(N+1)`.
5. Remove `kek_vN` from registry.
6. Audit log every step.

**Why never break old:** if backup restored from before rotation, we need old KEK to decrypt. Keep N-1 in cold storage for 90 days.

### 3.2 JWT signing key rotation (6-month)

- Generate new RSA 2048 (or RSA 3072 for forward-leaning).
- Add `kid=v(N+1)` to JWKS endpoint.
- Backend starts signing with new `kid`.
- Old key stays in JWKS for max access-token TTL (15m + grace = 1h).
- Then remove old key.

### 3.3 Stripe / Omise / DB / Redis (quarterly)

- Generate new in provider console.
- Update env / secret manager.
- Restart app with dual-key window (where supported).
- Revoke old after 24h.

### 3.4 Per-user TOTP seed

- Rotated only on user request or after suspected compromise.

### 3.5 Rotation calendar (default)

| Secret | Cadence | Trigger |
|--------|---------|---------|
| KEK | Quarterly | Calendar + on suspected leak |
| JWT key | 6-month | Calendar + on leak |
| Stripe key | Quarterly | Calendar |
| DB / Redis | Quarterly | Calendar |
| mTLS certs | Yearly | Calendar (auto via cert-manager) |
| User MT5 creds | User-driven | Leak / breach disclosure |

---

## 4. Storage Tiers

| Tier | What | Where |
|------|------|-------|
| **Tier-A: Critical** | KEK, JWT private key, Stripe key | Phase-1: env w/ file ACL 0400 + restart-only; Phase-2: KMS / Vault transit |
| **Tier-B: High** | DB password, Redis password, OAuth secrets | Env via Docker secret / systemd EnvironmentFile w/ 0400 |
| **Tier-C: Medium** | Sentry DSN, public config | Env, less restricted |
| **Tier-D: Per-user** | MT5 creds, TOTP seed | Postgres, envelope-encrypted |

### 4.1 Local dev

- `.env.example` contains **dummy** values:
  ```
  KEK_V1=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=   # 32B base64 dummy DO NOT USE IN PROD
  STRIPE_SECRET=sk_test_dummy_do_not_use
  JWT_PRIVATE_KEY_PATH=./dev-secrets/jwt-dev.pem
  ```
- `.env` is git-ignored (verified by pre-commit hook).
- `dev-secrets/` git-ignored, contains dev-only PEM.
- `make gen-dev-secrets` regenerates dev KEK + JWT key.
- Pre-commit hooks: **gitleaks** + **detect-secrets** + custom rule blocking 32-byte base64 in non-`.env.example`.

### 4.2 CI

- GitHub Actions secrets via environment `production` (required approval).
- OIDC to cloud (no long-lived AWS keys).
- Secrets masked in logs (`add-mask`).
- Build artifacts signed (cosign), no secrets baked into image.

### 4.3 Production (Phase-1)

- Backend on Linux VPS, secrets via systemd `EnvironmentFile=/etc/forexbot/env` with mode 0400, owner `forexbot`.
- Trading Engine on Windows VPS — env via secure registry / Windows Credential Manager (preferred over plain env on Windows).
- Restart-only secret read (no hot-reload of secrets to reduce in-mem footprint).

### 4.4 Production (Phase-2) — KMS migration

- AWS KMS (or GCP KMS or HashiCorp Vault) holds KEK.
- App calls `Decrypt(wrapped_dek_envelope)` → KMS returns DEK.
- Lower in-app exposure of KEK.
- Audit via CloudTrail.

---

## 5. Logging & Redaction

### 5.1 Deny-list (NEVER logged, scrub at source)

```
- password, pwd, passwd
- mt5_password, investor_password
- account_login (mask middle digits: 1234***5678)
- secret, sk_live, sk_test, whsec_, omise_skey_
- private_key, jwt_private_key, kek, dek
- Authorization header, Cookie header
- token, refresh_token, access_token, id_token
- card_number, cvv, exp_month, exp_year, pan
- ssn, nat_id, passport_no
- totp_seed, totp_secret
- email (mask: a***@example.com unless explicitly needed for support)
```

### 5.2 Implementation

- FastAPI custom `JSONFormatter` with field allowlist for structured logs.
- Pre-Sentry hook: `before_send` removes deny-list keys recursively.
- Logger filter that scrubs by regex (`sk_live_[A-Za-z0-9]+`, `eyJ[A-Za-z0-9_.-]+`, etc.).
- **Test:** unit test that logs deny-listed values, asserts they don't appear in captured handler output.

### 5.3 Audit log

Append-only `audit_log` table. **Hash-chained** (each row stores SHA-256 of previous row + payload) so tampering detectable.

Events to log (always, even for read):
- broker credential create / read / decrypt / delete
- live mode toggle on/off
- 2FA enable / disable / fail
- admin impersonation
- payment events
- key rotation steps
- kill switch trigger

Logged with: user_id (subject), actor_id (could be admin), action, target, IP, UA, request_id, before/after hash (not value).

---

## 6. Threat Model for Secrets Pipeline (mini)

| Threat | Mitigation |
|--------|-----------|
| KEK in env leaks via env dump | File ACL 0400, no `/proc/<pid>/environ` access to non-root; future: KMS |
| Memory dump reveals KEK | Minimize lifetime — Phase-2 KMS calls (KEK never in app mem) |
| Backup contains plaintext | Backup is of encrypted ciphertext only; KEK separately stored |
| Engineer copies prod DB to laptop | Prod role denies SELECT on `broker_credentials.*ciphertext` unless via approved tool; data minimization on staging copies |
| Re-wrap during rotation crashes | Idempotent batched re-wrap, transaction per row, resume on failure |
| Old KEK lost → cannot decrypt restored backup | Cold-storage retain N-1 for 90 days, document recovery |

---

## 7. Implementation Checklist (for Mnemosyne + Atlas + Daedalus)

### DB (Mnemosyne)
- [ ] Migration for `broker_credentials` schema (with nonce/tag/key_version columns)
- [ ] Same pattern for `totp_seed` column on `users`
- [ ] App role: only DML, no DDL
- [ ] pgaudit installed
- [ ] Backup encryption (age) + cron + restore drill

### App (Atlas)
- [ ] `encrypt_credential` / `decrypt_credential` utility module
- [ ] KEK registry loader (env + version map)
- [ ] Pre-send Sentry scrubber
- [ ] Custom JSON log formatter with deny-list
- [ ] Audit log writer (hash-chained)
- [ ] JWT key loader with `kid` rotation support
- [ ] Stripe webhook signature verifier + idempotency
- [ ] Pre-commit hook for gitleaks + detect-secrets

### Infra (Daedalus + Hestia)
- [ ] `EnvironmentFile` with mode 0400 on prod
- [ ] Backup bucket with object-lock + KMS encryption
- [ ] ADR-005 KMS migration plan (deferred Phase-2)
- [ ] Cron job for KEK rotation (quarterly)
- [ ] Cron job for cert-manager / step-ca yearly renew

---

## 8. References

- NIST SP 800-57 (key management)
- OWASP Cryptographic Storage Cheat Sheet
- Google Tink design (envelope encryption inspiration)
- AWS KMS envelope encryption pattern
- PyCA cryptography docs (`AESGCM`)
