# User Flows — Trading Bot SaaS
**Author:** Iris Kaguya (UX/UI Designer)
**Date:** 2026-06-14
**Project:** Forex/Crypto Trading Bot Platform

Notation:
- Rectangle = screen / page
- Diamond = decision
- Parallelogram = system action
- Bold border = critical / irreversible action

---

## F1: Sign-up → Email Verify → Trial Activation

**Primary persona:** P1 Warit (Beginner)
**Goal:** Get from zero to active Free Trial with bot access in under 5 minutes.

```mermaid
flowchart TD
    A([Landing Page]) --> B[Click Get Started Free]
    B --> C[/Sign-up Form\nEmail + Password + Confirm/]
    C --> D{Valid input?}
    D -- No --> C
    D -- Yes --> E[\System: Create account\nSend verify email/]
    E --> F[/Check Your Email Screen\nResend link option/]
    F --> G{User clicks verify link}
    G -- Link expired --> H[/Resend verification page/]
    H --> E
    G -- Valid --> I[\System: Mark email verified\nActivate Free Trial 14 days/]
    I --> J[/Welcome Screen\nTrial countdown shown: 14 days remaining/]
    J --> K[/Onboarding Step 1: Connect Broker/]
    K --> L([Dashboard])

    style E fill:#1E293B,color:#94A3B8
    style I fill:#1E293B,color:#94A3B8
```

**Edge cases:**
- Email already registered → show "Sign in instead" inline error
- Verify link clicked after 24h → explain expiry, offer one-click resend
- User closes tab after registration → next visit shows "verify your email" banner until confirmed
- Mobile: verify link opens app deeplink, not broken browser redirect

---

## F2: Connect Exness MT5 → Broker Credential Form → Test Connection

**Primary persona:** P1 Warit, P2 Priya
**Goal:** Securely connect MT5 account so bot can execute trades.

```mermaid
flowchart TD
    A([Dashboard]) --> B[Click Connect Broker]
    B --> C[/Broker Selection\nExness MT5 highlighted — only supported/]
    C --> D[/MT5 Credential Form\nServer / Login / Password\n+ Security notice: encrypted at rest/]
    D --> E{All fields filled?}
    E -- No --> D
    E -- Yes --> F[Click Test Connection]
    F --> G[\System: Validate MT5 credentials\nTest read-only account info/]
    G --> H{Connection result}
    H -- Success --> I[/Success state\nAccount name, balance, server confirmed/]
    I --> J[Click Save and Continue]
    J --> K[\System: Store encrypted credentials\nLink to user account/]
    K --> L([Dashboard — Broker Connected badge])
    H -- Fail: wrong credentials --> M[/Inline error: Check your Login ID and password\nDo not show which field is wrong — security/]
    M --> D
    H -- Fail: server unreachable --> N[/Inline error: Cannot reach server\nCheck server name or try again/]
    N --> D
    H -- Timeout --> O[/Timeout state\nRetry button + status indicator/]
    O --> F

    style G fill:#1E293B,color:#94A3B8
    style K fill:#1E293B,color:#94A3B8
```

**Edge cases:**
- User pastes password with trailing space → trim silently but note in tooltip "spaces removed"
- MT5 server list: provide dropdown with known Exness servers as autocomplete
- Connection success but read-only (wrong account type) → warn clearly before saving
- Credentials update: require password re-entry to modify saved broker credentials

---

## F3: Run Backtest → Pick Strategy → Set Params → See Equity Curve

**Primary persona:** P2 Priya, P3 Krit
**Goal:** Validate strategy performance on historical data before going live.

```mermaid
flowchart TD
    A([Strategies List]) --> B[Select Strategy Card]
    B --> C[/Strategy Detail Page/]
    C --> D[Click Run Backtest]
    D --> E[/Backtest Config Panel\nDate range picker / Symbol / Timeframe\nLot size / SL / TP / Slippage / Spread/]
    E --> F{Config valid?}
    F -- No: date range too short --> G[/Inline warning: min 30 days required/]
    G --> E
    F -- Yes --> H[Click Run]
    H --> I[\System: Queue backtest job\nShow loading state with progress/]
    I --> J{Job complete?}
    J -- Running --> K[/Progress bar: Calculating... X% complete/]
    K --> J
    J -- Error --> L[/Error state\nReason + retry button/]
    J -- Success --> M[/Backtest Results Page\nEquity curve / Drawdown / Metric cards\nMonthly heatmap / Trade list/]
    M --> N{User action}
    N -- Adjust params --> E
    N -- Save result --> O[\System: Save backtest snapshot/]
    N -- Go live --> P[/Activate Live Trading flow — see F5/]

    style I fill:#1E293B,color:#94A3B8
    style O fill:#1E293B,color:#94A3B8
```

**Edge cases:**
- Backtest on insufficient data (e.g., strategy needs 200 candles, range gives 50) → block with explanation
- Long-running backtest (>60s) → show progress bar, allow leaving page (notified when done)
- Results with zero trades → explain why (strategy conditions never triggered) with parameter suggestions
- P3 Krit: export button always visible — CSV/JSON of full trade log

---

## F4: Subscribe to Plan → Stripe Checkout → Activate

**Primary persona:** P1 Warit (upgrade), P2 Priya (upgrade/change)
**Goal:** Upgrade from Free Trial to paid plan with minimal friction.

```mermaid
flowchart TD
    A([Billing Page / Upgrade CTA]) --> B[/Plan Comparison\nFree Trial / Pro Monthly / Lifetime\n— features side by side/]
    B --> C[Click Choose Plan]
    C --> D[/Order Summary\nPlan name, price, billing cycle, VAT note/]
    D --> E[Click Proceed to Payment]
    E --> F[\Redirect to Stripe Checkout\nHosted by Stripe — PCI compliant/]
    F --> G{Payment result}
    G -- Success --> H[\System: Activate plan\nSend confirmation email\nUpdate user tier/]
    H --> I[/Success Screen\nYour Pro plan is active\nReceipt emailed/]
    I --> J([Dashboard — plan badge updated])
    G -- Card declined --> K[/Stripe error: Card declined\nTry different card/]
    K --> F
    G -- User cancelled --> L[/Billing page — plan unchanged\nNo charge made/]
    G -- 3D Secure required --> M[/Stripe 3DS flow/]
    M --> G

    style F fill:#1E293B,color:#94A3B8
    style H fill:#1E293B,color:#94A3B8
```

**Edge cases:**
- Trial expiry mid-session → show non-blocking banner "Trial ends in X days — upgrade to keep access"
- Lifetime plan: one-time charge, no auto-renew — copy must be explicit
- VAT/tax for Thai users: Stripe Tax handles calculation — display before confirm
- Downgrade: handled by cancellation at end of billing period, not immediate

---

## F5: Activate Live Trading → Confirm Risk Warning → Bot Running

**Primary persona:** P1 Warit, P2 Priya
**Goal:** Start the bot on a live account after understanding the risks.

```mermaid
flowchart TD
    A([Strategy Detail Page]) --> B{Broker connected?}
    B -- No --> C[/Prompt: Connect broker first\nLink to F2 flow/]
    B -- Yes --> D[Click Activate Live Trading]
    D --> E[/Risk Confirmation Modal\nExplicit risk warning — 3 statements\nUser must check each checkbox\nCannot dismiss without reading/]
    E --> F{All 3 boxes checked?}
    F -- No --> E
    F -- Yes --> G[Click I Understand — Start Bot]
    G --> H[\System: Enable live trading mode\nActivate strategy on MT5/]
    H --> I{Activation successful?}
    I -- Fail --> J[/Error: Could not start bot\nCheck broker connection / account balance/]
    J --> B
    I -- Success --> K[/Strategy card updates:\nStatus = LIVE — green indicator\nFirst ping: Connected/]
    K --> L([Dashboard — strategy listed as LIVE])

    style H fill:#1E293B,color:#94A3B8
    style E fill:#7F1D1D,color:#FCA5A5
    style G fill:#7F1D1D,color:#FCA5A5
```

**Risk warning modal content (non-negotiable):**
1. "Automated trading involves risk of financial loss. Past performance does not guarantee future results."
2. "This bot will place real trades on your Exness account using real money."
3. "You are responsible for monitoring your account and setting appropriate position sizes."

**Edge cases:**
- Account balance too low for minimum lot → warn before activation, not after
- Strategy already running on another account → prevent duplicate activation, explain why
- Trial user trying to activate live → gate with upgrade prompt
- MT5 account in read-only mode → detect and block with clear error before showing risk modal

---

## F6: Manual Stop / Emergency Kill Switch

**Primary persona:** P1 Warit (panic), P2 Priya (planned), P3 Krit (programmatic)
**Goal:** Stop all bot activity immediately. Zero ambiguity. Zero delay.

```mermaid
flowchart TD
    A([Any Page — Emergency Stop always accessible]) --> B[/Emergency Stop button\n— always visible in header/]
    B --> C[/Confirmation Modal\nRed background\nLarge text: STOP ALL TRADING?\nThis will close no open positions — only stop new trades/]
    C --> D{User action}
    D -- Cancel --> E([Return to current page — no action taken])
    D -- Confirm Stop --> F[\System: Send kill signal to all active strategies\nLog event with timestamp/]
    F --> G{All strategies stopped?}
    G -- Partial failure --> H[/Warning: X strategies stopped, Y failed\nRetry failed + contact support/]
    G -- All stopped --> I[/Success state: All trading stopped\nBot status = STOPPED on all cards\nEmail confirmation sent/]
    I --> J([Dashboard — all strategies show STOPPED])

    subgraph SingleStrategy [Stop Single Strategy]
        K([Strategy Detail Page]) --> L[Click Stop Strategy]
        L --> M[/Inline confirm: Stop this strategy?\nOpen positions will not be closed/]
        M --> N{Confirmed?}
        N -- Yes --> O[\System: Stop single strategy/]
        O --> P([Strategy status = STOPPED])
    end

    style B fill:#7F1D1D,color:#FECACA
    style C fill:#7F1D1D,color:#FECACA
    style F fill:#1E293B,color:#94A3B8
```

**Critical design decisions:**
- Emergency stop is in the persistent header — always visible, never hidden behind a menu
- Confirmation modal is the ONLY gate — no second confirmation, no timeout, no password
- Stop does NOT close open positions by default — this is disclosed in the modal explicitly
- System logs the stop event with user ID, timestamp, and all stopped strategy IDs
- Email confirmation of stop event sent immediately
- Keyboard shortcut: modal is focusable, Enter = Cancel (safe default), Tab to Confirm then Enter

**Edge cases:**
- Network loss during kill → system must have last-known-state; resync on reconnect shows correct STOPPED status
- User refreshes immediately after stop → status persists from server, not local state
- Stop while backtest running → backtest cancels, data is discarded — explain in modal
