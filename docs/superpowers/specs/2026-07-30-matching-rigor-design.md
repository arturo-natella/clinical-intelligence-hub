# Matching Rigor + Persisted Dismissals — Design

**Date:** 2026-07-30 · **Approved:** "Balanced" precision policy. Follows the
deferred items in `2026-07-30-crossdisc-unify-design.md`.

## Problem (measured, not assumed)

`SYSTEMIC_DISEASE_TRIADS` carries 177 lab markers; only 29 encode a direction
("low" ×20, "high" ×9). The engine joins the whole record into one string and
strips qualifiers before substring matching, so:

- `"high ferritin"` → `"ferritin"` matches a **normal** ferritin.
- `"ana positive"` → `"ana"` matches an ANA that came back **negative**.
- `"no chest pain"`, `"denies dyspnea"`, `"family history of stroke"` all count
  as positive hits — one joined blob has no notion of scope or negation.
- A triad can fire on non-specific symptoms alone (fatigue + headache +
  dizziness appear in a large share of the table).

Dismissals are session-only (`CrossDiscGraph._hidden`), so a finding the reader
already rejected returns on every reload and still occupies the report.

## Part A — evidence matching (new module)

`src/analysis/diagnostic_engine/evidence_match.py` owns matching so
`cross_specialty.py` keeps only the triad table and scoring. Public surface:

```python
build_evidence(profile_data) -> Evidence          # structured, PHI-free-shaped
Evidence.match_symptom(term) -> bool
Evidence.match_lab_marker(marker) -> bool
is_specific_symptom(term) -> bool
```

1. **Structured labs.** `Evidence.labs`: `{name, direction, is_abnormal}` where
   `direction ∈ {"high","low",None}`. Direction comes from the lab's flag
   (`high|h|elevated|critical high|abnormal high` → high; `low|l|decreased`
   → low) and, when the flag is absent, is **computed** from `value` against
   `reference_range` / `reference_low` / `reference_high` (numeric parse;
   ranges like `"13.0-17.0"` or `"< 5.7"` supported). Unparseable → `None`,
   `is_abnormal=False`.
2. **Lab marker matching.** A marker whose base name matches a lab counts only
   when that lab `is_abnormal`; if the marker carries a direction, the lab's
   direction must equal it. Positivity markers (`"… positive"`) require an
   abnormal/positive result. A marker that matches **no** lab falls back to
   text matching against non-lab entries — so `"hypercalcemia"` or
   `"proteinuria"` recorded as a diagnosis still counts.
3. **Per-entry text matching with negation.** Text entries (diagnoses, meds,
   symptoms, episode text, imaging, genetics) are matched individually. A hit
   is rejected when a cue appears within 40 characters before it in the same
   entry: `no`, `not`, `never`, `denies`, `denied`, `negative for`, `without`,
   `ruled out`, `r/o`, `absent`, `resolved`, `family history of`, `fh of`,
   `mother`, `father`, `sibling` (attribution, not the patient).
4. **Synonyms.** Small curated lay↔clinical map (dyspnea/shortness of breath,
   fatigue/tired/exhaustion, pruritus/itching, syncope/fainting, myalgia/muscle
   pain, arthralgia/joint pain, paresthesia/numbness/tingling, edema/swelling,
   palpitations/racing heart, alopecia/hair loss). Bidirectional, applied to
   symptom terms only.
5. **Specificity gate (Balanced policy).** `NON_SPECIFIC_SYMPTOMS` (fatigue,
   headache, dizziness, nausea, malaise, brain fog, weakness, insomnia, anxiety,
   weight gain/loss, joint pain, muscle pain). A triad fires only when it has
   ≥1 **specific** signal: an abnormal lab hit or a symptom outside that set.
   Threshold and severity rules otherwise unchanged.

`cross_specialty._analyze` consumes `Evidence`; `_build_corpus` stays for the
local-AI prompt (that path needs prose, not structure).

## Part B — persisted dismissals

- **Model:** `AnalysisResults.dismissed_findings: list[DismissedFinding]` with
  `key` (normalized title, same `_dedupe_key` as the merge), `kind`
  (`"cross_disciplinary"`), `title`, `dismissed_at`. Stored inside the
  encrypted profile — never localStorage, because it is PHI-derived.
- **Endpoints:** `POST /api/findings/dismiss` `{kind, title}` and
  `POST /api/findings/restore` `{kind, title|all}`; both persist via the
  existing vault save and return the updated dismissed list. Unknown kind → 400.
- **Filtering:** `merge_connections(..., dismissed_keys=...)` drops matches, so
  the graph, dashboard tile, Visit Prep counts, and Word report all respect a
  dismissal from one place.
- **UI:** detail-rail button becomes "Not relevant" (persists, with an undo
  affordance); filter bar shows "N dismissed — show" which calls restore.
  Session-only `_hidden` is removed in favor of the persisted list.

## Tests (`tests/test_matching_rigor.py`)

Direction: normal ferritin no longer matches `"high ferritin"`; a high ferritin
does; a low value does not satisfy a "high" marker · flagless value + reference
range computes direction · `"ana positive"` needs a positive result · negation
and family-history entries rejected, plain mention accepted · synonym pair
matches both ways · specificity gate: fatigue+headache+dizziness alone does not
fire, same profile plus one abnormal lab does · end-to-end `analyze()` on a
synthetic profile (first real test of the triad table) · dismissal round-trip
(dismiss → merge filters → restore) · endpoint contract incl. 400 on bad kind.

## Out of scope

Symptom→SNOMED normalization, value-threshold severity (e.g. how high a
ferritin), and reference ranges for markers the record does not carry. Local-AI
discovery prompt/caps unchanged.
