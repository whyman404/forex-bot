# Postmortem — [Incident Title]

> Owner: [author]
> Date of incident: YYYY-MM-DD
> Date of postmortem: YYYY-MM-DD
> Severity: SEV-1 / SEV-2 / SEV-3 / SEV-4
> Status: draft / under review / final
>
> **Blameless.** This document is about systems, not individuals.

---

## Summary

One paragraph: what happened, who was impacted, how long, how resolved.

---

## Impact

- **Users affected:** [number, percentage of total active]
- **Duration:** [start UTC] → [end UTC] = [hh:mm]
- **Revenue impact:** $[estimated]
- **Trading impact:** [positions affected, P&L deviation if any]
- **Data loss:** [yes/no, scope]
- **External communication:** [status page update? email?]

---

## Timeline (UTC)

| Time | Event | Source |
|---|---|---|
| HH:MM | First symptom appears | Prometheus alert XYZ |
| HH:MM | On-call paged | PagerDuty |
| HH:MM | On-call acknowledges | Slack #incidents |
| HH:MM | Diagnosis: <…> | Grafana / Loki |
| HH:MM | Mitigation applied: <…> | command/PR link |
| HH:MM | Status page updated | Better Stack |
| HH:MM | Resolved — alerts cleared | Prometheus |
| HH:MM | Post-incident review starts | |

---

## Root cause(s)

Use 5-whys, not 5-blames.

1. Why did X fail? Because Y.
2. Why did Y happen? Because Z.
3. (continue)

### Contributing factors

- [ ] Monitoring gap (alert fired late / didn't fire)
- [ ] Deploy gap (no canary / no rollback test)
- [ ] Doc gap (runbook missing / wrong)
- [ ] Capacity gap (under-provisioned)
- [ ] Dependency gap (3rd-party failed)
- [ ] Process gap (no on-call coverage / handoff failed)

---

## What went well

- ...
- ...

---

## What went poorly

- ...
- ...

---

## Where we got lucky

This is the most important section. List things that, if changed slightly,
would have made the incident worse. These are future SEV-1s.

- ...

---

## Action items

Every action item MUST have an owner and a deadline. Items without these are
just venting — delete them.

| # | Description | Owner | Deadline | Status | Link |
|---|---|---|---|---|---|
| AI-1 | Add alert for X | @hestia | 2026-MM-DD | open | issue#... |
| AI-2 | Update runbook for Y | @author | 2026-MM-DD | open | PR#... |
| AI-3 | Capacity test for Z | @hestia | 2026-MM-DD | open | issue#... |
| AI-4 | Communicate change to team | @founder | 2026-MM-DD | open | — |

---

## Learnings

What pattern does this incident teach us about our systems?

1. ...
2. ...

These become entries in `dev-team/05-devops-hestia-kaoru/learning-log.md`
and `dev-team/05-devops-hestia-kaoru/skills/<pattern>.md`.

---

## Appendix

### Relevant graphs
[paste Grafana panel screenshots or links]

### Relevant log lines
```
[paste 5-10 representative log lines from Loki]
```

### Commands run
```
[the diagnostic + mitigation commands that worked, for the runbook]
```

### Links
- Slack incident channel: ...
- Pull request that caused/fixed it: ...
- Related issue: ...
