# Wireframe 07 — Broker Connection (Exness MT5)
**Author:** Iris Kaguya
**Date:** 2026-06-14
**Fidelity:** Mid-fi ASCII

---

## Desktop — Connection Form

```
┌─────────────────────────────────────────────────────────────────────┐
│ [Header with Emergency Stop]                                        │
└─────────────────────────────────────────────────────────────────────┘
┌──────┐  ┌─────────────────────────────────────────────────────────┐
│ NAV  │  │ Settings > Broker Connection                             │
│      │  │                                                          │
│      │  │  ┌──────────────────────────────────────────────────┐   │
│      │  │  │                                                   │   │
│      │  │  │  [Exness logo]  Connect Exness MT5               │   │
│      │  │  │                                                   │   │
│      │  │  │  Your broker credentials are encrypted using     │   │
│      │  │  │  AES-256 and stored securely. We never share     │   │
│      │  │  │  your credentials with third parties.            │   │
│      │  │  │  [Learn how we protect your data →]              │   │
│      │  │  │                                                   │   │
│      │  │  │  ─────────────────────────────────────────────   │   │
│      │  │  │                                                   │   │
│      │  │  │  MT5 Server                                       │   │
│      │  │  │  ┌──────────────────────────────────────────┐   │   │
│      │  │  │  │ Exness-MT5Real8                      ▾   │   │   │
│      │  │  │  └──────────────────────────────────────────┘   │   │
│      │  │  │  Common Exness servers:                          │   │
│      │  │  │  · Exness-MT5Real  · Exness-MT5Real2            │   │
│      │  │  │  · Exness-MT5Real8  · Exness-MT5Trial           │   │
│      │  │  │  (Find yours in MT5: File > Login > Server)     │   │
│      │  │  │                                                   │   │
│      │  │  │  MT5 Login (Account Number)                      │   │
│      │  │  │  ┌──────────────────────────────────────────┐   │   │
│      │  │  │  │ 12345678                                  │   │   │
│      │  │  │  └──────────────────────────────────────────┘   │   │
│      │  │  │  This is your numeric account ID from Exness.   │   │
│      │  │  │  Not your email address.                         │   │
│      │  │  │                                                   │   │
│      │  │  │  MT5 Investor Password                           │   │
│      │  │  │  ┌──────────────────────────────────────────┐   │   │
│      │  │  │  │ ••••••••••••••••••••         [show]      │   │   │
│      │  │  │  └──────────────────────────────────────────┘   │   │
│      │  │  │                                                   │   │
│      │  │  │  ┌─────────────────────────────────────────┐    │   │
│      │  │  │  │ [ℹ] Use Investor Password, not Master   │    │   │
│      │  │  │  │                                         │    │   │
│      │  │  │  │ Investor Password = read + trade only   │    │   │
│      │  │  │  │ Master Password = full account access   │    │   │
│      │  │  │  │                                         │    │   │
│      │  │  │  │ We recommend using Investor Password for│    │   │
│      │  │  │  │ maximum security. Find it in:           │    │   │
│      │  │  │  │ Exness Personal Area > Accounts >       │    │   │
│      │  │  │  │ Manage > Passwords                      │    │   │
│      │  │  │  │                                         │    │   │
│      │  │  │  │ [View Exness guide →] (opens new tab)  │    │   │
│      │  │  │  └─────────────────────────────────────────┘    │   │
│      │  │  │                                                   │   │
│      │  │  │  [  Test Connection  ]                           │   │
│      │  │  │                                                   │   │
│      │  │  └──────────────────────────────────────────────────┘   │
└──────┘  └─────────────────────────────────────────────────────────┘
```

---

## Connection States

```
IDLE (before test):
[  Test Connection  ]
No status shown.

TESTING:
[  Testing...  ⟳  ]
Connecting to Exness-MT5Real8...

SUCCESS:
┌──────────────────────────────────────────────┐
│ ✓ Connected successfully                     │
│                                              │
│ Account: John Smith                          │
│ Balance: $10,245.30 USD                      │
│ Account type: Real                           │
│ Leverage: 1:500                              │
│ Server: Exness-MT5Real8                      │
└──────────────────────────────────────────────┘
[  Save and Continue  ]  [Test again]

WRONG CREDENTIALS:
✕ Could not connect. Check your account number
  and password and try again.
  (Do not specify which field is wrong)

SERVER UNREACHABLE:
✕ Cannot reach Exness-MT5Real8.
  Check the server name or try again.
  Common servers: [Exness-MT5Real] [Exness-MT5Real2]

TIMEOUT:
✕ Connection timed out.
  [Retry]  This may be a temporary issue.

READ-ONLY ACCOUNT DETECTED:
⚠ Your account is set to read-only.
  The bot cannot place trades.
  Check your MT5 account settings or contact Exness.
```

---

## Connected State (already saved credentials)

```
┌─────────────────────────────────────────────────────────────────────┐
│ Settings > Broker Connection                                        │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ [Exness logo]  MT5 Account Connected                  ✓      │  │
│  │                                                              │  │
│  │ Account:  John Smith                                         │  │
│  │ Login ID: ****5678  (masked)                                 │  │
│  │ Server:   Exness-MT5Real8                                    │  │
│  │ Balance:  $10,245.30  (last sync: 14:32:01)                 │  │
│  │                                                              │  │
│  │ Status:   ● Live connection active                           │  │
│  │                                                              │  │
│  │ [Sync Now]  [Update Credentials]  [Disconnect Account]       │  │
│  │                                                              │  │
│  │ To update credentials, you must re-enter your current        │  │
│  │ password before setting a new one.                           │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Mobile (375px)

```
┌─────────────────────────────┐
│ ← Broker Connection         │
│                              │
│ [Exness logo]               │
│ Connect Exness MT5          │
│                              │
│ Your credentials are        │
│ encrypted with AES-256.     │
│ We never share them.        │
│                              │
│ MT5 Server                  │
│ [Exness-MT5Real8      ▾]    │
│                              │
│ Common servers:             │
│ Exness-MT5Real              │
│ Exness-MT5Real2             │
│ Exness-MT5Real8             │
│                              │
│ MT5 Login (Account ID)      │
│ [12345678             ]     │
│ Not your email address.     │
│                              │
│ MT5 Investor Password       │
│ [••••••••••••   [show]]     │
│                              │
│ ┌───────────────────────┐   │
│ │ ℹ Use Investor        │   │
│ │ Password — read+trade │   │
│ │ only. Not Master.     │   │
│ │ [Exness guide →]      │   │
│ └───────────────────────┘   │
│                              │
│ [   Test Connection   ]     │
└─────────────────────────────┘
```

---

## Design notes

- Security copy appears FIRST, above the form — not buried at the bottom
- Login ID helper text: "Not your email address" — P1 Warit confusion point from research
- Investor Password guidance is inline, not hidden in FAQ — reduces support tickets
- Error messages never indicate which specific field failed — security best practice (credential enumeration)
- Server field is a searchable dropdown with known Exness servers + free text for custom
- "Disconnect Account" requires a separate confirmation modal — irreversible action
- Balance masked after save — never re-display password, only allow update/replace
- Connection test is mandatory before save — cannot save untested credentials
