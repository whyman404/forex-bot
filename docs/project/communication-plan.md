# Communication Plan — Forex/Crypto Trading Bot Platform

**Owner:** Zeus Ryujin
**Date:** 2026-06-14
**Cadence:** 1-week sprints, async-first

---

## 1. Principles

1. **Async-first.** Default to written communication that other timezones / future-you can read.
2. **One source of truth.** Decisions live in ADRs / charter / risk register. Chat is for nudges, not decisions.
3. **Surface blockers within 4h.** Silent blockers cost the team. Speak up = good.
4. **Status is honest.** RED is not failure, RED is information that triggers help.
5. **Sponsor reads one thing per week.** Friday status report. Anything else is escalation.

---

## 2. Daily Async Standup

**When:** Every weekday by 09:30 local time of each specialist (async — post by 09:30 your time)
**Where:** `team-channel` (or repo `/sync/standup/YYYY-MM-DD.md`)
**Format (per agent, 3 lines max):**

```
[YYYY-MM-DD] AGENT-NAME
- Yesterday: <one bullet>
- Today: <one bullet>
- Blocker: <NONE | specific issue + who can unblock>
```

**Zeus duty:**
- Read all standups by 11:00 ICT
- Flag blockers in `#blockers` thread
- Reply with action / who-owns within 4h
- Update sprint board

**Example:**
```
[2026-06-17] Kairos Toki
- Yesterday: Spec'd London Breakout entry + filter rules
- Today: Spec'd NY Killzone, start vectorbt notebook
- Blocker: Need Gold tick data — Hestia, can you confirm Dukascopy account today?
```

---

## 3. Sprint Cadence (1 week)

| Day | Event | Format | Duration | Attendees |
|-----|-------|--------|----------|-----------|
| **Mon AM** | Sprint Planning | Async doc + 30min sync if needed | Async: 1h to read+commit; Sync (optional): 30min | Zeus + all |
| **Mon-Fri** | Daily standup | Async post | < 5min per person | All |
| **Fri PM** | Sprint Demo | Recorded screen share (Loom) + comments thread | 15-30 min recording, async comments | All + sponsor (watch when ready) |
| **Sun PM** | Sprint Retro | Async retro doc (Mad/Sad/Glad/Action) | 1h to write+react | All |
| **Sun PM** | Sponsor Status Report | Email + repo file | 5 min read | Sponsor + team |

### Sprint Planning (Monday)
- Zeus opens `/sync/sprint/SPRINT-N-plan.md` with proposed goal + tickets per agent
- Each agent comments by EOD Monday: commit / push back / clarify
- Zeus locks plan by Monday 18:00; sprint starts

### Sprint Demo (Friday)
- Each agent records 2-5 min Loom showing what shipped this week
- Posted in `#demos` by Friday 17:00 local
- Sponsor watches over weekend; comments inline
- Zeus aggregates highlights into status report

### Sprint Retro (Sunday async)
- `/sync/sprint/SPRINT-N-retro.md` with 4 columns: Mad / Sad / Glad / Action
- Each agent adds ≥ 1 item per column by Sunday 21:00
- Zeus picks top 3 actions for next sprint; assigns owner

---

## 4. Sponsor Status Report — Friday Email Template

**Recipient:** whyman404@gmail.com
**Sent:** Every Friday by 18:00 ICT
**Format:** Markdown email (also archived at `/sync/status/SPRINT-N-status.md`)

```markdown
# Status Report — Sprint N (Date Range)

## Overall RAG: 🟢 GREEN / 🟡 AMBER / 🔴 RED

**One-line summary:** [What this week meant for the project in one sentence]

---

## Progress vs. Phase 1 (week N of 6)

| Milestone | Target | Status |
|-----------|--------|--------|
| M1 Design Freeze | End W2 | 🟢 / 🟡 / 🔴 |
| M2 Backtest Pass | End W4 | 🟢 / 🟡 / 🔴 |
| M3 Paper Trading | End W6 | 🟢 / 🟡 / 🔴 |

**Completion: X% of Phase 1 scope**

## Achievements (this week)
- [bullet 1]
- [bullet 2]
- [bullet 3]

## Demo Link
[Loom / video URL]

## Top Risks Status
| Risk | Movement | Action |
|------|----------|--------|
| R05 Overfit | unchanged HIGH | walk-forward in progress |
| R11 User loss | unchanged MED-CRIT | disclaimer draft ready |
| ... | | |

## Decisions Needed from Sponsor (within X days)
- [ ] [Decision A by date — context, options, recommendation]
- [ ] [Decision B by date]

(if none) "No decisions needed this week."

## Next Week
- Main goal: [...]
- Critical path: [agent / task]

## Burn
- Hosting cost MTD: $X (budget $100/mo)
- Effort: X agent-days used / Y planned

---
Zeus Ryujin, PM
```

**RAG color rule:**
- 🟢 GREEN: on track, no blockers, milestones at risk < 10%
- 🟡 AMBER: slip < 1 week, mitigation underway, milestone at risk 10-30%
- 🔴 RED: slip > 1 week OR milestone miss probable > 30% OR a kill criterion triggered → sponsor decision required

---

## 5. Escalation Path

| Trigger | Path | SLA |
|---------|------|-----|
| Blocker > 4h without owner | Agent → Zeus in #blockers | Zeus assigns within 4h |
| Blocker > 24h still open | Zeus → escalation thread + identify trade-off | Resolved or sponsor brief within 24h |
| Cross-team conflict | Zeus mediates async, decides if no consensus in 24h | Decision documented in ADR / decision log |
| CRITICAL risk trigger (R05 / R08 / R11 / R12 / R13) | Whoever detects → Zeus immediately | Zeus to sponsor within 4h with options |
| Kill criterion triggered (K1-K6) | Zeus → sponsor with options + recommendation | Sponsor decides within 48h |
| Security incident | Argus → Zeus → sponsor | Argus incident response < 1h; sponsor brief < 4h |
| Production outage in paper / live trading | Hestia + Atlas → Zeus | Status page-style update every 30min |

**Escalation rules:**
- Zeus never escalates a problem without a recommendation
- Sponsor only sees decisions, not just problems
- Documented: every escalation creates an entry in `/sync/escalations/YYYY-MM-DD-topic.md`

---

## 6. Decision Log

All cross-team or load-bearing decisions logged in `docs/decisions/YYYY-MM-DD-title.md`:
```markdown
# Decision: [title]
Date: YYYY-MM-DD
Maker: [name]
Context:
Options considered:
Decision:
Consequences:
Reversal cost:
```

Architectural decisions = ADR in `docs/architecture/adr/`.

---

## 7. Communication Channels

| Channel | Purpose | Response SLA |
|---------|---------|-------------|
| `#standup` | Daily async standup | by 11:00 ICT |
| `#blockers` | Active blockers | Zeus < 4h |
| `#decisions` | Decisions log + ADR notifications | informational |
| `#demos` | Sprint demos | weekend watch |
| `#incidents` | Production / outage | < 30 min ack |
| `#random` | Off-topic | none |
| Repo PR / issues | Async code review | < 24h |
| Email (sponsor) | Status report + escalation only | sponsor reads on own time |
| 1:1 sync (rare) | Conflict resolution | scheduled when needed |

**NO Slack DMs for decisions** — push to public channel or repo for traceability.

---

## 8. Meeting Discipline

Default: **no meetings**. If a meeting is needed:
- Must have written agenda 24h in advance
- Must end with written decisions + owners
- Max 45 min
- Recorded if possible
- "Could this be an async doc?" — yes 90% of the time

Sync meetings allowed:
- Sprint planning (optional 30min)
- Demo (optional join-live)
- Conflict resolution (when async fails after 24h)
- M1 / M2 / M3 gate review (Zeus + leads, 45min)

---

## 9. Documentation Conventions

| Doc Type | Location |
|----------|----------|
| Charter, roadmap, risks, comms | `docs/project/` |
| Architecture + ADR | `docs/architecture/` |
| API spec | `docs/api/` |
| Database schema | `docs/database/` |
| Strategy specs | `docs/strategies/` |
| Security | `docs/security/` |
| Testing | `docs/testing/` |
| Standups | `sync/standup/YYYY-MM-DD.md` |
| Sprint plans / retros / status | `sync/sprint/` and `sync/status/` |
| Escalations | `sync/escalations/` |
| Incidents | `sync/incidents/YYYY-MM-DD-name.md` |

**Format:** Markdown. **Diagrams:** Mermaid (inline) or Figma (linked).

---

## 10. Cultural Norms

- **Disagree and commit.** Argue your case fully — once a decision is made, support it.
- **Strong opinions, weakly held.** Bring data, change your mind when shown better.
- **Blameless postmortem.** Incident = system failure, not person failure.
- **Brevity is respect.** A 3-line standup beats a 10-line one.
- **Default to transparency.** Public channels > DMs.

---

_— Zeus Ryujin, 2026-06-14_
_This plan adapts to team feedback. Retro can amend any rule._
