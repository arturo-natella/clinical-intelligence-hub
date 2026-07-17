# Dashboard Polish — "Clinical Instrument" Pass

**Date:** 2026-07-17 · **Scope approved:** Full polish pass + two a11y fold-ins (nav names, urgency wording). Bold restructure explicitly rejected.

## Problem

The dashboard reads as unfinished next to the rest of the app: the KPI strip and chart
cards are inline-styled with a rogue palette (`#5080B0` top borders, `#607080`/`#777`
labels, `#556` units) that bypasses the Amaru Dark token system; 10px micro-labels and
low-opacity text tokens (0.56/0.40/0.24 white) are hard to read for the target user
(non-technical, ~60); red — the medical alert color — is spent on navigation and
primary buttons, diluting its meaning.

## Design decisions

1. **Red means attention, nothing else.** New `--accent-primary` (Clinical Steel,
   `#5a8ffc`, already in the palette as `--accent-bluetron`) takes over all interactive
   identity: active sidebar item, links, `::selection`, `.btn-primary`, focus rings,
   profile icon. `--heat` red remains ONLY for severity/alert semantics. This is the
   signature: any red pixel on the dashboard is clinically meaningful.
2. **Contrast lift at the token layer.** `--text-secondary` 0.56→0.72,
   `--text-muted` 0.40→0.58, `--text-faint` 0.24→0.42. One edit brightens every
   muted label app-wide; on `#171717` cards the muted tier now passes WCAG AA (≈4.6:1).
3. **Dashboard de-inlined into components.** New classes `.dash-grid-kpi`,
   `.dash-kpi(-label/-value/-unit)`, `.dash-grid-charts`, `.dash-card(-title)`,
   `.dash-summary`, `.dash-urgency`. Labels: 12px JetBrains Mono uppercase eyebrows
   (matches `.section-label` idiom — instrument-readout structure). KPI values: 28px,
   `font-variant-numeric: tabular-nums`. Card padding 16/18px, grid gap 14px,
   radius 10px. The undifferentiated steel top-border on all six KPI tiles is removed.
4. **Summary leads the page.** The plain-language Clinical Summary panel moves above
   the KPI strip (hierarchy fix within polish scope — the one thing a non-technical
   reader should see first), with a 3px Clinical Steel left rule and 15px/1.65 body.
5. **Plain-word urgency line** (`#dash-flags-urgency`) under the flags donut, populated
   by `App.renderDashboard`: critical → "N critical finding(s) — discuss with your
   doctor promptly." / high → "N finding(s) worth discussing at your next visit." /
   else → "No urgent findings." Red text only for the critical tier.
6. **A11y floor:** `aria-label` on every sidebar button (names survive icon-only
   collapsed mode), `aria-label="Main navigation"` on the nav, `aria-current="page"`
   managed at the view-switch site in app.js, global `:focus-visible` ring in
   accent-primary, `prefers-reduced-motion` media guard disabling transitions.

## Constraints

- Every element ID keeps its name — `app.js` renders by ID (`dash-risk-gauge`,
  `kpi-*`, `dash-*`). No JS render-contract changes beyond the urgency line + aria-current.
- Chart internals (`dashboard_charts.js` axis fonts, palettes) untouched this pass.
- Non-dashboard views untouched except what the token lift inherits.
- Legacy `.nav-tabs` CSS (unused in markup) re-pointed but not removed.

## Verification

Suite stays green (379); browser pass on the running hub server with demo patient:
readable labels at arm's length, no red outside severity contexts, collapsed-sidebar
buttons announce names, urgency line renders, no console errors, screenshot review.
