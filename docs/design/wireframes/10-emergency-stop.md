# Wireframe 10 — Emergency Stop (Kill Switch Modal)
**Author:** Iris Kaguya
**Date:** 2026-06-14
**Fidelity:** Mid-fi ASCII

---

## Trigger — Header Button (all pages)

```
┌─────────────────────────────────────────────────────────────────────┐
│ [Logo]  Dashboard  Strategies  Backtest  Billing  Settings          │
│                                               [🔔] [Avatar]         │
│                          [ ■ STOP ALL TRADING ] ← persistent, red  │
└─────────────────────────────────────────────────────────────────────┘

Button spec:
- Background: #DC2626 (loss red)
- Text: "■ STOP ALL TRADING"
- Weight: semibold, all caps
- Position: right side of header, always visible
- Never hidden in dropdown or mobile hamburger
- Mobile: full-width banner below header
```

---

## Emergency Stop Modal

```
┌─────────────────────────────────────────────────────────────────────┐
│  (page content dimmed behind modal)                                 │
│                                                                     │
│              ┌───────────────────────────────────┐                 │
│              │                                   │                 │
│              │  ■ STOP ALL TRADING?              │                 │
│              │                                   │                 │
│              │  This will immediately stop all   │                 │
│              │  active strategies from placing   │                 │
│              │  new trades.                      │                 │
│              │                                   │                 │
│              │  Active now:                      │                 │
│              │  · London Breakout  ● LIVE        │                 │
│              │  · EMA + ADX        ● LIVE        │                 │
│              │  · SMC Concepts     ◑ PAPER       │                 │
│              │                                   │                 │
│              │  ┌───────────────────────────┐   │                 │
│              │  │ ⚠ Open positions will NOT │   │                 │
│              │  │   be closed automatically.│   │                 │
│              │  │   You must close them     │   │                 │
│              │  │   manually in MT5.        │   │                 │
│              │  └───────────────────────────┘   │                 │
│              │                                   │                 │
│              │  [    Cancel — Keep Running    ]  │                 │
│              │  (default focus — safe default)   │                 │
│              │                                   │                 │
│              │  [  ■ Confirm — Stop All Now  ]   │                 │
│              │  (danger style — requires Tab)    │                 │
│              │                                   │                 │
│              └───────────────────────────────────┘                 │
└─────────────────────────────────────────────────────────────────────┘

Modal design:
- Background: #7F1D1D (dark red) or very dark overlay
- Header text: white, large (24px), bold
- "Cancel" button: primary green / neutral — default focus (Enter = Cancel)
- "Confirm Stop" button: danger red, requires Tab to reach or explicit click
- Pressing Escape = Cancel (same as clicking Cancel)
- Modal cannot be closed by clicking overlay — must choose an action
- No timeout or auto-confirm
- Trap focus inside modal — keyboard users cannot Tab out
```

---

## Processing State (after Confirm clicked)

```
┌───────────────────────────────────┐
│                                   │
│  ■ Stopping all strategies...     │
│                                   │
│  London Breakout     ✓ Stopped    │
│  EMA + ADX           ⟳ Stopping  │
│  SMC Concepts        ○ Queued    │
│                                   │
│  [████████████░░░░░] 67%          │
│                                   │
│  Please wait — do not close       │
│  this window.                     │
│                                   │
└───────────────────────────────────┘
```

---

## Success State

```
┌───────────────────────────────────┐
│                                   │
│  ✓ All trading stopped            │
│                                   │
│  London Breakout     ✓ Stopped    │
│  EMA + ADX           ✓ Stopped    │
│  SMC Concepts        ✓ Stopped    │
│                                   │
│  Stopped at: 14:32:08 +07         │
│  A confirmation has been emailed  │
│  to john@example.com              │
│                                   │
│  ⚠ Open positions (if any) must  │
│    be closed manually in MT5.     │
│                                   │
│  [  OK — Go to Dashboard  ]       │
│                                   │
└───────────────────────────────────┘
```

---

## Partial Failure State

```
┌───────────────────────────────────┐
│                                   │
│  ⚠ Partial stop — action needed  │
│                                   │
│  London Breakout     ✓ Stopped    │
│  EMA + ADX           ✕ Failed     │
│  SMC Concepts        ✓ Stopped    │
│                                   │
│  EMA + ADX could not be stopped   │
│  (connection timeout).            │
│                                   │
│  [Retry — Stop EMA + ADX]         │
│  [Contact Support]                │
│  [OK — Continue]                  │
│                                   │
│  ⚠ EMA + ADX may still be        │
│    placing trades. Monitor MT5    │
│    directly until resolved.       │
│                                   │
└───────────────────────────────────┘
```

---

## Mobile (375px) — Kill switch layout

```
┌─────────────────────────────┐
│ [Logo]              [🔔][=] │
│ [■  STOP ALL TRADING      ] │  ← full-width, always below header
└─────────────────────────────┘

Modal (bottom sheet on mobile):
┌─────────────────────────────┐
│                             │
│ ■ STOP ALL TRADING?        │
│                             │
│ Stops all strategies from  │
│ placing new trades.         │
│                             │
│ Active:                     │
│ · London Breakout ●LIVE    │
│ · EMA + ADX       ●LIVE    │
│                             │
│ ⚠ Open positions will NOT  │
│   be closed automatically. │
│   Close them in MT5.       │
│                             │
│ [  Cancel — Keep Running ] │
│ [■ Confirm — Stop All Now] │
│                             │
└─────────────────────────────┘
```

---

## Single Strategy Stop (from Strategy Detail page)

```
Inline confirm, not full modal:

┌──────────────────────────────────────────────┐
│ Stop London Breakout?                        │
│                                              │
│ This strategy will stop accepting new        │
│ signals. Open positions will remain open     │
│ and must be managed in MT5.                  │
│                                              │
│ [Keep Running]  [Stop This Strategy]         │
└──────────────────────────────────────────────┘
```

---

## Keyboard navigation spec

```
Tab order inside modal:
1. Cancel button (default focus, Enter = safe action)
2. Confirm Stop button (requires explicit Tab or click)

Key behaviors:
Escape        → Cancel (identical to clicking Cancel)
Enter         → Activates currently focused button
Tab           → Move to next button (Cancel → Confirm Stop)
Shift+Tab     → Move to previous button

Screen reader announcement:
- When modal opens: "Dialog: Stop all trading? Press Tab to navigate."
- Cancel button: "Button: Cancel, Keep running"
- Confirm button: "Button: Confirm, Stop all trading now. This action cannot be undone."
- Success state: "Status: All trading stopped at 14:32:08. Email confirmation sent."
```

---

## Design rationale

This screen is the most critical UI in the product. Design decisions:

1. Always visible — user who is panicking cannot hunt for the kill switch.
2. Single confirmation only — two confirmations add delay in a panic situation. One is enough.
3. Cancel is default focus — the "safe" action is always the keyboard default. A user who accidentally triggers the modal and hits Enter immediately gets Cancel, not Stop.
4. Open positions disclosure is explicit and repeated — not burying this causes the most user confusion and support tickets.
5. Partial failure is a first-class state — the system must tell the user if a strategy failed to stop, not silently succeed.
6. Email confirmation — logged event gives the user a receipt and the system an audit trail.
