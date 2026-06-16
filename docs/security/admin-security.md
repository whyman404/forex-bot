# Admin Security — Privileged Access Model

**Owner:** Argus Hayato (Security)
**Phase:** 3.5 (admin panel + admin endpoints)
**Status:** Mandatory for any `/api/v1/admin/*` endpoint
**Last updated:** 2026-06-16

> "Trust no one, verify everything." Admin is the highest blast radius role in the system. Single mistake = mass compromise. Defense in depth is non-negotiable.

---

## 0. NON-NEGOTIABLES (must satisfy BEFORE any destructive admin op)

🔴 **All of the following MUST be true on every destructive admin request:**

1. JWT valid AND role re-fetched from DB == `admin` (NOT trusted from JWT claim alone)
2. Step-up TOTP code valid (header `X-Step-Up-TOTP`) within 5min window, single-use, bound to action+target hash
3. IP allowlist check passes (if `ADMIN_IP_ALLOWLIST` set) OR breakglass window active
4. Multi-admin approval present (if action is in n-of-m list)
5. Action is NOT prohibited (self-action, impersonation of admin, etc.)
6. Audit log row written BEFORE state change (write-ahead)

Fail any of these → 403 + audit + alert.

---

## 1. Privileged Access Model

### 1.1 Role Schema
```sql
ALTER TABLE users ADD COLUMN role VARCHAR(16) DEFAULT 'user' NOT NULL;
-- 'user' | 'admin'
CREATE INDEX idx_users_role ON users(role) WHERE role = 'admin';
```

### 1.2 `require_admin` Middleware (mandatory)
- Loaded role **from DB, every request** — never trust JWT claim alone
- Why: detect concurrent demotion (admin A demotes admin B, B's existing tokens must immediately lose admin power)
- Cache: NO cache for role on admin endpoints (latency cost acceptable; correctness > speed)
- Mount on every route under `/api/v1/admin/*` — use route-tree mount not per-handler decoration (defense against forgetting)

```python
async def require_admin(request: Request, user=Depends(get_current_user)):
    # CRITICAL: re-fetch from DB, do NOT trust JWT
    db_user = await db.fetch_one("SELECT role, is_active, totp_enrolled FROM users WHERE id = $1", user.id)
    if not db_user or db_user.role != "admin" or not db_user.is_active:
        await audit_log(actor=user.id, action="admin_access_denied", reason="not_admin_or_inactive", ip=request.client.host)
        raise HTTPException(403, "admin required")
    if not db_user.totp_enrolled:
        raise HTTPException(403, "TOTP enrollment required for admin")
    request.state.admin = db_user
    return db_user
```

### 1.3 Route-Tree Mount Pattern
```python
admin_router = APIRouter(prefix="/api/v1/admin", dependencies=[Depends(require_admin)])
# every sub-router auto-inherits require_admin
app.include_router(admin_router)
```

---

## 2. Step-Up Authentication (TOTP)

### 2.1 Destructive Operations Requiring Step-Up
- `POST /admin/users/{id}/impersonate`
- `DELETE /admin/users/{id}`
- `POST /admin/users/{id}/ban`
- `POST /admin/broadcast/email`
- `POST /admin/system/kill-switch`
- `PATCH /admin/users/{id}/role` (any role change)
- `POST /admin/subscriptions/{id}/override`
- `DELETE /admin/audit-log/*` (NEVER allowed actually — see §3)

### 2.2 Step-Up Token Properties
- **Lifetime:** 5 min max
- **Use count:** single-use (replay-protected via Redis SETNX on token hash)
- **Bound to:** action name + target id hash (cannot use TOTP for action X on target Y to perform action X on target Z)
- **Delivery:** Header `X-Step-Up-TOTP: <6-digit-code>`
- **Verification:** server validates against admin's enrolled TOTP secret

### 2.3 Step-Up Flow
1. Admin clicks destructive button in UI
2. UI prompts modal: "Enter 6-digit TOTP code from authenticator"
3. UI sends request with `X-Step-Up-TOTP` header
4. Middleware verifies TOTP + replay (SETNX `stepup:{admin_id}:{code}:{action}:{target_hash}` EX 300)
5. On success → audit log + perform action
6. On fail → 403 + audit `stepup_failed` (alert on 3 fails in 5min)

### 2.4 Middleware
```python
async def require_stepup(request: Request, action: str, target_id: str, admin=Depends(require_admin)):
    code = request.headers.get("X-Step-Up-TOTP")
    if not code or len(code) != 6 or not code.isdigit():
        raise HTTPException(403, "step-up TOTP required")
    if not pyotp.TOTP(admin.totp_secret).verify(code, valid_window=1):
        await audit_log(actor=admin.id, action="stepup_failed", target_type="self", target_id=admin.id, ip=request.client.host)
        raise HTTPException(403, "invalid TOTP")
    target_hash = hashlib.sha256(f"{action}:{target_id}".encode()).hexdigest()[:16]
    key = f"stepup:{admin.id}:{code}:{target_hash}"
    if not await redis.set(key, "1", nx=True, ex=300):
        raise HTTPException(403, "step-up code already used")
```

---

## 3. Audit Log Requirements

### 3.1 Schema
```sql
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ DEFAULT now() NOT NULL,
    actor_id UUID NOT NULL,
    impersonator_id UUID,  -- non-null only during impersonation
    action VARCHAR(64) NOT NULL,
    target_type VARCHAR(32),
    target_id UUID,
    payload JSONB,          -- redacted of PII (no passwords, no broker_password, no CC)
    before_state JSONB,
    after_state JSONB,
    ip_addr INET,
    user_agent TEXT,
    request_id UUID,
    success BOOLEAN NOT NULL DEFAULT true,
    error_code VARCHAR(32)
);
CREATE INDEX idx_audit_actor_ts ON audit_log(actor_id, ts DESC);
CREATE INDEX idx_audit_action_ts ON audit_log(action, ts DESC);
CREATE INDEX idx_audit_target ON audit_log(target_type, target_id, ts DESC);
-- Append-only: revoke UPDATE/DELETE on audit_log from app user
REVOKE UPDATE, DELETE ON audit_log FROM forex_app;
GRANT INSERT, SELECT ON audit_log TO forex_app;
```

### 3.2 Write-Ahead Rule
- Audit row MUST be inserted **before** mutating state — if mutation fails, mark `success=false` in a follow-up insert (not update)
- Use Postgres NOTIFY for real-time alerting on critical actions (kill_switch, mass_delete, role_change)

### 3.3 PII Redaction
- `password`, `broker_password`, `mt5_password`, `totp_secret`, `card_*`, `iban`, `ssn` → `[REDACTED]`
- Email → first 2 chars + `***@domain.com`
- Use central `redact_pii(dict)` helper

### 3.4 Retention
- 7 years (financial regulation)
- Cold storage after 90 days (S3 Glacier with Object Lock — immutable)
- Hash-chain each daily batch (sha256 of prior batch + current → next) — tamper detection

### 3.5 Read Access
- Admin read: yes (via admin panel) but their reads are themselves audited (sampled)
- No admin can delete audit_log entries — schema enforced
- Export: only super-admin role (future), step-up required

---

## 4. Impersonation Security

### 4.1 Flow
1. Admin selects user → reason field (required, min 10 chars) → ticket number (optional)
2. Step-up TOTP
3. Server issues short-lived JWT:
```json
{
  "user_id": "<target_user_id>",
  "impersonator_id": "<admin_id>",
  "iss": "forex-bot",
  "exp": <now+5min>,
  "type": "impersonation",
  "ticket": "SUP-1234",
  "reason_hash": "<sha256 of reason>",
  "jti": "<unique>"
}
```
4. UI uses this token for subsequent calls (NOT replacing admin's session — opens "impersonation tab")
5. Server middleware checks `type==impersonation` and resolves user_id for action context, impersonator_id for audit

### 4.2 Restrictions During Impersonation
🔴 **Cannot perform** (server-side enforced):
- Delete any record (own account, EA, signals)
- Change broker credentials (MT5 connection)
- Go live (paper → live mode flip)
- Withdraw / payout
- Change email / password
- Manage TOTP
- Manage payment method
- Subscribe / cancel subscription
- Any `/admin/*` endpoint

If admin tries → 403 `impersonation_blocked`. Middleware: `if request.state.impersonator_id and route in WRITE_DESTRUCTIVE_LIST: 403`.

### 4.3 Cannot Impersonate
- Self (admin == target)
- Any user with role == `admin` (impersonating another admin = lateral escalation)
- Users with active `do_not_impersonate` flag (legal/dispute hold)

### 4.4 User Notification
- Email to user: "Your account was accessed by support for ticket SUP-XXXX on YYYY-MM-DD. Reason summary: [first 50 chars]"
- **Batched 24h** to avoid leaking access patterns to attacker who compromises admin account (delay buys detection time)
- One email/day max, summarizing all impersonation sessions

### 4.5 Audit During Impersonation
Every action writes BOTH ids:
```json
{ "actor_id": "<target_user>", "impersonator_id": "<admin>", ... }
```

---

## 5. Self-Protection Rules

🔴 **Server REJECTS (cannot be overridden by another admin's approval — these are absolute):**

| Action | Self-rule | Reason |
|---|---|---|
| Demote self (`role: admin → user`) | BLOCKED | Lockout / bypass approval chain |
| Ban self | BLOCKED | Lockout |
| Delete self | BLOCKED | Lockout, audit chain break |
| Disable own TOTP | BLOCKED | Bypass step-up forever |
| Impersonate self | BLOCKED | Bypass impersonation restrictions |
| Approve own multi-admin request | BLOCKED | n-of-m collapse |

Code:
```python
if action in SELF_FORBIDDEN and target_id == admin.id:
    raise HTTPException(403, f"cannot {action} self")
```

Recovery: another admin performs the action (e.g. admin A wants to demote self for security review → admin B does it).

---

## 6. Multi-Admin Approval (n-of-m)

### 6.1 Actions Requiring n=2 (when ≥ 2 admins exist)
- Global kill switch ON (system-wide trading halt)
- Demote another admin → user
- Ban another admin
- Delete another admin
- Rotate KEK / disable encryption
- Bulk delete users (>50)
- Export full audit log

### 6.2 Workflow
1. Admin A initiates → step-up TOTP → request stored in `admin_approval_requests` (status=`pending`, expires_at=now+15min)
2. Admin B sees pending request in panel → reviews payload diff → step-up TOTP → approve
3. Server checks: approver != initiator, both still admin, request not expired
4. Action executes; both ids logged in audit (`actor_id=initiator, co_approver_id=approver`)
5. Expiry: auto-cancel after 15min, audit logged

### 6.3 Single-Admin Edge Case
- If total active admins == 1 → n-of-m relaxed to n=1 BUT requires elevated step-up (TOTP + email confirmation link clicked within 10min)
- Strong recommendation in onboarding: **always provision 2+ admins** post-launch

### 6.4 Schema
```sql
CREATE TABLE admin_approval_requests (
    id UUID PRIMARY KEY,
    initiator_id UUID NOT NULL,
    action VARCHAR(64) NOT NULL,
    target_type VARCHAR(32),
    target_id UUID,
    payload JSONB,
    status VARCHAR(16) DEFAULT 'pending', -- pending|approved|rejected|expired
    approver_id UUID,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    executed_at TIMESTAMPTZ
);
```

---

## 7. IP Allowlist + Breakglass

### 7.1 Allowlist
- Env `ADMIN_IP_ALLOWLIST` = comma-separated CIDR list (e.g. `203.0.113.0/24,198.51.100.42/32`)
- Empty / unset = allowlist disabled (warning in seed_admin.py for production)
- Middleware on `/api/v1/admin/*`:
```python
if ADMIN_IP_ALLOWLIST and not in_cidr(request.client.host, ADMIN_IP_ALLOWLIST):
    await audit_log(actor=admin.id, action="admin_ip_denied", ip=request.client.host)
    raise HTTPException(403, "IP not allowed for admin")
```
- Behind reverse proxy: use `X-Forwarded-For` with trusted-proxy validation (don't trust raw header)

### 7.2 Breakglass
- Emergency: lost office network, on-call from home, etc.
- Trigger: env `ADMIN_BREAKGLASS=true` AND restart app
- Window: 30 minutes from process start (read from process boot time, NOT user-controllable)
- Effect: IP allowlist bypassed; everything else (step-up, multi-admin) STILL enforced
- Audit: every request during breakglass logs `breakglass_active=true` + alert to all admins + Slack channel

### 7.3 Operational Discipline
- Breakglass leaves audit trail; mis-use grounds for revocation
- Post-incident: review `breakglass_active=true` rows, justify each session

---

## 8. Weak Password Warning at Seed

### 8.1 Policy
`seed_admin.py` checks `ADMIN_PASSWORD` against:
- Length < 12 → warn
- Common passwords (top 10k list) → block unless `--allow-weak`
- Dictionary word ratio > 50% → warn
- No mixed case / digit / special → warn
- Includes admin email local part → warn

### 8.2 Current Seed Value: `.Master6728`
**Verdict:** BORDERLINE
- Length: 11 (below recommended 12) — WARN
- Has: uppercase, lowercase, digit, special (`.`) — PASS
- Dictionary: "Master" common word — WARN
- Verdict: **PROCEED with WARN** — do not block

### 8.3 Required Recommendation (in seed output)
```
⚠️  ADMIN_PASSWORD warning:
   - Length 11 (recommended 12+)
   - Contains common word "Master"
   - RECOMMENDED: rotate password on first login.
   - At first login UI MUST require password change before any other action.
```

### 8.4 Force Rotation
- DB column: `users.force_password_change BOOLEAN`
- Seeded admin: `force_password_change=true`
- Middleware blocks all endpoints except `POST /me/password` until cleared

---

## 9. Session Monitoring

### 9.1 Per-Request Sampling
- 10% of admin requests audit-logged in full (path, method, status, latency)
- 100% of writes / step-up / destructive actions logged

### 9.2 Anomaly Detection
- New country (GeoIP from session IP) vs last 30d → email alert + Slack to all admins
- New user-agent (browser fingerprint hash) → soft warn in panel
- > 50 requests/min → throttle + alert
- Failed step-up TOTP (3 in 5min) → temp lock 30min + email
- Login from Tor exit node → block (env switch to allow)

### 9.3 Concurrent Session Detection
- Admin must not have > 2 concurrent sessions; alert on 3rd; revoke oldest

---

## 10. Defense-in-Depth Against Role Escalation

### 10.1 Layered Controls
1. **JWT role claim ignored** — always re-fetched from DB (see §1.2)
2. **Role change requires step-up TOTP**
3. **Role change requires multi-admin approval if target is another admin**
4. **Demotion immediate** — token still valid but next call re-reads role, 403s
5. **Cron job** every 6h: revoke admin tokens older than 24h, force re-login (`max_admin_session_age=24h`)
6. **Token JTI denylist** for revoked admin sessions
7. **Database trigger** on `users.role` change → audit row + NOTIFY channel `role_changed` → SOC alert
8. **No mass-assign** on user update — explicit allowlist `["display_name", "timezone"]`; role NEVER in body parser allowlist
9. **Separate endpoint** for role change: `PATCH /admin/users/{id}/role` (clear intent, easier to audit)

### 10.2 Anti-Race
- Demote + then-act window: between demote commit and actor's next request, demoted-admin still has valid JWT
- Mitigation: cron is too slow; instead — on demotion commit, publish to Redis pub/sub `revoked_admins`, all instances drop cached role + add JTI to denylist within 1s
- Acceptable residual risk: 1s window after demotion

---

## 11. Logging + Alerting (operational)

| Event | Alert | Channel |
|---|---|---|
| Step-up TOTP fail x3 in 5min | HIGH | Email + Slack |
| Login from new country | HIGH | Email |
| Admin role change | CRITICAL | Email + Slack + PagerDuty |
| Global kill switch toggled | CRITICAL | All channels + SMS |
| Audit log INSERT failure | CRITICAL | PagerDuty |
| Breakglass activated | HIGH | Slack + email |
| Multi-admin approval expired | LOW | Slack |
| Impersonation initiated | MEDIUM | Slack (private channel) |

---

## 12. References
- Threat model: `/docs/security/threat-model-admin.md`
- Incident response: `/docs/security/incident-response-admin.md`
- Onboarding: `/docs/security/admin-onboarding-runbook.md`
- Secure defaults: `/docs/security/secure-defaults.md` §18
- Secrets: `/docs/security/secrets-audit.md`
- Launch checklist: `/docs/security/live-trading-launch-checklist.md` §ADMIN
