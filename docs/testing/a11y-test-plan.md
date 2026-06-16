# Accessibility Test Plan

**Owner:** Themis Saori
**Standard:** WCAG 2.1 Level AA
**Updated:** 2026-06-14

A trading dashboard must be usable by everyone, including users with motor / vision / cognitive needs. The **kill switch** must remain reachable under all assistive tech conditions — failure there is a financial safety issue, not a polish issue.

---

## 1. Automated coverage — axe-core/playwright

Run on every PR for the following pages:

| Page | Critical? | Threshold |
|---|---|---|
| `/` (marketing) | Yes | 0 axe `serious`+ |
| `/login` | Yes | 0 axe `serious`+ |
| `/signup` | Yes | 0 axe `serious`+ |
| `/reset-password` | Yes | 0 axe `serious`+ |
| `/dashboard` | Yes | 0 axe `serious`+ |
| `/strategies` | Yes | 0 axe `serious`+ |
| `/strategies/:id` | Yes | 0 axe `serious`+ |
| **Kill switch modal** | **CRITICAL** | 0 axe `moderate`+ |
| `/billing` | Yes | 0 axe `serious`+ |
| `/settings/security` | Yes | 0 axe `serious`+ |

Example:
```ts
import AxeBuilder from '@axe-core/playwright';

test('dashboard a11y', async ({ page }) => {
  await page.goto('/dashboard');
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze();
  expect(results.violations.filter(v => ['serious','critical'].includes(v.impact))).toEqual([]);
});
```

---

## 2. Manual review (per sprint, per touched page)

Use these heuristics:

### Keyboard
- Tab order is logical and complete.
- Visible focus indicator on every interactive element.
- All actions reachable without mouse — including **kill switch** (focusable, Enter activates, ESC closes confirm).
- Skip-to-main-content link first in Tab order.
- No keyboard trap (except modal focus trap that exits with ESC).

### Screen reader (NVDA Windows + VoiceOver macOS — minimum)
- Page title announced.
- Headings hierarchy logical (h1 → h2 → h3, no skips).
- Form fields associated with `<label>`.
- Errors announced via `aria-live=polite` (validation) and `assertive` for blocking errors.
- Kill switch button announces: "Stop strategy <name>, button". Confirm dialog announces: "Confirm stop strategy. Press Enter to confirm, Escape to cancel".
- Charts have text alternative (table or summary text).
- Status changes (strategy running → stopped) announced via `aria-live`.

### Color + contrast
- Text contrast ≥ 4.5:1 (≥ 3:1 for large).
- Status not conveyed by color alone (red/green: also has icon + text).
- Focus indicator ≥ 3:1 against background.

### Motion + animation
- `prefers-reduced-motion` respected — chart animation, modal animation disabled.
- No flashing content > 3 Hz.

### Zoom + responsive
- 200% zoom in browser — no horizontal scroll, no clipped content.
- 400% zoom — content reflows; kill switch remains reachable.

### Cognitive
- Plain language for confirms ("Stop strategy?" not "Halt instance?").
- Critical actions (stop, delete, withdraw) require confirmation.
- Time-out warnings give user the option to extend.

---

## 3. Kill switch a11y spec (highest priority)

Independent acceptance criteria:

```
The kill switch shall:
1. Be a single, primary-colored button labeled "Stop strategy".
2. Have aria-label "Stop strategy <name>".
3. Be reachable within ≤ 5 Tab key presses from /dashboard load.
4. Have a focus indicator visible at 4.5:1 contrast against background.
5. Open a confirm dialog with focus auto-moved to "Confirm" button.
6. Allow ESC to close confirm without stopping.
7. Allow Enter on confirm to stop.
8. Announce result via aria-live=assertive ("Strategy stopped").
9. Work without JavaScript-disabled? No — but must show a clear noscript message; the dashboard requires JS.
10. Pass axe with 0 serious or critical findings.
```

Automated test in `e2e/start-paper-and-kill.spec.ts` (see e2e-flows.md Flow 5).

---

## 4. Tooling

- `@axe-core/playwright` — automated.
- NVDA (Windows) + VoiceOver (macOS) + JAWS spot-check pre-release.
- WAVE / Lighthouse accessibility audit per release.
- Color contrast: TPGi Color Contrast Analyzer.

---

## 5. Reporting

- Per page: `docs/testing/a11y-reports/<page>-YYYY-MM-DD.md` with axe JSON, manual checklist, screenshots, remediation notes.
- Sprint summary: open WCAG issues by severity.
- Pre-release: full audit signoff.

---

## 6. Release gate

- 0 critical or serious axe findings on critical pages.
- Manual review signed off on kill switch + auth pages.
- No known WCAG 2.1 AA failures on a critical page.
