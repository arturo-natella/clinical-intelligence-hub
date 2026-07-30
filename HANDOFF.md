# MedPrep Session Handoff — 2026-07-17

**Repo state:** `main` @ `a54f1c3`, pushed, working tree clean — the P1–P7 batch
is committed (branch `7.30.26-p1-p7-phi-logs-ci-deep-insights`, fast-forwarded to
main on 2026-07-30). Test suite: **426 passed** locally AND on the first GitHub
Actions run (ubuntu, 2m53s, green).
Server: launch config `"hub"`, Flask on **:5050**. Demo patient works end-to-end.
Prior handoffs (2026-03-13, 2026-04-15) are in git history; fix details live in
`~/.claude/projects/-Users-owner-Desktop-Tech-Tools-MedPrep/memory/bugs-and-fixes.md`.

## Where Things Stand

Three batches shipped and merged on 2026-07-17:

1. **Rescue** (`b596bb5`, `ab3296f`, `ed9bd63`) — four months of uncommitted work
   committed: PII cloud-safety gate, local-LLM routing, lab-date precedence,
   Ollama model preflight, flags render contract, blood-panel layout, hermetic
   environmental-sync test.
2. **Insight conveyance** (`2cdcc2a`) — dashboard plain-language narrative endpoint,
   `question_for_doctor` rendered on flag cards + fed into Visit Prep, community
   tab field-contract fix.
3. **Dashboard "Clinical Instrument" polish** (`fe45bf2`) — steel `--accent-primary`
   for all interactive states (red = severity/alert ONLY), text-contrast tokens
   lifted to WCAG AA, `.dash-*` components replace inline styles, risk-gauge D3
   angle fix, plain-word urgency line, sidebar aria-labels + `aria-current`,
   `prefers-reduced-motion`. Spec: `docs/superpowers/specs/2026-07-17-dashboard-polish-design.md`.

## What's Next (prioritized)

### P1 — Scrub patient data from logs  *(completed locally 2026-07-17)*
Raw source text, model responses, filenames, and extracted clinical values were
removed from extraction, imaging, validation, monitoring, UI, and pipeline
logging. Exception objects are reduced to their type before logging or progress
display. Regression tests assert that PHI sentinels never reach the log stream
and statically reject direct interpolation of patient-bearing values.

### P2 — CI on GitHub  *(DONE — verified green 2026-07-30)*
Read-only Ubuntu GitHub Actions workflow for push/PR with Python 3.13, pip
caching, dependency installation, and `python -m pytest tests/ -q`. Apple
Vision installs only on macOS. First run passed on ubuntu-latest in 2m53s.

### P3 — Full-corpus soak run  *(bookmarked / deferred 2026-07-17)*
The exact 7,278-page PDF is present, but no full run has completed. The prior
~17-hour estimate is unverified and conflicts with the code's much higher rough
estimate; benchmark a small sample before scheduling the soak. Chunk-level
SQLite resume is now implemented and regression-tested locally, but the live
run still needs to verify memory growth, dashboard responsiveness, and a real
mid-run stop/restart. Start only after the existing vault is unlocked locally;
never expose its passphrase in chat or shell output.

### P4 — Make deep insights retrievable  *(completed locally 2026-07-17)*
Biomarker cascades, snowball differential, PGx interaction map, and trajectories
now persist as fingerprinted snapshots inside the encrypted patient profile.
The UI APIs reuse valid cached results, `/api/deep-insights` retrieves them, and
the Word report renders all four with record-level provenance. The report and
pipeline compute missing snapshots locally with per-engine graceful degradation.

### P5 — Confidence + provenance on cards; jargon rollout  *(completed locally 2026-07-17)*
Flag and cross-disciplinary APIs now retain or evidence-match record provenance
and confidence without copying raw text. Flag, cross-disciplinary, community,
treatment, and Body Map cards render the metadata that actually exists;
community confidence remains explicitly "Unverified" rather than receiving a
clinical score. Body Map plain-English requests now include diagnosis names,
flag descriptions, and stored cross-disciplinary titles, with a shared local
clinical glossary extending the Labs tooltip pattern.

### P6 — Decide the dead Pass 2  *(completed locally 2026-07-17)*
The Gemini 3 Flash fallback is now wired for the narrow case it was designed
for: a fully completed local extraction that returns zero clinical entities.
Presidio is mandatory for raw-document fallback, local filenames are stripped
from every cloud payload, eligible documents are chunked without truncation,
and a hard default ceiling limits fallback to 3 whole documents of at most
60,000 characters each (5 calls/document). Shared Gemini calls now serialize,
rate-limit, and retry transient failures with bounded exponential backoff.

### P7 — Data-quality debts  *(completed locally 2026-07-17)*
- Lab merge now assigns local LOINC codes/reference metadata and uses LOINC as
  the primary identity, so same-event aliases deduplicate while dated readings
  remain a longitudinal series.
- Common SNOMED terms now validate against the local curated database first.
  The unusable unauthenticated NLM ValueSet expansion fallback was removed;
  Snowstorm remains optional enrichment for terms outside the local set.

### P8 — UI nice-to-haves
- **System-health panel — DONE 2026-07-30.** `GET /api/system-health` (six
  checks: Ollama, both MedGemma models, disk, Presidio, vault; 15 s cache,
  never raises, no patient data) + "System Status" dashboard card with
  plain-language hints. Loads at app init, before unlock — visible exactly when
  the stack is broken. Tests: `tests/test_system_health.py` (9).
  Spec: `docs/superpowers/specs/2026-07-30-system-health-panel-design.md`.
- **Text-size toggle — DONE 2026-07-30.** Sidebar button cycles
  Standard/Large/Extra large via root `zoom` (px-based stylesheet rules out
  rem scaling); stored in `localStorage["medprep_text_scale"]`, applied
  pre-paint by a whitelisting head script. Static contract tests in
  `tests/test_text_scale.py`; runtime cycle/persistence verified in browser.
  Spec: `docs/superpowers/specs/2026-07-30-text-size-toggle-design.md`.
- Still deferred: light mode, sidebar density (16 items). Neither blocks
  daily use after the polish pass.

### Cross-disciplinary unification — DONE 2026-07-30
The feature's three layers now compose (spec:
`docs/superpowers/specs/2026-07-30-crossdisc-unify-design.md`): the 29+7 query
engine is wired into Pass 3 (was a literal `[]` at the pipeline seam), engine
results snapshot-cache as deep-insight kind `cross_specialty` (8 ms cached vs
live Ollama+PubMed per view), stored + engine layers merge deduplicated
(`src/analysis/crossdisc_merge.py`) for the endpoint AND report, Pass 4
citations attach to their connections, the model retains layer fields, and the
report labels origins with an honest empty case. UI: five severities render,
filter chips + specialty select, session "Hide for now", local-AI credit
corrected. Ride-alongs fixed: Visit Prep 500, duplicate APS triad, stale "22
conditions" label, graph drawn synchronously (rAF never fired in background
tabs). Deferred: matching rigor (Direction 2 — abnormal-only labs, negation),
vault-persisted dismissals. Tests: `tests/test_crossdisc_unify.py` (14).

### Matching rigor + persisted dismissals — DONE 2026-07-30
Spec: `docs/superpowers/specs/2026-07-30-matching-rigor-design.md`. New
`src/analysis/diagnostic_engine/evidence_match.py` keeps labs structured
(direction from flag, or computed from reference range) and matches text per
record entry, so a NORMAL ferritin no longer satisfies `"high ferritin"`, a
negative ANA no longer satisfies `"ana positive"`, and `"denies chest pain"` /
`"family history of stroke"` stop counting as findings. Balanced policy: a
triad needs ≥1 specific signal (abnormal lab or a symptom outside
`NON_SPECIFIC_SYMPTOMS`) — vague fatigue+headache clusters no longer fire.
Also fixed a field asymmetry: demo/legacy labs use `test_name`, so the old
corpus saw **zero labs** — the matcher now accepts `name`/`test_name`/`test`
(demo went from 0 to 3 lab-backed findings). Dismissals persist in the
encrypted vault (`AnalysisResults.dismissed_findings`,
`POST /api/findings/dismiss|restore`, `GET /api/findings/dismissed`) and are
filtered inside `merge_connections`, so "Not relevant" holds across reloads
and keeps the finding out of the Word report. Tests:
`tests/test_matching_rigor.py` (26). Suite 478.

### Unwired-plumbing pass — DONE 2026-07-30 (branch `7.30.26-unwired-features-plumbing`)

An audit for features whose pipes weren't connected end-to-end (all 85 routes
diffed against every frontend fetch; all 99 Python modules checked for
importers; the launchd → scheduler → vault chain traced). Six gaps found and
closed. Suite **477 passed**. Full detail in `CHANGELOG.md` [Unreleased].

- **Monitoring could never run unattended** — the installer wrote the vault
  passphrase to the Keychain and nothing read it back; under launchd the
  scheduler died in `getpass`. `resolve_passphrase()` now reads the Keychain.
- **`volumetric_renderer.py` was orphaned** — now driven by
  `src/imaging/volumetric_twin.py` from the imaging pass, behind two closed-by-
  default gates. See the CHANGELOG for why a missing checkpoint must mean no
  mesh at all.
- **Deep Analysis card** surfaces persisted insights (`/api/deep-insights` had
  no caller); **symptom "History"** drill-down wires
  `/api/symptom-analytics/<id>`; **tracker** now reads `/api/tracker/vitals-types`
  and enforces each type's range in the form; **`/api/profile`** (whole-profile
  decrypted dump, zero callers) removed.

**Still needs the user at the machine:** run `./install_monitors.sh` to store
the passphrase and load the launchd agents — monitoring stays dormant until
then.

**Found but not fixed (spun out):** `POST /api/snowball-diagnoses` returns 500
whenever imaging findings are plain strings —
`snowball_engine.py:1651` assumes `list[ImagingFinding]` but
`_build_demo_profile()` stores one string per study. Pre-existing (a54f1c3),
and it means Differential diagnosis never appears in the new Deep Analysis card.

### Imaging findings shape — FIXED 2026-07-30
`ImagingStudy.findings` is `list[ImagingFinding]`, but `_build_demo_profile()`
stored one plain **string** per study. Every consumer that iterated it walked
the string character by character:

- `POST /api/snowball-diagnoses` called `.get()` on a character → **500**, so
  Differential diagnosis never appeared in the new Deep Analysis card;
- the Imaging view rendered **507 empty boxes** (one per character);
- `bodymap3d.js` joined findings raw, which yields `[object Object]` for real
  (correctly-shaped) pipeline data.

Fixed at the source (demo now emits `[{"description": …}]`) **and**
defensively in every consumer: `_normalize_findings()` in `snowball_engine.py`
and `App._normalizeFindings()` in `app.js`, both accepting strings, objects,
or mixed lists. Verified live: snowball 500 → 200 (99 ranked conditions),
imaging 507 empty boxes → 6 real findings. Tests:
`tests/test_imaging_findings_shape.py` (5).

### Housekeeping
- Removed the stale `nested-leaping-goose.md` rebuild-plan reference from
  `CLAUDE.md`.
- Environment check on 2026-07-17: Presidio imports successfully; no
  `UMLS_API_KEY` or `MEDPREP_VAULT_PASSPHRASE` is exported in this shell. The
  encrypted vault passphrase was not tested or exposed.

## Quick Reference

- Run server: launch config `"hub"` → http://localhost:5050 (never `python app.py` via Bash — use the preview tool)
- Tests: `python3 -m pytest tests/ -q`
- Model: `jwang580/medgemma_27b_q8_0` (~28 GB, Ollama, `keep_alive: "0"`)
- Lab date precedence: `test_date → date → collected_date`
- Labs grouped in frontend (`_groupLabsByName`); `/api/labs` stays flat
- `PINECONE_API_KEY` is global in `~/.zshrc`, NOT in project `.env`
- Design doc: `/Users/owner/docs/plans/2026-02-24-ck-plan-design.md`
