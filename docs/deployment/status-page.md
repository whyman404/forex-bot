# Status Page & Uptime Monitoring

> Owner: Hestia Kaoru
> Last updated: 2026-06-15

---

## Recommendation

**Use Better Stack (better-stack.com, formerly betterstack.com / betteruptime)
for both uptime monitoring and the public status page.** Single vendor, single
bill, well-designed UI, free tier covers our needs at MVP scale.

| Need | Better Stack | UptimeRobot | Atlassian Statuspage |
|---|---|---|---|
| Public status page | included | basic ($30/mo for custom) | $29/mo |
| Uptime monitoring | included | free 50 monitors | separate |
| Incident creation API | yes | yes | yes |
| Custom domain | yes ($18/mo) | yes ($29/mo) | yes |
| Slack integration | yes | yes | yes |
| Cost at MVP | free → $18/mo | free | $29/mo |

Fallback choice if Better Stack pricing changes: UptimeRobot free + Statuspage
free tier.

---

## Monitors to configure

Each monitor probes from 3 geographic regions (lowers false-positives).

| Monitor | URL / Check | Interval | Failure threshold |
|---|---|---|---|
| Frontend | https://forexbot.example.com | 60s | 2 fails |
| Backend healthz | https://api.forexbot.example.com/healthz | 30s | 2 fails |
| Backend readyz | https://api.forexbot.example.com/readyz | 60s | 3 fails |
| Stripe webhook | https://api.forexbot.example.com/api/v1/stripe/health | 5m | 3 fails |
| MT5 bridge (internal) | n/a — Prometheus alert covers it | n/a | n/a |
| Postgres pool | n/a — covered by /readyz | n/a | n/a |
| Login flow synthetic | POST /api/v1/auth/login with test account | 5m | 2 fails |

**Synthetic login:** create a dedicated test user (`status-monitor@internal`)
with a non-rotating password stored in 1Password. Better Stack hits it every
5 min and asserts response contains `accessToken`. This catches regressions
that bypass /healthz.

---

## Public status page

URL: `https://status.forexbot.example.com` (CNAME → `stats.betterstack.com`).

### Components shown

- **Frontend (Web App)**
- **Backend API**
- **Trading (live engine + MT5 bridge)** — single composite; users only care that trading works
- **Database** — only show if degraded (don't expose internals when ok)
- **Backups & DR** — show last successful backup, last verify drill

### Incidents

Auto-create when a monitor goes red. Manual incidents for planned maintenance.

Template for incident posts (publish via Better Stack API):

```
Investigating
We're seeing elevated error rates on the Backend API. Our team is on it.
We'll update in 15 minutes.
```

```
Identified
The Stripe webhook handler is returning 500 due to a missing event type
mapping. We're deploying a fix.
```

```
Monitoring
The fix is deployed. We're watching for regressions.
```

```
Resolved
Issue resolved. Total impact: 14 minutes, no transactions lost.
We will publish a postmortem in 48 hours.
```

---

## Webhook → Slack flow

Better Stack → webhook → `#alerts-critical` Slack channel.

When the public status page changes (incident opened/updated), a Slack message
is auto-posted. This keeps non-engineering teammates informed without forcing
them to refresh the status page.

---

## On-call rotation tie-in

Better Stack also supports an on-call schedule (PagerDuty-style). For MVP
(single founder + one ops), this is overkill — use PagerDuty's free tier.

When team grows to 3+, consolidate everything in Better Stack:
- monitoring + status + on-call + incidents in one tool
- saves ~$30/mo vs separate PagerDuty subscription

---

## Setup steps (one-time)

1. Create Better Stack account at https://betterstack.com.
2. Add monitors per table above. Use the "Add monitor" wizard.
3. Add team members (whyman404@gmail.com + ops alias).
4. Create status page → "Forex Bot Status" → add components.
5. Connect status page to monitors (component goes red when monitor red).
6. Add custom domain: status.forexbot.example.com. Add CNAME in Cloudflare,
   verify, request SSL.
7. Webhooks → Slack integration → connect Slack workspace, pick channel.
8. Status page → Subscribers: enable email + Slack subscribe buttons for
   end users.

Test: manually pause one monitor → verify status page goes orange + Slack
post appears.

---

## Embedding status in the app

Add `<StatusBadge />` in the app footer (`frontend/src/components/footer.tsx`):

```tsx
<a href="https://status.forexbot.example.com" target="_blank" rel="noopener">
  <img src="https://status.forexbot.example.com/badge" alt="Status" />
</a>
```

The badge auto-updates from Better Stack — no extra polling on our end.
