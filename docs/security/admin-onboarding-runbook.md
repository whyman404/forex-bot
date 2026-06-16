# Admin Onboarding Runbook

**Audience:** new admin operators
**Owner:** Argus Hayato
**Last updated:** 2026-06-16

> Welcome. Admin role is the highest-trust position in the system. Read this fully before performing any action.

---

## 0. Acceptable Use Acknowledgement

Before activation, new admin must sign acknowledgement:
- I will not impersonate users without a documented support ticket
- I will not export user data beyond what's needed for support
- I understand all my actions are logged and reviewed weekly
- I will report any suspected compromise of my account within 1 hour
- I will use the official admin panel only (not direct DB)
- I will not share my TOTP / passkey with anyone, including teammates

Signed: _________________ Date: _________________

---

## 1. Activation Flow

### 1.1 First Login (Seeded Admin)
1. Visit `/admin/login` from approved network (IP allowlist enforced if configured)
2. Use email + the seeded `ADMIN_PASSWORD`
3. UI forces password change immediately (`force_password_change=true`)
4. New password requirements:
   - 16+ characters
   - Mixed case + digits + symbols
   - Not in common-password list
   - Not previously used (history 5)
5. UI forces TOTP enrollment immediately:
   - Scan QR with authenticator app (Aegis, 1Password, Authy)
   - Verify with 2 consecutive codes
   - Download backup codes (8 single-use), store in password manager
6. (Recommended) Enroll passkey (WebAuthn) — post-launch feature

### 1.2 Subsequent Admin (Created by Existing Admin)
1. Existing admin creates account via `POST /admin/users/admin-create` (step-up TOTP)
2. Multi-admin approval required (n=2 if ≥2 admins)
3. New admin receives email with one-time activation link (expires 24h)
4. New admin completes flow §1.1 steps 4-6

---

## 2. Daily Workflow

### 2.1 Session
- Sessions last 24h max
- Re-login forced after 24h (cron job revokes)
- Concurrent session limit: 2

### 2.2 IP Allowlist
- If you work from a new location (travel, home), request IP added via existing admin
- For emergency: use breakglass procedure (§5)

### 2.3 Read Operations (no step-up)
- View user list, search
- View subscription status
- View audit log (your reads are themselves logged — privacy reciprocity)
- View system status

### 2.4 Write Operations (step-up TOTP required)
- Impersonate user
- Reset user password
- Suspend / unsuspend user
- Cancel / refund subscription (Stripe-backed)
- Override sub tier (e.g. comp account)
- Send broadcast email
- Toggle global kill switch
- Change another admin's role

---

## 3. Using Step-Up TOTP

### When prompted
1. Open authenticator app
2. Enter 6-digit code into modal
3. Submit
4. Action executes if code valid

### Replay protection
- Each code single-use per action+target
- Don't try to reuse — wait next 30s window
- 3 failed attempts in 5min → 30min lockout + alert

### If TOTP lost
- Use backup code (8 available, single-use each)
- After all backups used → contact second admin to reset (multi-admin approval)

---

## 4. Impersonation — Sensitive Operation

### When to use
- Support ticket where user gave consent (in ticket conversation)
- Investigation of suspected fraud (legal documented)
- Reproducing a bug a user reported

### When NOT to use
- "Just checking" — never
- Looking at another admin
- Yourself
- Without a ticket / documented reason

### Flow
1. Open user record in admin panel
2. Click "Impersonate"
3. Fill reason (10+ chars) + ticket id
4. Step-up TOTP
5. New tab opens as that user (max 5min)
6. Do only what's needed
7. Close tab → impersonation ends

### Restrictions (server-enforced)
🔴 You CANNOT during impersonation:
- Delete anything
- Change broker credentials
- Flip paper → live
- Withdraw / payout
- Change user's email / password / TOTP
- Manage user's payment method
- Use any `/admin/*` endpoint
- Impersonate another admin

### User notification
- User receives email summary daily of all impersonation sessions
- Be professional — your actions are visible to them

---

## 5. Multi-Admin Approval

### When required
- Global kill switch
- Demote / ban / delete another admin
- Bulk delete > 50 users
- Mass broadcast > 10k recipients
- KEK rotation
- Full audit log export

### Your role as initiator
1. Click destructive action
2. Step-up TOTP
3. Request enters `pending` state, expires 15min
4. Notify second admin in Slack #admin-approvals
5. Wait for approval

### Your role as approver
1. Watch Slack #admin-approvals OR poll panel
2. Click pending request
3. Review action + target + payload + initiator name
4. If suspicious: REJECT + DM initiator OR escalate to security
5. If legit: step-up TOTP → approve
6. Action executes immediately

### You CANNOT
- Approve your own request
- Approve after expiry
- Approve while not active admin

---

## 6. Breakglass (Emergency Access)

### When
- You need admin access urgently from outside IP allowlist
- Other admin unreachable

### Procedure
1. Notify in #incidents that breakglass is being engaged
2. SSH to host, set `ADMIN_BREAKGLASS=true`
3. Restart admin API process
4. You have 30 minutes from process start
5. All other controls still apply (step-up TOTP, multi-admin)
6. After: unset env, restart, write post-incident note

### Audit
- Every request during breakglass logs `breakglass_active=true`
- Security reviews within 24h
- Mis-use grounds for role revocation

---

## 7. Reading the Audit Log

### Access
- Panel: `/admin/audit-log` (filtered, paginated)
- Filters: actor_id, action, target_id, date range
- Export limited to 1000 rows / day (full export needs multi-admin)

### What you can see
- All admin actions (including your own)
- Includes IP, UA, before/after diff
- Excludes PII (passwords, broker creds — REDACTED)

### What to look for (weekly review)
- Any actor performing more impersonations than usual
- Failed step-up attempts
- Breakglass activations
- Multi-admin approvals — was the second approval thoughtful or rubber-stamp?

---

## 8. When to Ask for Second Approval (even if not required)

Use judgment beyond minimum policy:
- Action affects > 100 users → 2nd opinion
- Action involves money movement → 2nd opinion
- You feel uncertain or pressured → 2nd opinion + Slack security
- Unusual hours / fatigue / unfamiliar request → 2nd opinion

When in doubt → ask. Security team never penalizes asking.

---

## 9. Reporting Suspected Compromise

If you suspect:
- Your password leaked
- Your TOTP secret seen by someone
- Your laptop lost / stolen
- Strange email asking for credentials
- Unusual login alert you didn't trigger

**Within 1 hour:**
1. From a different device, page security via PagerDuty `forex-bot-sev1`
2. Slack #security-incidents
3. Do NOT log in to admin panel until cleared

---

## 10. Quarterly Review

Every quarter (calendar Q1/Q2/Q3/Q4):
- Confirm you still need admin role (revoke if dormant)
- Re-read this runbook
- Re-sign acceptable use
- Verify TOTP backup codes still accessible
- Verify panel access from primary network works
- Run a fire drill: simulated impersonation + approval

---

## References
- `/docs/security/admin-security.md` — full policy
- `/docs/security/threat-model-admin.md` — what we defend against
- `/docs/security/incident-response-admin.md` — what to do when it goes wrong
