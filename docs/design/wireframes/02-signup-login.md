# Wireframe 02 — Sign-up / Login (Auth)
**Author:** Iris Kaguya
**Date:** 2026-06-14
**Fidelity:** Mid-fi ASCII

---

## Sign-up Screen (Desktop — centered card, 480px max-width)

```
┌─────────────────────────────────────────────────────────────────────┐
│                           [Logo]                                    │
│                                                                     │
│          ┌───────────────────────────────────────┐                 │
│          │ Create your account                   │                 │
│          │ Start your 14-day free trial           │                 │
│          │ No credit card required.               │                 │
│          │                                       │                 │
│          │ Email address                         │                 │
│          │ ┌─────────────────────────────────┐  │                 │
│          │ │ you@example.com                 │  │                 │
│          │ └─────────────────────────────────┘  │                 │
│          │                                       │                 │
│          │ Password                              │                 │
│          │ ┌─────────────────────────────────┐  │                 │
│          │ │ ••••••••••••             [show] │  │                 │
│          │ └─────────────────────────────────┘  │                 │
│          │ ○ At least 8 characters               │                 │
│          │ ○ One uppercase letter                │                 │
│          │ ○ One number or symbol                │                 │
│          │ (inline checklist updates on type)    │                 │
│          │                                       │                 │
│          │ Confirm password                      │                 │
│          │ ┌─────────────────────────────────┐  │                 │
│          │ │ ••••••••••••             [show] │  │                 │
│          │ └─────────────────────────────────┘  │                 │
│          │                                       │                 │
│          │ [ ] I have read and agree to the      │                 │
│          │     Terms of Service and              │                 │
│          │     Risk Disclosure                   │                 │
│          │                                       │                 │
│          │ [     Create Account     ]            │                 │
│          │  (disabled until form valid)          │                 │
│          │                                       │                 │
│          │ ─────────── or ───────────            │                 │
│          │                                       │                 │
│          │ [G  Continue with Google]             │                 │
│          │                                       │                 │
│          │ Already have an account? Sign in      │                 │
│          └───────────────────────────────────────┘                 │
└─────────────────────────────────────────────────────────────────────┘
```

**Error states:**
```
Email already registered:
│ Email address                          │
│ ┌────────────────────────────────┐    │
│ │ you@example.com                │ ✕  │  ← red border
│ └────────────────────────────────┘    │
│ ✕ An account with this email exists.  │
│   Sign in instead?                    │

Password mismatch:
│ ✕ Passwords do not match              │
```

---

## Email Verification Pending Screen

```
┌─────────────────────────────────────────────────────────────────────┐
│                           [Logo]                                    │
│                                                                     │
│          ┌───────────────────────────────────────┐                 │
│          │                                       │                 │
│          │        [envelope illustration]        │                 │
│          │                                       │                 │
│          │  Check your email                     │                 │
│          │                                       │                 │
│          │  We sent a verification link to       │                 │
│          │  you@example.com                      │                 │
│          │                                       │                 │
│          │  Click the link to activate your      │                 │
│          │  free trial. Check spam if you        │                 │
│          │  don't see it.                        │                 │
│          │                                       │                 │
│          │  [Resend verification email]          │                 │
│          │  (disabled for 60s after send)        │                 │
│          │  Resend available in: 45s             │                 │
│          │                                       │                 │
│          │  Wrong email? Start over              │                 │
│          └───────────────────────────────────────┘                 │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Login Screen

```
┌─────────────────────────────────────────────────────────────────────┐
│                           [Logo]                                    │
│                                                                     │
│          ┌───────────────────────────────────────┐                 │
│          │ Sign in to your account               │                 │
│          │                                       │                 │
│          │ Email address                         │                 │
│          │ ┌─────────────────────────────────┐  │                 │
│          │ │ you@example.com                 │  │                 │
│          │ └─────────────────────────────────┘  │                 │
│          │                                       │                 │
│          │ Password                              │                 │
│          │ ┌─────────────────────────────────┐  │                 │
│          │ │ ••••••••••••             [show] │  │                 │
│          │ └─────────────────────────────────┘  │                 │
│          │                              Forgot password?            │
│          │                                       │                 │
│          │ [        Sign In          ]            │                 │
│          │                                       │                 │
│          │ ─────────── or ───────────            │                 │
│          │ [G  Continue with Google]             │                 │
│          │                                       │                 │
│          │ Don't have an account? Sign up free   │                 │
│          └───────────────────────────────────────┘                 │
└─────────────────────────────────────────────────────────────────────┘
```

**Failed login error:**
```
│ ✕ Incorrect email or password.               │
│   (do not specify which field is wrong)      │
│   5 failed attempts will lock your account   │
│   for 15 minutes.                            │
```

---

## 2FA Challenge Screen (if enabled)

```
┌───────────────────────────────────────┐
│ Two-factor authentication             │
│                                       │
│ Enter the 6-digit code from your      │
│ authenticator app.                    │
│                                       │
│  ┌──┐ ┌──┐ ┌──┐  ┌──┐ ┌──┐ ┌──┐    │
│  │  │ │  │ │  │  │  │ │  │ │  │    │
│  └──┘ └──┘ └──┘  └──┘ └──┘ └──┘    │
│  (auto-advance on 6th digit)         │
│                                       │
│ Use a backup code instead             │
│ [Cancel — sign in as different user]  │
└───────────────────────────────────────┘
```

---

## Design notes

- No CAPTCHA on signup — use honeypot + rate limiting server-side (CAPTCHA adds friction for legitimate users)
- Password show/hide toggle uses eye icon + "show"/"hide" text label (not icon-only — accessibility)
- Password requirements show as inline checklist, not tooltip — P1 Warit needs clear guidance
- "Risk Disclosure" link in signup terms opens in new tab, does not navigate away from form
- Verify link: 24-hour expiry with clear explanation and one-click resend
- Login: lockout warning shown BEFORE 5th attempt, not after
- All form inputs have visible focus ring — no outline:none override
