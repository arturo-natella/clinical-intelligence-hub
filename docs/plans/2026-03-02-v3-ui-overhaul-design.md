# MedPrep v3.0 — UI Overhaul Design

**Date:** 2026-03-02
**Status:** Approved
**Scope:** 10 items — sidebar nav, dashboard command center, timeline visualization, cross-disciplinary node graph, environmental tab, health tracker integration, body map fix, vitals surfacing, risk score rollup, chat embedding

---

## Design Principles

- **Target user:** Non-technical ~60-year-old managing complex medical history
- **30 years of data:** Built for deep longitudinal records, not just recent visits
- **The tool does the work:** Show information, don't assign homework
- **Partnership framing:** Empowerment over alarm, "Hey friend" tone
- **Visual appeal matters:** Thrivo.ai-inspired flowing aesthetics, Snowball-style node graphs
- **No data silos:** Dashboard connects everything; tabs are for drilling deeper

---

## 1. Sidebar Navigation

**Replaces:** Top tab bar

- Left sidebar, collapsible (icons + labels → icons only)
- ~220px expanded, ~60px collapsed
- Collapse/expand toggle at bottom

**Nav items (in order):**
1. Dashboard
2. Body Map
3. Timeline
4. Medications
5. Labs
6. Imaging
7. Symptoms
8. Environment
9. Health Tracker
10. Flags
11. Alerts
12. Report

**Removed tabs:** Chat (embedded in Dashboard)

---

## 2. Dashboard — Diagnostic Command Center

**Replaces:** Current summary card dashboard

### Top Bar
- **"So What?" AI narrative** — Plain-English paragraph: top 3 things to discuss with doctor, generated from all analysis engines
- **Risk score rollup** — Aggregate health trajectory indicator (improving / stable / needs attention), computed from lab trends, flags, conditions
- **Visit Prep readiness** — "12 items ready to print" with quick-print button

### Analytics Grid (widget-based layout)

| Widget | Data Source | Visual |
|--------|-----------|--------|
| Blood Panel Overview | Latest labs + flags + reference ranges | Table with red/green flags |
| Lab Trend Sparklines | All labs with 3+ data points (30 years) | Mini line charts, long-term trends |
| Medication Safety | PGx collisions | Red badge: "2 critical gene-drug interactions", expandable |
| Overdue/Missing Tests | Missing Negative Detection | Actionable list: "HbA1c — 8 months overdue" |
| Symptom-Medication Correlation | Symptom episodes + medication start/stop dates | Timeline overlay showing temporal relationships |
| Active Conditions | Diagnoses + Snowball top matches | Severity indicators, click for detail |
| Top Snowball Matches | Snowball engine | Mini node preview of strongest matches |
| Active Flags Count | All flag sources (monitoring, environmental, radiomic) | Categorized badge counts |
| Health Tracker | Fitbit/Apple Watch | Resting HR trend, sleep score, steps, SpO2 |
| Vitals | Clinical records (BP, weight, heart rate) | Sparkline trends |
| Cross-Specialty Alerts | Cross-Disciplinary engine | "3 potential multi-system patterns detected" |
| Recent PubMed Findings | Sweep results | Latest relevant research with relevance scores |

### Chat Panel
- Docked to right side, collapsible
- Full context of dashboard data
- For diagnostic Q&A: "My HbA1c has been rising for 5 years while my TSH normalized — what could explain that?"

---

## 3. Timeline — Flowing Interactive Visualization

**Replaces:** Current flat chronological list in `view-timeline`
**Tech:** D3.js with d3-zoom (already in project)

### Layout
- Full-width horizontal canvas
- Left = oldest record, Right = present
- Flowing bezier curves connect nodes (thrivo.ai wave aesthetic)

### Zoom Levels (semantic zoom)

| Level | View | Visible |
|-------|------|---------|
| 1 (default) | 5-year blocks | Major milestones only. Block labels: "2000–2005", etc. |
| 2 | Yearly | Major + notable events. Year labels. |
| 3 | Monthly | All events grouped by month. Minor nodes visible. |
| 4 | Individual | Every event with full detail. Daily granularity. |

### Node Classification (auto by event type)

**Major nodes** (larger circles, ~20px):
- New diagnoses
- Surgeries / procedures
- Hospitalizations
- First occurrence of a medication
- Critical lab flags

**Minor nodes** (smaller circles, ~10px):
- Routine labs
- Medication dose changes
- Symptom episodes
- Imaging studies

### Color Palette (existing)
- Blue (#5a8ffc) = Medication
- Red (#dc2626) = Lab
- Purple (#a07aff) = Diagnosis
- Gold (#f0c550) = Procedure
- Green (#5cd47f) = Imaging
- Rose (#e06c8a) = Symptom

### Interaction
- Scroll/pinch to zoom between levels — nodes fade in/out smoothly
- Pan left/right to navigate through time
- Click a node → expanding detail panel slides open below with all records from that date
- Hover → tooltip with event title and date

### Empty State
- Timeline path renders with message: "Upload your records to see your medical journey unfold"

---

## 4. Cross-Disciplinary — Node Graph Visualization

**Replaces:** Current list view
**Tech:** D3.js force-directed graph (Snowball pattern)

- Colored circles = detected multi-system patterns
- Circle size = number of matching patient data points
- Dashed connections between conditions sharing findings
- Click node → detail panel: matched findings, severity, specialties, question for doctor
- Category color coding by specialty (same legend as Snowball)
- Partnership messaging maintained

---

## 5. Environmental — Own Nav Tab

**Promoted from:** Buried in Flags view

- New sidebar entry under nav
- All 25 geographic risks with patient's location context
- Personalized risks (matching conditions/symptoms) highlighted at top
- Non-personalized risks below as awareness items
- Location indicator showing their region

---

## 6. Health Tracker Integration

**New feature — new tab + dashboard widgets**

### Architecture: Extensible Adapter Pattern
- `src/trackers/base.py` — abstract adapter interface
- `src/trackers/fitbit.py` — Fitbit Web API adapter (first)
- `src/trackers/apple_health.py` — Apple Health XML export adapter (second)
- Built to add: Garmin, Samsung Health, Oura, Whoop, etc.

### Data Points
- Heart rate (resting, active, recovery)
- Sleep (duration, stages, quality score)
- SpO2 trends
- Steps / activity / calories
- Correlation with symptoms ("resting HR spikes on days you log migraines")

### Own Tab — Deep Dive
- Full charts for each metric
- Date range picker
- Symptom overlay toggle
- Device management (connect/disconnect)

### Dashboard Widgets
- Resting HR sparkline
- Sleep score trend
- Steps this week
- SpO2 latest

---

## 7. Body Map Fix

**Problem:** 3D model doesn't render without patient data loaded
**Fix:** `autoLoadModel()` loads GLB immediately regardless of profile state
- No data = clean anatomy model, no pins, no deformations
- When data loads later, pins and deformations overlay onto already-rendered model
- Stays in its own Body Map tab

---

## 8. Vitals Surfaced

**Already in data model** (`src/models.py` — `Vital` class) **but not displayed**

- Blood pressure, weight, heart rate over time
- Dashboard: sparkline widgets
- Labs tab: vitals section with full trend charts

---

## 9. Risk Score Rollup

**New computed metric on Dashboard**

- Inputs: lab trends (rising/falling/stable), active flag count, condition severity, overdue tests, trajectory crossings
- Output: Single indicator — Improving / Stable / Needs Attention
- Visual: Color-coded badge or gauge on dashboard top bar
- Updates on each data load

---

## 10. Chat Embedded in Dashboard

**Removes:** Separate Chat nav tab
**Adds:** Collapsible chat panel docked to right side of Dashboard

- Same chat backend (Gemini)
- Has context of all dashboard data for informed Q&A
- Collapse/expand toggle
- Persists conversation during session

---

## 11. UI Framework — GNOME + Tailwind CSS

**Replaces:** Current hand-rolled `styles.css` with CSS custom properties

### Aesthetic: GNOME / Adwaita-Inspired
- Clean, minimal, generous whitespace
- Rounded corners (`rounded-xl`, `rounded-2xl`)
- Subtle shadows, not harsh borders
- Muted dark palette with purposeful accent colors
- Confident, calm typography hierarchy
- Large touch targets (60-year-old user)

### Tech: Tailwind CSS
- Load via CDN (no build step — keeps Flask simplicity)
- Tailwind utility classes replace custom CSS
- Dark mode as default (`dark:` prefix or class-based)
- Custom color tokens in Tailwind config for MedPrep palette:
  - Bluetron (medications), Heat red (labs), Amethyst (diagnoses/PGx)
  - Gold (procedures), Forest (imaging), Rose (symptoms)
  - Crimson (cascades), Teal (sweeps)

### Migration
- Existing `styles.css` custom properties → Tailwind equivalents
- Overlay styles (Snowball, Cascades, PGx, Trajectories, Symptom Analytics) migrated to Tailwind
- All existing JS DOM creation updated to use Tailwind classes

---

## Technical Notes

- **D3.js** already loaded for Cascades, PGx, Trajectories, Snowball — no new visualization dependencies
- **Three.js** already loaded for Body Map — no change
- **Tailwind CSS** added via CDN for GNOME-style design system
- **DOM safety**: All new code uses createElement/textContent (no innerHTML) per existing security policy
- **Flask backend**: New endpoints for health tracker, vitals, risk score
- **Existing overlays** (Snowball, Cascades, PGx, Trajectories, Symptom Analytics) migrated to Tailwind
- **MedPrep-Demo** will need updates after v3 stabilizes
