# Admin Setup — Single-source onboarding

> **Audience:** First operator bringing the platform up (laptop or Railway).
> **Time:** 5 minutes (dev) / 10 minutes (cloud).
> **Security model:** see `docs/security/admin-security.md` for the full
> privileged-access policy. This file is the operational quick reference.

The admin panel is **role-gated** — only users whose `users.role = 'admin'`
can see `/admin/*` or call `/api/v1/admin/*`. The first admin must be created
**out-of-band** via the seed script; subsequent admins are promoted from the
admin panel itself with step-up TOTP confirmation.

---

## 1 — Local dev

Credentials live in `.env.admin` at the repo root. **This file is gitignored**
(`.env.*` glob in `.gitignore`) and is the source of truth for your local box.

```bash
# .env.admin (already exists for whyman404@gmail.com)
ADMIN_EMAIL=whyman404@gmail.com
ADMIN_PASSWORD=...           # rotate after first login
ADMIN_FULL_NAME=Whyman404
ADMIN_COUNTRY=TH
```

Bring up the stack:

```bash
cd projects/forex-bot
./scripts/dev.sh
```

`scripts/dev.sh` injects `.env.admin` into the backend container's environment
and runs `python -m scripts.seed_admin --from-env` once during boot. The
script is **idempotent** — re-running does nothing if the admin already exists.

Open <http://localhost:3000> and sign in.

### First login checklist (dev or cloud)

1. Sign in with the seeded email + password.
2. Open `/settings/security` and **rotate the password**. The seed credential
   is only meant to bootstrap — never use it long-term.
3. **Enable TOTP** on the same page. This is required because destructive
   admin actions (`/admin/users/:id/ban`, `…/delete`, `…/impersonate`,
   `/admin/system/global-kill`, broadcast) demand a fresh 6-digit code in the
   `X-Step-Up-TOTP` header.
4. (Optional, recommended for prod) Set the IP allowlist for admin routes —
   `docs/security/admin-onboarding-runbook.md` §IP-allowlist documents the
   Caddy / Vercel firewall snippet.

---

## 2 — Railway (cloud)

The `.env.admin` file is **never pushed to git**. Instead, the same two
variables go into the Railway env panel, and you run the seed script once
in the Railway shell.

1. Open Railway → your backend service → **Variables**.
2. Add:
   - `ADMIN_EMAIL = <your real email>`
   - `ADMIN_PASSWORD = <openssl rand -base64 18>` (long random, **rotate after
     first login**)
   - `ADMIN_FULL_NAME = <your full name>`
   - `ADMIN_COUNTRY = <ISO 3166-1 alpha-2>` — e.g. `TH`, `US`, `GB`.
3. Trigger a new deploy so the variables are visible to the service.
4. Open the Railway **Shell** for the backend service:
   ```bash
   python -m scripts.seed_admin --from-env
   ```
5. Expected output: `seed_admin: created admin <your-email>` (or
   `already exists; no-op` if you've run it before).
6. Sign in at your Vercel URL and follow the **First login checklist** above.

### Why env panel and not a secret file?

Railway env vars are injected at process start and never written to disk.
A `.env.admin` file in the deploy would be a long-lived secret in storage
(image layer or volume); env panel is shorter-lived and rotates naturally
when the service redeploys.

---

## 3 — Adding a second admin

Once the first admin is signed in **and has TOTP enrolled**, never run the
seed script again. Promote new admins from the UI:

1. First admin signs in.
2. Open `/admin/users` and search for the user to promote.
3. Click the user → **Change role** → select `admin` → enter your 6-digit TOTP
   code in the step-up modal → confirm.
4. The audit log (`/admin/audit-log`) records the change with both the actor
   (you) and the target user.

The target user gets admin access on their next access-token refresh
(within ~15 min) or immediately if they sign out and back in.

### Demoting an admin

Same flow in reverse. `require_admin` re-fetches `users.role` from the DB on
every admin request, so a demotion takes effect on the next admin API call —
no token-blacklist required.

---

## 4 — Recovery — lost TOTP / lost admin

This is intentionally **out-of-band only**:

1. SSH/Railway-shell into the backend service.
2. Open a Postgres shell:
   ```bash
   psql "$DATABASE_URL"
   ```
3. Reset the TOTP secret (re-enroll on next sign-in):
   ```sql
   UPDATE users SET totp_secret = NULL, totp_enabled = false
   WHERE email = '<your-email>';
   ```
4. If the user lost the password too, also reset:
   ```sql
   UPDATE users SET password_hash = NULL
   WHERE email = '<your-email>';
   ```
   Then trigger a password-reset email from `/forgot-password`.

Audit log this manually in the incident channel — there is no app-layer
"reset my own admin TOTP" button on purpose.

See `docs/security/incident-response-admin.md` for the full incident-response
playbook including admin account compromise.

---

## 5 — Credentials hygiene

| File / location | Contains | Source of truth | Lives where |
|---|---|---|---|
| `.env.admin` | First-admin seed creds (dev) | Yes for **local dev only** | Your laptop only; gitignored. |
| Railway env panel | First-admin seed creds (cloud) | Yes for **cloud** | Railway only; rotated via panel. |
| `users.password_hash` (DB) | Hashed login password (argon2id) | Yes after first login | Postgres. |
| `users.totp_secret` (DB) | Envelope-encrypted TOTP secret | Yes after enrollment | Postgres. |

The seed credential is **single-use**. After step 1-2 of the First-login
checklist (rotate password + enable TOTP), the values in `.env.admin` /
Railway env panel are no longer the active credentials — the DB is.

You can revoke them by deleting the env vars from Railway. Keep `.env.admin`
on your laptop as a recovery hint, but treat it as **stale** — the live
credentials are in the DB.

---

## 6 — Related docs

- `docs/security/admin-security.md` — privileged access model, separation of duties.
- `docs/security/threat-model-admin.md` — STRIDE + 10 attack scenarios.
- `docs/security/incident-response-admin.md` — admin compromise playbook.
- `docs/security/admin-onboarding-runbook.md` — full operator runbook.
- `docs/security/live-trading-launch-checklist.md` — Section ADMIN (AD1-AD18) launch gates.
- `docs/api/openapi.yaml` — all 22 admin endpoints under tag `admin`.
