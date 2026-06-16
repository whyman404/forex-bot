# Data Retention & Deletion Policy

> GDPR + PDPA-aligned data lifecycle for the Forex/Crypto Trading Bot Platform
> **Author:** Mnemosyne Rin
> **Reviewed with:** Argus Hayato (Security/Privacy), Daedalus Souta (Architecture)
> **Created:** 2026-06-14

---

## 1. Scope & legal basis

We process personal data of EU residents (GDPR), Thai residents (PDPA), and others. We also handle **financial transaction data** that is subject to financial-services record-retention obligations (varies by jurisdiction; we adopt the strictest applicable: **7 years** for transaction history).

This policy defines:
1. **Retention period** per table / data class.
2. **Soft-delete + hard-purge windows** for user-initiated deletion.
3. **Right-to-be-forgotten** workflow.
4. **Operational mechanics** (jobs, scripts, partitions).

---

## 2. Retention matrix

| Data class                       | Tables                                  | Retention window | Basis | Disposal |
|----------------------------------|-----------------------------------------|------------------|-------|----------|
| User account (active)            | users, broker_accounts, strategy_instances, api_keys | While active                                    | Contract performance | n/a |
| User account (soft-deleted)      | users                                   | 30 days                                         | User right-to-deletion | Hard purge after 30d unless legal hold |
| Financial transaction records    | trades, signals (filled), invoices, subscriptions | **7 years from event date**           | Financial regs (strictest of GDPR / PDPA / KYC)  | Archive to WORM S3; PG partition drop after archive verified |
| Trading history (informational)  | signals (non-filled), backtests         | 24 months online, then archive                  | Operational value     | Move to cold storage / OLAP |
| Audit log                        | audit_log                               | **7 years**                                     | SOC2 + financial compliance | Archive at 12m to S3 WORM; PG partition drop at 84m |
| Authentication artifacts         | password_hash, totp_secret              | Until account deletion + 30d                    | Security              | Hard purge with account |
| Notifications                    | notifications                           | 90 days (read or unread)                        | Operational           | Hard delete by nightly job |
| MT5 terminal pool                | mt5_terminal_pool                       | Lifetime of host                                | Operational           | Hard delete on host decommission |
| Encryption key versions          | broker_accounts.credentials_*           | 13 months past key rotation                     | Operational + audit   | Re-encrypted to current key |

---

## 3. Soft delete vs. hard purge

We use **soft delete** (set `deleted_at`) on entities a user might restore or that produce dependent records:

- `users.deleted_at`
- `broker_accounts.deleted_at`
- `strategy_instances.deleted_at`

The records remain readable internally for 30 days. After 30 days the **purge job** runs hard delete + dependent-record handling. Tables not listed above are hard-deleted on the user request (notifications, api_keys revocation) or never user-deletable (invoices, trades, audit_log) because they support financial obligation.

### 3.1 Soft-delete grace = 30 days

This window lets the user undo a mistaken cancellation, but is short enough to keep storage bounded and to be defensible under GDPR "without undue delay" (Art. 17).

---

## 4. Right-to-be-forgotten workflow

When a user invokes deletion (UI button or written request):

```
T+0    : POST /me/delete
         -> users.deleted_at = now()
         -> broker_accounts.is_active = false, deleted_at = now()
         -> strategy_instances: stop live; deleted_at = now()
         -> active sessions revoked
         -> api_keys.revoked_at = now()
         -> stripe subscription canceled (no refund implied)
         -> audit_log row written

T+30d  : purge job runs
         -> users.email/full_name/totp_secret OVERWRITTEN with NULL or token
         -> users.password_hash overwritten with random string
         -> broker_accounts.credentials_ciphertext zeroed; row kept (FK from trades)
         -> personal payload fields in notifications scrubbed; row kept if FK exists
         -> audit_log.payload_redacted scrubbed of free-form PII fields
         -> FK relations preserved with NULL actor_user_id where allowed

T+7y   : trades / invoices / audit_log partition drop
         -> verified archive in WORM S3 already; partition DETACH + DROP
```

**Why we do not hard delete the row:** trades and invoices are referenced by financial accounts; deleting them creates orphan transactions. Instead we **de-identify** (overwrite PII) while preserving the financial fact. This is the GDPR "anonymization" path, lawful under Art. 17(3)(b) (legal obligation) and Art. 17(3)(e) (legal claims defense).

---

## 5. Legal hold

If a user is under regulatory investigation, dispute, or legal hold, the operator can set `users.role` to admin-restricted mode and a `legal_hold = true` flag (added in a later migration when needed). The purge job MUST skip held users.

---

## 6. Implementation mechanics

### 6.1 Soft-delete behavior

All queries in the application must filter `WHERE deleted_at IS NULL` for these tables. To enforce, we recommend Atlas's ORM define a default scope on the SQLAlchemy session. Backups respect the soft-delete state — they capture the row as-is including `deleted_at`.

### 6.2 Purge job (`scripts/purge_soft_deleted.py`)

Runs daily at 03:00 UTC. Pseudocode:

```python
threshold = now() - timedelta(days=30)

# Hard purge users (de-identify)
UPDATE users
   SET email = 'deleted-' || id::text || '@purged.local',
       full_name = 'Deleted User',
       password_hash = encode(gen_random_bytes(32), 'hex'),
       totp_secret = NULL
 WHERE deleted_at IS NOT NULL
   AND deleted_at < $1
   AND email NOT LIKE 'deleted-%';

-- Zero broker credentials
UPDATE broker_accounts
   SET credentials_ciphertext = '\x'::bytea,
       credentials_nonce = '\x'::bytea
 WHERE deleted_at IS NOT NULL AND deleted_at < $1;
```

### 6.3 Notification purge

```sql
DELETE FROM notifications
 WHERE created_at < now() - INTERVAL '90 days';
```

Run nightly. Cheap on a small table because of the `(user_id, created_at DESC)` btree.

### 6.4 Archive + drop partition (signals/audit_log)

See `partitioning.md` section 8 for the archive workflow.

### 6.5 Daily-loss counter reset

`strategy_instances.daily_loss_today_cents` is reset to 0 at 00:00 UTC by the engine. Not a retention concern but operationally co-located here for visibility.

---

## 7. Backup retention

Backup retention is governed alongside live retention so we don't restore "forgotten" data:

| Backup type        | Retention | Storage             |
|--------------------|-----------|---------------------|
| WAL (PITR)         | 14 days   | S3 + encryption     |
| Daily full         | 35 days   | S3 + encryption     |
| Monthly full       | 13 months | S3 + encryption + object lock |
| Annual full        | 7 years   | S3 Glacier Deep Archive + object lock |

When a user is purged, that user's PII is overwritten in **live DB**. The pre-purge data still exists in backups within their retention windows. This is GDPR-acceptable provided we:
1. Document the retention windows publicly (privacy policy).
2. Refuse to use those backups except for disaster recovery affecting the whole DB.
3. Re-apply the purge after any restore (a post-restore script reruns purge on any user with `deleted_at IS NOT NULL` AND past threshold).

---

## 8. PII inventory

| Field                          | Table                    | Class |
|--------------------------------|--------------------------|-------|
| email                          | users                    | PII (identifier) |
| full_name                      | users                    | PII |
| country                        | users                    | quasi-PII |
| password_hash                  | users                    | authentication secret |
| totp_secret (encrypted)        | users                    | authentication secret |
| ip_addr                        | audit_log                | PII (legally PII under GDPR) |
| user_agent                     | audit_log                | quasi-PII |
| credentials_ciphertext         | broker_accounts          | financial secret |
| stripe_subscription_id / invoice_id | subscriptions, invoices | financial linkage |

The PII inventory is the input for **Argus's data classification doc** and the privacy policy displayed to users.

---

## 9. User-facing commitments (suggested wording)

> "When you delete your account, we immediately stop processing your data for active services. Within 30 days we permanently de-identify your account record. Financial transaction records and audit logs are retained for 7 years for legal compliance, then permanently deleted. Backups roll out of our system on the schedule documented in our Backup Retention table."

Iris will review for tone and place in the UI.

---

## 10. References

- ADR-005 — Encrypted broker credentials (Argus)
- `partitioning.md` — partition drop/archive workflow
- `schema.md` — soft-delete columns per table
- GDPR Art. 17 (Right to erasure)
- PDPA (Thailand) Sec. 33 (Right of rectification and erasure)

---

## 11. Phase-2 additions (2026-06-15)

### 11.1 New tables — retention summary

| Table                  | Online retention | Disposal | Rationale |
|------------------------|------------------|----------|-----------|
| plans                  | indefinite       | hard delete only if no FK refs | Lookup catalog |
| stripe_events          | 24 months        | partition-style purge by `created_at` | Stripe replay window + audit |
| email_verifications    | 30 days          | `DELETE WHERE used_at IS NOT NULL OR expires_at < now() - 30d` | Single-use tokens |
| password_resets        | 30 days          | same as above | Single-use tokens |
| consents               | indefinite       | de-identify on user purge (user_id → NULL) | Legal record of agreement |
| live_consents          | indefinite       | de-identify on user purge | Legal record + IP for traceability |
| live_gate_checks       | 24 months        | nightly delete by `checked_at` | Operational audit |
| mt5_bridges            | while account active + 30d | hard delete on broker_account purge | Tied to user |
| email_outbox           | **6 months** (partitioned) | partition drop | Operational debug only; receipt = ESP record |
| webhook_inbox          | **12 months** (partitioned) | partition drop | Stripe dispute / replay window |
| account_exports        | 7 days after `ready` | row delete + S3 object delete on `expired` | Pre-signed URL TTL |
| account_deletions      | indefinite       | row preserved as audit of the deletion event | Compliance audit |
| live_engine_runs       | 24 months        | nightly delete by `started_at` | Operational stats |

### 11.2 Special handling — `consents` + `live_consents` under purge

When a user is hard-purged (T+30d), we MUST keep the consent rows as proof
of the original agreement BUT remove direct identifiers:
- `consents.user_id` is preserved (it's a UUID, already not-PII once the
  user is de-identified) — same as `audit_log`.
- `live_consents.ip_addr` is OVERWRITTEN to `NULL`.
- `live_consents.user_agent` is OVERWRITTEN to `NULL`.

This balances GDPR Art. 17 (erase PII) with Art. 17(3)(e) (legal defense).

Update `scripts/purge_soft_deleted.py` to add the above clear steps.

---

## 12. PDPA (Thailand) — explicit obligations

Thailand's PDPA mirrors GDPR closely for our purposes; the following are
the deltas we explicitly commit to:

### 12.1 Data Subject Access Request (DSAR) — 30-day SLA

PDPA s. 30 requires controllers to respond to access requests **within 30
days**. Our SLA: **on request, the export is queued; user receives the
download link within 7 calendar days**. Concrete steps:
1. User clicks "Export my data" in account settings.
2. Row inserted into `account_exports` with `status='queued'`.
3. Worker generates the archive (spec: `docs/database/gdpr-export-spec.md`).
4. User receives email with pre-signed S3 URL.
5. URL expires 7 days after generation.

If 7 days lapses without delivery, the on-call DBA must investigate; the
PDPA 30-day hard limit must never be breached.

### 12.2 Financial records — 7-year retention

PDPA accepts retention required by other law. The 7-year retention on
`trades`, `invoices`, `audit_log` is justified under Thai Anti-Money
Laundering Act + Revenue Code record-keeping requirements (whichever is
stricter applies; both are 5 years, we elect 7 for headroom).

### 12.3 Hard delete window — 30 days unless legal hold

On a deletion request, the user is soft-deleted immediately and
hard-purged at T+30d. If a legal hold is active (s.5 above), the purge
job MUST skip the user; an internal ticket records the basis for the hold.

### 12.4 Cross-border transfer

We host data in Singapore (AWS ap-southeast-1) which is on Thailand's
"adequate" list for transfers. Backups to S3 Glacier follow the same
region. Stripe data crosses to the US under Stripe's PDPA DPA. This is
disclosed in the privacy policy.

### 12.5 Breach notification — 72h

Same as GDPR Art. 33. Argus owns the breach playbook; DB engineer's
role is to provide the affected-row count + classification within 4 hours
of incident declaration.
