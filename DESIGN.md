# Design System: OrcaAppBuilder (incumbent)

## Overview

Dark navy product chrome with **cyan** as the primary accent (Orca family). Mode cards use secondary accents (purple / green / orange / yellow) only as gentle border tints — not competing brand systems.

**Creative north star:** Calm on-ramp. One clear action. No neon SaaS glow theater.

## Surfaces (CSS variables in `index.html`)

| Token | Example | Role |
|-------|---------|------|
| `--bg` | `#080c18` | Page ground |
| `--bg2` | `#0f1526` | Header / sidebar |
| `--bg3` | `#1a2238` | Controls at rest |
| `--card` | `#131929` | Grouped content |
| `--border` | `#1e2d4a` | Hairline structure |
| `--cyan` | `#00d4ff` | Primary accent |
| `--muted` | `#9aa3b5` | Secondary text (AA on dark) |
| `--purple` | `#c4b5fd` | Secondary accent fill (with dark label) |
| `--on-accent` | `#0a0f1e` | Text on filled cyan/purple buttons |
| `--text` | `#e8eaf0` | Primary text |

## Color rules

- **Cyan carries primary actions** (primary buttons, active nav, logo wordmark).
- **Muted text must clear WCAG AA** on `bg3` / `card`.
- **Filled accents use dark ink** (`--on-accent`) when white fails contrast.
- **No gradient-clipped headline text** — solid cyan for hero titles.
- **No cyan glow shadows** on dark UI — use neutral elevation.

## Typography

System UI stack (`-apple-system`, `Segoe UI`, sans-serif). Hierarchy via weight and size.

- Body / page subcopy: readable 15–18px.
- UI chrome / hints: minimum **12px**.
- Mobile bottom nav labels: minimum **11–12px**.
- Section badges: short labels; prefer sentence case over long ALL CAPS.

## Components

- **Nav:** Active state via background tint + cyan text (no thick single-side “AI tab” borders).
- **Mode cards:** Flat cards; hover uses **neutral** shadow.
- **Buttons:** Primary cyan + dark label; purple variant uses light purple fill + dark label.
- **Tip jar:** Compact card; visual polish only — do not change tip amounts, addresses, or pay helpers.

## Do / Do not

**Do** keep cyan + navy Orca identity · tighten contrast · enlarge tiny type · quiet glows.

**Do not** introduce purple-blue hero gradients · Inter-as-brand · nested card stacks · rebrand to unrelated systems · touch KEIKO / wallet / tip **behavior**.
