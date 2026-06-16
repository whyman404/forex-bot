# Accessibility Checklist — Trading Bot SaaS
**Author:** Iris Kaguya (UX/UI Designer)
**Date:** 2026-06-14
**Standard:** WCAG 2.1 Level AA (target: full compliance)
**Priority areas:** Financial data color usage, keyboard emergency stop, chart screen reader access, dark-mode contrast

---

## Color and Contrast

### 1.4.3 — Contrast (Minimum) — Level AA

Minimum 4.5:1 for normal text, 3:1 for large text (18px+ regular or 14px+ bold).

| Element | Foreground | Background | Ratio | Status |
|---|---|---|---|---|
| Primary body text | gray-100 (#F3F4F6) | gray-900 (#111827) | 15.8:1 | Pass |
| Secondary text | gray-400 (#9CA3AF) | gray-900 (#111827) | 6.4:1 | Pass |
| Disabled text | gray-600 (#4B5563) | gray-800 (#1F2937) | 2.8:1 | Exempt (disabled) |
| Brand primary btn | white (#FFF) | brand-800 (#065F46) | 9.2:1 | Pass |
| Danger button | white (#FFF) | loss (#DC2626) | 4.6:1 | Pass |
| Profit text | profit-light (#BBF7D0) | gray-900 (#111827) | 10.1:1 | Pass |
| Loss text | loss-light (#FECACA) | gray-900 (#111827) | 8.7:1 | Pass |
| Chart tooltip text | gray-100 | gray-900 | 15.8:1 | Pass |
| Axis labels (chart) | gray-500 (#6B7280) | gray-950 (#030712) | 5.2:1 | Pass |
| Input placeholder | gray-600 (#4B5563) | gray-800 (#1F2937) | 2.8:1 | Fail — must use gray-500 minimum |

**Action:** Update placeholder color to gray-500 (#6B7280) on gray-800 background — ratio 4.0:1 (borderline, test). Use gray-400 on gray-900 for safe compliance.

### 1.4.11 — Non-text Contrast — Level AA

UI components and graphical objects must have 3:1 against adjacent colors.

| Component | Component color | Adjacent bg | Ratio | Status |
|---|---|---|---|---|
| Input border (default) | gray-700 (#374151) | gray-900 (#111827) | 2.4:1 | Fail — upgrade to gray-600 |
| Input border (focus) | brand-600 (#059669) | gray-900 (#111827) | 5.8:1 | Pass |
| Profit chart line | #059669 | gray-950 (#030712) | 5.5:1 | Pass |
| Drawdown chart line | #DC2626 | gray-950 (#030712) | 4.3:1 | Pass |
| Status ● LIVE dot | #16A34A | gray-900 (#111827) | 4.9:1 | Pass |

**Action:** Default input border must be gray-600 (#4B5563) minimum for 3:1 against gray-900.

---

## Color-Only Prohibition (critical for trading app)

### 1.4.1 — Use of Color — Level A

**Color must never be the sole means of conveying information.**

This is the highest-priority accessibility rule for a trading dashboard.

| Information type | Prohibited (color only) | Required implementation |
|---|---|---|
| P&L positive | Green text only | ▲ symbol + "+" sign + green color |
| P&L negative | Red text only | ▼ symbol + "−" sign + red color |
| Strategy LIVE | Green indicator only | ● filled circle + "LIVE" text label |
| Strategy PAPER | Amber indicator only | ◑ half circle + "PAPER" text label |
| Strategy OFF | Gray indicator only | ○ empty circle + "OFF" text label |
| Backtest heatmap positive | Green cell only | Green bg + "+" percentage text |
| Backtest heatmap negative | Red cell only | Red bg + "−" percentage text |
| Form field error | Red border only | Red border + ✕ icon + error message text |
| Form field success | Green border only | Green border + ✓ icon + confirmation text |
| Chart equity up | Rising green line | Line + labeled tooltip + data table |
| Emergency stop button | Red button only | ■ icon + "STOP ALL TRADING" text |

**Rule:** If a user with deuteranopia (red-green colorblindness, affects 8% of male users) cannot understand the information, the implementation fails.

---

## Keyboard Navigation

### 2.1.1 — Keyboard — Level A

All functionality must be available via keyboard.

**Emergency Kill Switch — Critical Path:**

```
Tab order:
1. Header logo (skip link target)
2. Main navigation items
3. "STOP ALL TRADING" button (Tab to reach)
4. [Modal opens]
5. "Cancel" button (default focus)
6. "Confirm Stop" button
7. Return to page on dismiss

Required keyboard behaviors:
- Tab from any focused element → reaches "STOP ALL TRADING" within ≤ 10 Tab presses
- Enter/Space on button → opens modal
- Tab inside modal → cycles Cancel → Confirm → Cancel (trapped)
- Shift+Tab → reverse cycle
- Escape → activates Cancel (never Confirm)
- Enter on focused Cancel → Cancel
- Enter on focused Confirm → Execute stop
```

**Strategy Forms:**
- All inputs: Tab reachable, Enter submits
- Dropdowns: Arrow keys navigate options, Enter selects, Escape closes
- Date pickers: Arrow keys navigate calendar, Enter selects date
- Number inputs with ↑↓ arrows: arrow keys increment/decrement values

**Charts:**
- Equity curve: focusable with Tab
- Left/Right arrow keys: move crosshair along time axis
- Value at crosshair position announced to screen reader
- Tab away exits chart interaction

### 2.1.2 — No Keyboard Trap — Level A

- Modals: Escape always available to close (except emergency stop — Escape = Cancel = safe)
- Dropdown menus: Escape closes
- Date pickers: Escape closes
- Charts: Tab exits chart, does not trap

### 2.4.3 — Focus Order — Level A

Focus order follows visual reading order (top → bottom, left → right). Emergency stop button position in header ensures it is reachable early in the Tab sequence.

### 2.4.7 — Focus Visible — Level AA

All interactive elements show a visible focus indicator:
- Minimum: 2px solid ring, brand-500 color, 2px offset
- Do not use CSS `outline: none` without replacing with custom focus ring
- Focus ring must achieve 3:1 contrast against adjacent background

---

## Screen Reader Support

### 1.1.1 — Non-text Content — Level A

| Element | Required alt/label |
|---|---|
| Logo image | alt="TradingBot — Home" |
| Status icons (●◑○) | aria-label="Status: Live" / "Paper" / "Off" |
| P&L arrows (▲▼) | aria-hidden="true" — text and sign carry meaning |
| Chart (equity curve) | role="img" aria-label="Equity curve for London Breakout strategy. Period: Jun 2024 to Jun 2025. Start: $10,000. End: $11,420. Max drawdown: -11.2%." |
| Spark charts on strategy cards | aria-label="30-day equity trend, [up/flat/down]" |
| Loading spinner | aria-label="Loading" role="status" |
| Modal | role="dialog" aria-modal="true" aria-labelledby="modal-title" |

### Charts — Screen Reader Data Table

Every chart must have a visually hidden data table as an alternative:

```html
<figure>
  <div aria-hidden="true">
    <!-- visual chart canvas -->
  </div>
  <figcaption class="sr-only">
    Equity curve: London Breakout strategy, January 2024 to June 2025.
    Starting balance $10,000. Ending balance $11,420 (+14.2%).
    Maximum drawdown: -11.2% (July 2024).
  </figcaption>
  <table class="sr-only">
    <caption>Monthly equity values</caption>
    <thead>
      <tr><th>Month</th><th>Equity</th><th>Change</th></tr>
    </thead>
    <tbody>
      <tr><td>Jan 2024</td><td>$10,210</td><td>+2.1%</td></tr>
      <!-- ... -->
    </tbody>
  </table>
</figure>
```

### 4.1.3 — Status Messages — Level AA

Live P&L updates and trade notifications must use ARIA live regions:

```html
<!-- P&L card that updates every 5s -->
<div aria-live="polite" aria-atomic="true">
  <span>Today P&L: up $142.50, up 1.42 percent</span>
</div>

<!-- Trade notification (immediate) -->
<div aria-live="assertive" aria-atomic="true">
  <!-- Only used for critical alerts like strategy stopped, bot error -->
</div>

<!-- New trade opened (non-urgent) -->
<div aria-live="polite">
  Trade opened: Buy XAUUSD at 2341.5
</div>
```

### 2.5.3 — Label in Name — Level A

Button visible text must match or contain the accessible name:

- Button text "Stop All Trading" → accessible name contains "Stop All Trading" ✓
- Icon-only buttons must have aria-label matching the action ← no icon-only buttons for critical actions
- Toggle labels must match their current state: aria-checked="true/false" for toggles

---

## Forms and Inputs

### 1.3.5 — Identify Input Purpose — Level AA

All form inputs must have autocomplete attributes where applicable:

```html
<input type="email" autocomplete="email" />
<input type="password" autocomplete="current-password" />
<input type="password" autocomplete="new-password" /> <!-- new password field -->
<input type="tel" autocomplete="off" />  <!-- MT5 login ID — no autocomplete -->
```

### 3.3.1 — Error Identification — Level A

Every error must:
1. Be described in text (not only red border)
2. Identify the field that has the error
3. Be programmatically associated with the field (aria-describedby)

```html
<label for="email">Email address</label>
<input id="email" aria-describedby="email-error" aria-invalid="true" />
<span id="email-error" role="alert">
  ✕ An account with this email already exists. Sign in instead.
</span>
```

### 3.3.2 — Labels or Instructions — Level A

- All inputs have a visible label
- Password requirements shown as inline checklist, not tooltip-only
- MT5 server field: helper text "Find in MT5: File > Login > Server" visible, not icon-only tooltip
- No placeholder-as-label pattern

---

## Motion and Interaction

### 2.3.3 — Animation from Interactions — Level AAA (target)

- Equity curve animation on load: respect `prefers-reduced-motion` media query — show static chart immediately
- Loading spinners: can remain (essential state feedback), but avoid complex animations
- Transition durations: max 200ms for state changes, 300ms for page transitions

```css
@media (prefers-reduced-motion: reduce) {
  .equity-curve-animation { animation: none; }
  .page-transition { transition: none; }
}
```

---

## Audit Process

### Pre-launch requirements

1. Automated scan: axe DevTools or Lighthouse accessibility audit — zero critical/serious issues
2. Manual keyboard test: navigate entire critical path (sign-up → connect broker → run backtest → activate live → emergency stop) using only keyboard
3. Screen reader test: VoiceOver (macOS) + NVDA (Windows) on all 10 screens
4. Color contrast: all combinations checked in Figma with Able plugin or Contrast plugin
5. Colorblind simulation: Figma Stark plugin — simulate deuteranopia and protanopia on dashboard and backtest results
6. Zoom test: UI functional at 200% zoom (browser zoom) — no horizontal scrolling on desktop

### Known risk areas requiring extra attention

| Screen | Risk | Required mitigation |
|---|---|---|
| Dashboard | P&L updates via aria-live must not interrupt screen reader every 5s | Use aria-live="polite" not "assertive"; consider user-controlled refresh rate |
| Backtest monthly heatmap | Color + value — must test colorblind simulation specifically | Percentage text inside every cell; accessible summary above table |
| Emergency stop modal | Focus management on open/close | Programmatically move focus to Cancel button on modal open; return focus to trigger on close |
| Chart | Keyboard navigation of data points | Implement full keyboard chart navigation with screen reader announcement |
| Strategy status badges | Shape + text + color | All three must be present; test in Windows High Contrast mode |
| API key reveal | One-time display — user must act | aria-live announcement; explicit "Copy" button with visual and audio feedback |
