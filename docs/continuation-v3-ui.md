# MedPrep v3 UI Overhaul — Continuation Guide

Pick up where we left off if the context window resets.

## What This Project Is

**Clinical Intelligence Hub** — a medical data visualization tool that helps a real person understand their health condition. The user's friend has Type 2 Diabetes with cardiovascular comorbidities. This is not a toy project. The goal is to **save their life** by making complex medical data understandable.

## Architecture

- **Stack**: Flask SPA, Tailwind CSS (CDN), D3.js for charts, GNOME/Adwaita dark theme
- **Location**: `/Users/owner/Desktop/Tech Tools/MedPrep`
- **Server config**: `medprep` in `/Users/owner/Desktop/Tech Tools/.claude/launch.json`, port 5050
- **Vault passphrase**: `test`

## Key Files

| File | What it does |
|------|-------------|
| `src/ui/app.py` | Flask backend — all API endpoints, `_build_demo_profile()` for demo data |
| `src/ui/static/index.html` | Full SPA layout — sidebar, all tab views, KPI cards, chart containers |
| `src/ui/static/app.js` | SPA router, `loadDashboard()`, `loadDemoData()`, all tab loaders |
| `src/ui/static/js/dashboard_charts.js` | D3 chart library — gradient-based, blue-teal palette |
| `src/ui/static/js/sparklines.js` | Mini D3 line chart for lab trend widgets |
| `src/ui/static/js/snowball.js` | Differential diagnosis force-directed graph |
| `src/ui/static/js/cascades.js` | Drug interaction cascade visualization |
| `src/ui/static/js/pgx_map.js` | Pharmacogenomics gene-drug map |
| `src/ui/static/js/symptoms.js` | Symptom tracking UI |
| `src/ui/static/js/symptom_analytics.js` | Symptom analytics charts |
| `src/ui/static/styles.css` | GNOME dark theme tokens and base styles |
| `docs/plans/2026-03-02-v3-implementation-plan.md` | Full implementation plan |

## Design Principles (User Directives)

1. **Tableau-level data visualization** — "think tableau data crunching"
2. **Unified color palette** — cohesive blue-to-teal gradient family, NOT rainbow/skittles
3. **Flat geometry** — no rounded corners on bars, no cornerRadius on arcs, thin donut rings
4. **Gradient fills** — SVG `<linearGradient>` on all chart elements
5. **Color = meaning** — warm tones (red/amber) reserved ONLY for clinical severity. General data uses cool blue-teal tones
6. **Professional, not cartoonish** — data-dense, muted colors, clean typography

## Current Color System

### Dashboard Charts (`dashboard_charts.js`)

**General data gradients** (blue-teal family):
```
Azure:      #6B9BF7 → #3565C7
Cyan:       #7EC4E8 → #3A8BB8
Teal:       #5ED4C8 → #2A9D90
Steel:      #8BA8E8 → #4A68B8
Indigo:     #9B8BE0 → #6050B0
Sage:       #6BD4A8 → #38A078
Cornflower: #7AB0F0 → #4070C0
Aqua:       #68C8D8 → #3090A8
```

**Severity gradients** (warm, muted):
```
Critical: #C84040 → #8B1A1A
High:     #C87850 → #984828
Moderate: #C8A848 → #987820
Low:      #58B888 → #308860
```

**KPI cards**: All use `#5080B0` (steel blue) top border, white `#fff` numbers.

### Charts Implemented

All in `DashboardCharts` object:
- `renderLineChart` — multi-series time chart with gradient area fills
- `renderBarChart` — vertical bars with individual gradients
- `renderHBars` — horizontal bars with gradient fills
- `renderDonut` — thin ring (14px) with gradient segments, side legend
- `renderRiskGauge` — half-circle arc with severity gradient
- `renderLabRangeBars` — value markers on reference range tracks
- `renderSeverityBar` — stacked horizontal bar with severity legend

### Helper: `_grad(defs, id, top, bot, vertical)`
Creates SVG `<linearGradient>` in `<defs>` and returns `url(#id)` reference.

## Demo Data

- `/api/demo-data` POST endpoint loads comprehensive Type 2 Diabetic patient profile
- `_build_demo_profile()` in `app.py` generates: demographics, 10 medications, 8 diagnoses (ICD-10), 28 symptom entries, 40+ lab results, 6 imaging studies, 6 genetic variants, 4 procedures, 12 clinical flags, drug interactions, cross-disciplinary patterns, community insights, literature refs, questions for doctor
- "Load Demo Patient" button in the upload card area calls `App.loadDemoData()`

## What's Done (Phases A-F + Design Polish)

- [x] Sidebar navigation with all 15 tabs
- [x] Dashboard with 6 KPI cards (unified steel blue)
- [x] 7 chart widgets: blood panel, medication donut, flags donut + severity bar, lab trends, conditions h-bars, symptom bars, cross-specialty cards
- [x] Overdue tests table
- [x] AI clinical summary placeholder
- [x] Quick actions bar
- [x] Clinical assistant chat panel
- [x] Comprehensive demo patient data
- [x] Flat chart geometry (no rounded corners, no cornerRadius)
- [x] Gradient fills on all chart elements
- [x] Unified blue-teal palette (no rainbow skittles)

## What's Next (Remaining Plan Phases)

- [ ] **Verify demo data populates ALL tabs** (meds, labs, imaging, symptoms, timeline, genetics, flags, etc.)
- [ ] **Phase G1**: Cross-disciplinary node graph (force-directed D3 graph showing connections between specialties)
- [ ] **Phase H1**: Flowing timeline visualization (horizontal scrolling medical history)
- [ ] **Phase I1-I2**: Health tracker integration (daily logging for vitals, mood, symptoms)
- [ ] **Phase J1**: Vitals surfaced on dashboard (BP, heart rate, weight trending)
- [ ] **Phase K1**: Risk score rollup (aggregate risk from all flags)
- [ ] **Phase Z1-Z3**: Integration test, demo update, changelog

## v3.1 Planned Features (After v3)

- Family medical records
- Medication tracking with reminders
- Mood/wellness check-ins
- Specialist mapping with referral network
