# MedPrep v2.1 — Next Feature Batch

**Created:** 2026-03-01
**Status:** Spec ready for implementation
**Base:** All 13 v2.0 features complete (see PROGRESS.md)
**Plan file for v2.0:** `/Users/owner/.claude/plans/jolly-questing-shannon.md`

---

## Instructions for Claude

1. Read `PROGRESS.md` to understand the full v2.0 architecture, UX decisions, and file locations
2. Read `src/models.py` to understand existing data models (Diagnosis, Medication, Symptom, etc.)
3. Read `src/ui/app.py` to understand existing API endpoints
4. Review gaps in each feature below against what already exists
5. Implement each feature following the established patterns:
   - Pydantic models in `src/models.py` → encrypted JSON vault
   - Flask REST endpoints in `src/ui/app.py`
   - Frontend JS in `src/ui/static/js/` (createElement/textContent only, NO innerHTML)
   - DOM safety: `while (content.firstChild) content.removeChild(content.firstChild)` for clearing
   - UX: "Hey friend" tone, partnership framing, no alarming alerts
6. After implementing, update `tools/seed_demo.py` to include demo data for new features
7. Update `PROGRESS.md` with each completed feature

**Vault passphrase:** `test` (main) / `demo` (MedPrep-Demo)
**Server config:** medprep on port 5050 with autoPort in `.claude/launch.json`

---

## Feature 14: Diagnosis Confirmation Tracking

**Problem:** When a doctor gives a diagnosis, there's no way to track:
- When and who confirmed it
- Whether the patient agrees or disputes it
- How the diagnosis evolved over time (suspected → probable → confirmed)
- What evidence supports or contradicts it

**What exists now:**
- `Diagnosis` model has: name, snomed_code, icd10_code, date_diagnosed, status (Active/Resolved/Chronic), diagnosing_provider, provenance
- `GET /api/diagnoses` returns raw list
- No edit/update endpoints for diagnoses
- Diagnoses appear in Timeline, Dashboard stats, Visit Prep, and Snowball

**What to build:**
- Add confirmation status enum: `pending → suspected → probable → confirmed → ruled_out`
- Add confirmation history: list of dated status transitions with provider and notes
- Add patient agreement field: `agree / disagree / unsure` with optional reason
- Add evidence links: which labs, imaging, or symptoms support/contradict this diagnosis
- API endpoints: `PUT /api/diagnoses/<id>` to update confirmation status, `POST /api/diagnoses/<id>/history` to add history entry
- UI: Diagnosis detail panel (click a diagnosis to see its journey — who said what, when, what evidence)
- Integration: Feed confirmation status into Visit Prep ("I'd like to discuss my [suspected] diagnosis of X")

---

## Feature 15: Health Tracker Integration (Fitbit / Apple Watch)

**Problem:** Wearable health data (heart rate, sleep, steps, activity, SpO2) isn't captured. This data could correlate with symptoms (e.g., elevated resting HR during migraine episodes, poor sleep before fatigue flares).

**What exists now:**
- `Vital` model: name, value, unit, measurement_date, provenance (flat, no time-series)
- No import/integration with external health platforms
- Symptom episodes have `time_of_day` but no wearable correlation

**What to build:**
- New model: `HealthTrackerReading` — source (fitbit/apple_watch/manual), metric (heart_rate/steps/sleep_hours/sleep_quality/spo2/active_minutes/calories), value, unit, timestamp, provenance
- Storage: list in `ClinicalTimeline.health_tracker`
- Import methods:
  - **Manual CSV upload** (Fitbit export, Apple Health export) — parse common formats
  - **Manual entry** for one-off readings
- API endpoints: `POST /api/health-tracker/import` (CSV), `POST /api/health-tracker` (manual entry), `GET /api/health-tracker` (with date range filter)
- UI: Health Tracker view or sub-tab showing trends (D3 line charts)
- Integration: Correlate wearable data with symptom episodes in Symptom Analytics (e.g., "Your average resting HR was 12bpm higher on migraine days")
- Integration: Feed into Visit Prep ("Wearable data shows sleep averaging 5.2 hours on flare days vs 7.1 hours normally")

---

## Feature 16: Family Medical History

**Problem:** Family medical history (mother, father, siblings, grandparents) is critical for hereditary risk assessment but isn't tracked. A mother with breast cancer or father with heart disease changes the risk calculus.

**What exists now:**
- No family history model
- Demographics has biological_sex, birth_year, blood_type, ethnicity, location
- Snowball engine scores conditions but doesn't factor family history
- Cross-Specialty engine checks for systemic patterns but not hereditary ones

**What to build:**
- New model: `FamilyMember` — relationship (mother/father/sibling/maternal_grandmother/paternal_grandfather/etc.), name (optional), conditions (list of {name, age_at_diagnosis, status}), deceased (bool), cause_of_death (optional), notes
- Storage: `PatientProfile.family_history: list[FamilyMember]`
- API endpoints: `GET /api/family-history`, `POST /api/family-history`, `PUT /api/family-history/<id>`, `DELETE /api/family-history/<id>`
- UI: Family History section (accessible from Settings or its own nav item) — simple cards per family member with their conditions
- Integration: Snowball engine should weight conditions higher if they appear in family history (e.g., diabetes in mother → higher weight for diabetes-related conditions)
- Integration: Visit Prep should include "Family history of [condition] in [relationship]" in relevant sections
- Integration: Missing Negatives should recommend screening earlier if family history warrants (e.g., colonoscopy at 40 if parent had colon cancer)

---

## Feature 17: Specialist Visit Mapping

**Problem:** Patients see many specialists over time but there's no way to visualize the pattern — which specialists, how often, for what, and whether visits correlate with symptom changes or diagnosis evolution.

**What exists now:**
- Provider names stored as strings on Diagnosis, Medication, LabResult, ClinicalNote
- No Provider model with specialty/role
- No visit tracking (ClinicalNote has note_date, provider, facility, but it's unstructured)

**What to build:**
- New model: `SpecialistVisit` — visit_date, provider_name, specialty (enum or free text: primary_care/neurology/endocrinology/cardiology/rheumatology/etc.), facility, reason, outcome_notes, diagnoses_discussed (list of diagnosis IDs or names), follow_up_date, provenance
- Storage: `ClinicalTimeline.specialist_visits: list[SpecialistVisit]`
- API endpoints: `GET /api/specialist-visits`, `POST /api/specialist-visits`, `PUT /api/specialist-visits/<id>`, `DELETE /api/specialist-visits/<id>`
- UI: Specialist Map view — timeline visualization showing visits by specialty on parallel swim lanes (D3)
  - Color-coded by specialty
  - Click a visit to see details (reason, outcome, what was discussed)
  - Overlay symptom episodes on the timeline to spot correlations
- Analytics: "You've seen 3 neurologists in 6 months but your migraines have increased — consider discussing treatment changes"
- Integration: Visit Prep should reference recent specialist visits ("Last saw Dr. Park (Neurology) on [date] — discussed [topic]")

---

## Feature 18: Medication Adherence Tracking

**Problem:** Taking medication as prescribed is critical but hard to track. Users need to log when they took each med, track missed doses, and note any reactions or side effects.

**What exists now:**
- `Medication` model: name, dosage, frequency, route, start_date, end_date, status, reason
- No adherence/compliance tracking
- No reaction/side-effect logging
- Medication view shows a static table

**What to build:**
- New model: `MedicationDose` — medication_id (links to parent Medication), dose_date, dose_time, taken (bool), skipped_reason (optional), reaction (optional free text), severity_of_reaction (none/mild/moderate/severe), date_logged
- Storage: either `Medication.doses: list[MedicationDose]` (nested) or `ClinicalTimeline.medication_doses: list[MedicationDose]` (flat)
- API endpoints: `POST /api/medications/<id>/dose` (log a dose), `GET /api/medications/<id>/doses` (history), `GET /api/medication-adherence` (summary across all meds)
- UI: Medication Tracker view or sub-tab
  - Quick-log buttons: "Took it" / "Skipped" / "Took it + had a reaction"
  - Calendar heatmap per medication (green = taken, red = missed, yellow = reaction)
  - Adherence percentage per med
  - Reaction history list
- Integration: Symptom Analytics should correlate missed doses with symptom flares ("You skipped gabapentin 3 times in 2 weeks — tingling episodes increased")
- Integration: Visit Prep should include adherence summary ("Metformin: 92% adherence this month, 2 missed doses")
- Integration: If reactions are logged, flag them alongside PGx collision data

---

## Implementation Order (Suggested)

| Priority | Feature | Rationale |
|----------|---------|-----------|
| 1 | **F18: Medication Adherence** | Daily use feature, high engagement, simple model extension |
| 2 | **F14: Diagnosis Confirmation** | Core data model improvement, feeds many existing features |
| 3 | **F16: Family Medical History** | Independent module, directly improves Snowball + Visit Prep |
| 4 | **F17: Specialist Visit Mapping** | New visualization, requires Provider model |
| 5 | **F15: Health Tracker Import** | Complex (CSV parsing, external formats), highest integration effort |

---

## Cross-Cutting Concerns

- **All new data must be vault-encrypted** — extends the existing Pydantic → JSON → AES-256-GCM pattern
- **All new endpoints need vault unlock check** — follow `_profile_data` pattern in app.py
- **All DOM manipulation must use createElement/textContent** — security hook enforces no innerHTML
- **Demo data** — update `tools/seed_demo.py` with ghost data for each new feature
- **UX tone** — partnership, empowerment, "hey friend" — never alarming
