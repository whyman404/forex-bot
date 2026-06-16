# Design System — Trading Bot SaaS
**Author:** Iris Kaguya (UX/UI Designer)
**Date:** 2026-06-14
**Project:** Forex/Crypto Trading Bot Platform
**Stack:** Next.js 15 + Tailwind CSS + shadcn/ui

---

## Decision: Dark Mode Default

Trading users look at screens for long sessions, often at night or in low-light trading rooms. Dark mode reduces eye strain during extended monitoring sessions. All tokens are dark-first; light mode is a future consideration.

---

## Decision: Primary Brand Color — Deep Emerald

**Chosen: Deep Emerald (#065F46 base, #059669 interactive)**

Rationale:
- Navy (#1E3A5F) is the default "fintech blue" — used by Binance, Bybit, Interactive Brokers. Emerald differentiates the brand.
- Emerald has semantic resonance with trading (growth, markets, currency) without being confused with profit green.
- Profit green (#16A34A) and brand emerald must be distinct — they live in different saturation bands (brand = dark muted, profit = bright vivid). Deep emerald achieves this separation cleanly.
- On dark backgrounds, dark emerald reads as "trusted, professional" while avoiding the coldness of navy.

---

## Color Tokens

```
── BRAND ──────────────────────────────────────────────────────────────
brand-950    #022C22    Darkest brand — deep backgrounds, sidebars
brand-900    #064E3B    Brand surface — card backgrounds
brand-800    #065F46    Brand primary — buttons, active nav items
brand-600    #059669    Brand interactive — hover, focus rings
brand-500    #10B981    Brand accent — highlights, badges
brand-400    #34D399    Brand light — light text on dark bg

── SEMANTIC — FINANCIAL ──────────────────────────────────────────────
profit       #16A34A    Trade profit, positive P&L (always with arrow ▲)
profit-light #BBF7D0    Profit on dark: soft green text
profit-bg    #14532D    Profit cell background (heatmap, table)

loss         #DC2626    Trade loss, negative P&L (always with arrow ▼)
loss-light   #FECACA    Loss on dark: soft red text
loss-bg      #7F1D1D    Loss cell background, danger zones

warning      #D97706    Drawdown alert, high-risk parameter warning
warning-bg   #451A03    Warning background

── NEUTRAL (dark mode base) ──────────────────────────────────────────
gray-950     #030712    Page background
gray-900     #111827    Card/panel background
gray-800     #1F2937    Elevated surface
gray-700     #374151    Border, divider
gray-600     #4B5563    Disabled text, placeholder
gray-500     #6B7280    Secondary text, labels
gray-400     #9CA3AF    Muted text
gray-300     #D1D5DB    Primary body text
gray-100     #F3F4F6    High-emphasis text
white        #FFFFFF    Maximum emphasis, active labels

── EMERGENCY / DANGER ────────────────────────────────────────────────
danger-900   #450A0A    Emergency stop modal background
danger-700   #B91C1C    Emergency button hover
danger-600   #DC2626    Emergency button default (= loss red)
danger-400   #F87171    Emergency button text/icon on dark

── STATUS INDICATORS ─────────────────────────────────────────────────
status-live  #16A34A    ● LIVE (same as profit — intentional: live = growing)
status-paper #D97706    ◑ PAPER (amber)
status-off   #6B7280    ○ OFF (gray-500)
status-error #DC2626    ✕ Error (same as loss)

── CHART LINES ──────────────────────────────────────────────────────
chart-equity    #059669    Equity curve line (brand-600)
chart-drawdown  #DC2626    Drawdown line (loss)
chart-zero      #4B5563    Zero reference line (gray-600)
chart-grid      #1F2937    Chart grid lines (gray-800)
chart-tooltip   #111827    Tooltip background (gray-900)
```

---

## Typography

### Font Choice: Inter + JetBrains Mono

**Interface font: Inter** (not Geist)

Rationale: Inter is the de-facto standard for financial/SaaS dashboards (Linear, Vercel, shadcn). It has superior numeric rendering at small sizes and 9 weights with optical sizing. Geist is newer and slightly more opinionated stylistically. For a trust-sensitive financial product, Inter's familiarity is a feature.

**Monospace font: JetBrains Mono** (all numbers on dashboard)

Rationale: JetBrains Mono has tabular figures by default, making columns of prices and P&L align perfectly. It has clear 0/O and l/1 distinction — critical for reading account numbers, trade IDs, and API keys.

```
── SCALE ─────────────────────────────────────────────────────────────
Display     36px / 40px lh  / -0.02em  Inter 700   Page heroes
H1          30px / 36px lh  / -0.02em  Inter 700   Section headers
H2          24px / 32px lh  / -0.015em Inter 600   Card headers
H3          20px / 28px lh  / -0.01em  Inter 600   Sub-headers
H4          16px / 24px lh  / -0.005em Inter 600   Labels, nav items
Body-lg     18px / 28px lh  / 0        Inter 400   Long-form text
Body        16px / 24px lh  / 0        Inter 400   Default body
Body-sm     14px / 20px lh  / 0        Inter 400   Secondary text
Caption     12px / 16px lh  / 0.01em   Inter 400   Timestamps, metadata
Label       12px / 16px lh  / 0.05em   Inter 500   Form labels (uppercase)

── MONOSPACE (financial numbers) ─────────────────────────────────────
Num-xl      24px / 32px lh  JetBrains Mono 500  Balance, large P&L
Num-lg      18px / 24px lh  JetBrains Mono 500  Card metrics
Num-md      16px / 24px lh  JetBrains Mono 400  Table numbers
Num-sm      14px / 20px lh  JetBrains Mono 400  Small chart labels
Num-xs      12px / 16px lh  JetBrains Mono 400  Timestamps, IDs
```

---

## Spacing Scale (4px base)

```
space-1    4px     Tight spacing — icon gap, inline elements
space-2    8px     Small — input padding Y, badge padding
space-3    12px    Base — button padding Y, list item gap
space-4    16px    Default — section padding, card gap
space-6    24px    Medium — card padding, section internal spacing
space-8    32px    Large — between cards, section to section
space-12   48px    XL — page section spacing
space-16   64px    2XL — hero section, page vertical rhythm
```

---

## Border Radius Scale

```
radius-sm   4px    Badges, tags, inline chips
radius-md   8px    Inputs, buttons, small cards
radius-lg   12px   Cards, panels, modals
radius-xl   16px   Large surface cards, dashboard overview panels
radius-2xl  24px   Feature cards, pricing cards
radius-full 9999px Pills, status indicators, toggles
```

---

## Shadow Scale (dark mode)

In dark mode, shadows convey elevation via subtle highlight borders rather than dark drop shadows.

```
shadow-sm    0 1px 2px rgba(0,0,0,0.3),
             inset 0 1px 0 rgba(255,255,255,0.04)
             — Input default, badge

shadow-md    0 4px 6px rgba(0,0,0,0.4),
             inset 0 1px 0 rgba(255,255,255,0.06)
             — Card default

shadow-lg    0 10px 15px rgba(0,0,0,0.5),
             inset 0 1px 0 rgba(255,255,255,0.08)
             — Elevated cards, dropdowns

shadow-xl    0 20px 25px rgba(0,0,0,0.6),
             inset 0 1px 0 rgba(255,255,255,0.1)
             — Modals, overlay panels

shadow-inner inset 0 2px 4px rgba(0,0,0,0.4)
             — Pressed state, inset inputs
```

---

## Component Library

### Button

```
VARIANTS × SIZES matrix:

         sm (32px h)    md (40px h)    lg (48px h)
─────────────────────────────────────────────────────────────
primary  brand-800 bg   brand-800 bg   brand-800 bg
         white text     white text     white text
         hover: 600     hover: 600     hover: 600

secondary gray-800 bg   gray-800 bg   gray-800 bg
          gray-300 text  gray-300 text  gray-300 text
          hover: 700     hover: 700     hover: 700
          border: 700    border: 700    border: 700

danger   loss bg        loss bg        loss bg
          white text     white text     white text
          hover: 700     hover: 700     hover: 700

ghost    transparent    transparent    transparent
          gray-300 text  gray-300 text  gray-300 text
          hover: gray-800 bg

link     transparent    transparent    transparent
          brand-500 text brand-500 text brand-500 text
          underline on hover

ALL VARIANTS — States:
disabled: 50% opacity, cursor: not-allowed, no hover effect
loading:  spinner replaces left icon, text unchanged
focus:    2px ring, brand-500 color, 2px offset — visible on all backgrounds
active:   slightly darker bg (pressed feel)

Padding (px/py):
sm: px-3 py-1.5   md: px-4 py-2.5   lg: px-5 py-3
```

### Input

```
States:
Default   gray-800 bg, gray-700 border, gray-300 text
Focus     gray-800 bg, brand-600 border (2px), gray-100 text
Error     gray-800 bg, loss border (2px), loss-light label
Disabled  gray-900 bg, gray-800 border, gray-600 text
Success   gray-800 bg, profit border, profit-light message

Label: 12px Inter 500 uppercase gray-400, 4px below
Helper: 12px Inter 400 gray-500, 4px below input
Error:  12px Inter 400 loss-light, 4px below, ✕ prefix
```

### Card

```
card-default    gray-900 bg, gray-800 border, shadow-md, radius-lg, p-6
card-elevated   gray-800 bg, gray-700 border, shadow-lg, radius-xl, p-6
card-danger     danger-900 bg, danger-700 border, shadow-lg, radius-xl, p-6
card-metric     gray-900 bg, gray-800 border, shadow-sm, radius-lg, p-4
```

### Status Badge

```
LIVE    profit-bg bg, profit text, ● icon  (shape + text + color)
PAPER   warning-bg bg, warning text, ◑ icon
OFF     gray-800 bg, gray-500 text, ○ icon
ERROR   loss-bg bg, loss text, ✕ icon
```

### Metric Card (dashboard overview)

```
┌──────────────────┐
│ LABEL            │  12px uppercase gray-400
│                  │
│ JJ,JJJ.JJ        │  24px JetBrains Mono 500 gray-100
│ ▲ +JJ.JJ%        │  14px JetBrains Mono profit / loss
│                  │
│ Sub-label        │  12px Inter 400 gray-500
└──────────────────┘
Card: card-metric
```

### Navigation Sidebar

```
Width: 240px (expanded) / 64px (icon-only) / hidden (mobile)
Items:
  Active:   brand-900 bg, brand-400 text, brand-500 left border 2px
  Default:  transparent, gray-400 text
  Hover:    gray-800 bg, gray-300 text
```

### Toggle (strategy mode)

```
OFF → PAPER → LIVE progression
Use labeled toggle, not color-only switch:
[ OFF ] → [ ◑ PAPER ] → [ ● LIVE ]
Clicking advances state with confirmation on → LIVE transition.
```

### Chart (TradingView / lightweight-charts)

```
Background:     gray-950
Grid lines:     chart-grid (#1F2937)
Crosshair:      gray-600, dashed
Equity line:    chart-equity (#059669), 2px
Drawdown line:  chart-drawdown (#DC2626), 2px
Zero line:      chart-zero (#4B5563), 1px dashed
Tooltip bg:     gray-900, radius-md, shadow-xl
Tooltip text:   Num-sm, gray-100
Axes text:      12px JetBrains Mono, gray-500
```

### Modal

```
Overlay:  rgba(0,0,0,0.75)
Panel:    gray-900 bg, shadow-xl, radius-xl
Size:     max-w-md default, max-w-lg for complex forms
Close:    X button top-right, Escape key also closes (except emergency stop modal)
Focus trap: Tab cycles within modal only
```

### Empty State

```
Icon (80px, gray-700) centered
H3 text gray-300 (24px Inter 600)
Body text gray-500 (16px Inter 400)
CTA button below text
```

---

## Spacing Composition Examples

```
Dashboard page:
Page padding:      px-8 py-6 (desktop) / px-4 py-4 (mobile)
Card grid gap:     gap-4 (desktop) / gap-3 (mobile)
Section spacing:   mb-8 between major sections
Header height:     h-16 (64px)

Form fields:
Label → Input gap: gap-1 (4px)
Input → Helper:    gap-1 (4px)
Field → Field:     gap-4 (16px)
Section → Section: gap-8 (32px)
```

---

## Dark Mode Reference Map

```
Page bg         → gray-950 (#030712)
Sidebar bg      → gray-900 (#111827)
Card bg         → gray-900 (#111827)
Card border     → gray-800 (#1F2937)
Elevated card   → gray-800 (#1F2937)
Input bg        → gray-800 (#1F2937)
Input border    → gray-700 (#374151)
Divider         → gray-700 (#374151)
Primary text    → gray-100 (#F3F4F6)
Secondary text  → gray-400 (#9CA3AF)
Placeholder     → gray-600 (#4B5563)
```

---

## Figma Token Naming Convention (for dev handoff)

```
Format: {category}/{role}/{variant}/{state}

Examples:
color/brand/primary/default        → #065F46
color/brand/primary/hover          → #059669
color/semantic/profit/default      → #16A34A
color/semantic/loss/default        → #DC2626
color/neutral/surface/card         → #111827
color/neutral/text/primary         → #F3F4F6

typography/display/size            → 36px
typography/mono/num-lg/size        → 18px

spacing/4                          → 16px
radius/card                        → 12px
shadow/modal                       → (xl shadow value)
```
