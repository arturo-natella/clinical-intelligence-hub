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
