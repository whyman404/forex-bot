# Kill Switch — Specification

> The "panic button". Stops trading. Multiple triggers, low-friction, hard to break.
> **Author:** Argus Hayato | **Date:** 2026-06-14
> **Coordinates with:** Daedalus (architecture), Kairos (trading engine), Atlas (API), Eos (UI).

---

## 0. Why this matters

A trading bot WITHOUT a reliable kill switch is a liability. Market regime changes, strategy bugs, broker glitches — any of these can wipe an account quickly. The kill switch is the last line of defense and must be:

- **Fast** (one click).
- **Always available** (separate rate-limit lane, separate path).
- **Multi-trigger** (user, admin, automatic).
- **Auditable** (every flip logged).
- **Reversible** (re-arm flow with safeguards).

---

## 1. Scope levels

| Scope | Effect | Who can trigger |
|-------|--------|-----------------|
| **User-account-level** | Stops trading for one user only | User, admin, automatic per-user triggers |
| **Strategy-level** | Stops one strategy across all users | Admin, automatic strategy triggers |
| **Global** | Stops all trading platform-wide | Admin only, automatic global triggers |

Higher scope wins. Global ON → user-level state irrelevant.

---

## 2. State model

```
States: ARMED → TRIPPED → COOLDOWN → ARMED

ARMED:    trading allowed (live)
TRIPPED:  trading blocked, open positions handled per policy (see §5)
COOLDOWN: trading blocked until cooldown elapsed + user re-arm action
```

Stored per scope:
- `kill_state` table: `(scope, scope_id, state, tripped_at, tripped_by, tripped_reason, cooldown_until)`
- Indexed by `(scope, scope_id)` for fast lookup.
- Replicated to Redis for hot-path check (TTL refreshed; DB authoritative).

---

## 3. Triggers

### 3.1 User-side (UI button)

- **Location:** Dashboard top bar — large red "EMERGENCY STOP" button always visible.
- **Click flow (no confirm in emergency):**
  - Single click → trigger.
  - No "Are you sure?" modal (too slow in emergency).
  - Toast appears: "Trading stopped. Strategies paused. Confirm action?" with [Undo within 30s] option.
  - Audit log records click + later "undo" if used.
- **Affects:** that user's account only.
- **Auth:** existing session; if session expired, separate "Emergency stop" mini-page allows email + simple verification (HIBP-aware password) + immediate trip without full login.

### 3.2 Admin override

- **Admin dashboard** has Kill Switch panel:
  - Per-user kill / un-kill
  - Per-strategy kill / un-kill
  - Global kill / un-kill
- **2-person rule** for global kill / un-kill (require second admin approval within 5 min, or global stays in pending state).
- All admin kill actions: audit log + Slack alert.

### 3.3 Automatic triggers — per user

| Trigger | Threshold | Action |
|---------|----------|--------|
| Max drawdown breach | User-set limit (default 20%) | Trip user-level |
| Daily loss breach | User-set limit (default 5% of balance) | Trip user-level |
| Broker disconnect > 5 min | Per-user trading session | Trip user-level + notify |
| Abnormal order volume | > 10× user's 7-day p95 | Trip user-level + admin alert |
| MT5 margin level critical | < 200% | Trip user-level + warn |
| Strategy returns NaN / inf | Any | Trip strategy-level |

### 3.4 Automatic triggers — global

| Trigger | Threshold | Action |
|---------|----------|--------|
| Engine error rate > X / min | Sustained 2 min | Trip global |
| Order rejection rate > Y % | Sustained 5 min | Trip global |
| Broker API down platform-wide | All users disconnected | Trip global |
| Anomaly: orders placed for users with live mode OFF | Even 1 occurrence | Trip global + page on-call |
| Strategy file hash mismatch on load | On startup | Refuse to start engine (= global trip) |

---

## 4. Architecture

### 4.1 Hot-path check

Before every `place_order` call in the trading engine:

```python
def can_trade(user_id, strategy_id) -> tuple[bool, str | None]:
    # Check global
    if redis.get("kill:global"):
        return False, "global kill"
    # Check strategy
    if redis.get(f"kill:strategy:{strategy_id}"):
        return False, "strategy kill"
    # Check user
    if redis.get(f"kill:user:{user_id}"):
        return False, "user kill"
    return True, None
```

- Redis check ~1ms; DB authoritative state synced.
- On Redis miss, fall back to DB (fail-closed: if both Redis and DB unreachable → assume tripped).

### 4.2 Endpoints

- **`POST /api/v1/kill`** — user-self kill (own account).
- **`POST /api/v1/kill/rearm`** — user re-arm (requires step-up + cooldown).
- **`POST /api/v1/admin/kill`** — admin kill (scope param).
- **`POST /api/v1/admin/kill/rearm`** — admin re-arm.

**Rate limits:**
- User kill: separate lane in Redis (`kill_limit:<user_id>`), 10/min — generous to allow panic-clicking.
- User re-arm: 3/hour, requires step-up auth.
- Admin: bypass user rate limits but logged.

### 4.3 Frontend

- Big red button persistent (header).
- Toast confirm with undo.
- Status indicator on dashboard: "Trading: ARMED / TRIPPED" with color.
- After trip, dashboard shows: cause, since when, when can re-arm, what's needed to re-arm.

### 4.4 Engine

- Watcher subscribes to Redis pub/sub channel `kill_state_changes`.
- On TRIP event: immediately cancel pending orders in queue for that scope.
- Existing positions: policy (see §5).

---

## 5. What happens to existing positions on TRIP?

This is **policy** per scope and per user preference. Defaults:

| Preference | Behavior |
|-----------|---------|
| **Hold** (default) | Existing positions remain. Stop loss / take profit still managed if engine partially up; otherwise user manages manually via MT5. |
| **Close-all** | Engine closes all open positions market order. **Risky in fast markets** (slippage). Opt-in. |
| **Hedge** | Open opposite positions to neutralize. **Advanced**, may not be supported by broker. Phase-3. |

**Recommended default: HOLD** — close-all in panic during a flash event often makes loss worse.

User picks default in settings; one-time choice with confirmation.

---

## 6. Re-arm flow

To go ARMED again:

1. Cooldown must elapse (default 15 min after auto-trip; 0 for user-trip).
2. User clicks "Re-arm" → step-up re-auth (re-enter password + 2FA).
3. Confirmation screen:
   - "You are about to resume trading. Current account balance: X. Open positions: Y. Are you sure?" with type-to-confirm "I UNDERSTAND".
4. Audit log entry.
5. Strategy resumes from next signal (no replay of missed signals).

If auto-tripped by max DD / daily loss breach: user must explicitly raise threshold OR wait 24h (whichever they prefer).

Admin re-arm: same flow + reason field + Slack notification.

---

## 7. Testing

### 7.1 Unit tests

- `can_trade` returns False under each scope.
- Redis miss falls back to DB.
- Both Redis + DB miss → fail closed.

### 7.2 Integration tests

- Trigger via API, verify engine refuses next order within 100ms.
- Concurrent place_order vs kill: kill wins (race condition test).

### 7.3 Chaos drill (semi-annual)

- During staging trading session with paper orders flowing:
  - Trigger user kill → verify orders stop within 1s.
  - Trigger global kill → verify all stop within 5s.
  - Simulate broker disconnect → auto-trip fires within 5 min.
  - Simulate kill switch rate-limit attack (flood `/orders`) → kill endpoint still responsive.

### 7.4 Load test

- 1000 concurrent users all clicking kill → all succeed within 5s p95.
- Validate Redis isn't bottleneck.

---

## 8. Failure modes & mitigations

| Failure | Mitigation |
|---------|-----------|
| Redis down | DB-only check, slower but works. Cache result for 1s in process. |
| DB down | Last-known state in process memory, fail-closed if older than X seconds. |
| Engine doesn't honor kill | Watchdog: control plane forcefully kills engine process if order placed during kill state. |
| Broker doesn't honor cancel | Reconciliation cron checks broker state vs platform state; flag mismatch. |
| User can't access UI | Email-based emergency stop (one-time link, separate path). Phone hotline (Phase-3). |
| Attacker tries to spam-kill all users | Auth required, rate-limited; admin alert on mass kill events. |
| Attacker tries to un-kill | Re-arm requires step-up + 2FA + audit. |

---

## 9. UX notes

- **Color/iconography:** big red, recognizable as "stop", consistent across pages.
- **Affordance:** even non-technical users should understand at first glance.
- **Confirmation:** asymmetric — kill is one click (cost of accidental kill = paused trading, low harm); re-arm requires deliberate action (cost of accidental re-arm = unintended trades, high harm).
- **Status visibility:** state shown on every screen, not buried in settings.

---

## 10. Compliance / Disclosure

- Kill switch existence + behavior described in T&C and help docs.
- Users informed of auto-triggers and how to configure thresholds.
- Audit log retained per audit log retention policy (5 years for events involving auto-trip on financial limits — useful for any later dispute).

---

## 11. Open questions

- Phone-based kill (call a number → kill)? — defer to Phase-3.
- SMS confirmation as alternative 2FA channel for emergency re-arm? — defer.
- Per-strategy user-level kill? — defer; for now, user trip = all their strategies stop.
