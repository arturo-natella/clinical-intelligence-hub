# MedPrep Session Handoff — 2026-07-17

**Repo state:** `main` @ `fe45bf2`, pushed to GitHub, working tree clean. Test suite **387/387**.
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

### P1 — Scrub patient data from logs  *(security, ~1 session)*
The 07-15 safety gate covers **cloud calls only**. Logs still leak PHI to the UI
terminal viewer and unencrypted disk:
- `src/extraction/text_extractor.py:103` — logs raw `chunk_text[:300]` (name/MRN/DOB) at INFO
- `src/extraction/text_extractor.py:166,189` — logs raw MedGemma responses
Fix: truncate to non-PHI metadata (chunk index, char counts, timing) or run
Presidio over log payloads. Add a regression test asserting no raw record text
reaches the log stream.

### P2 — CI on GitHub  *(~30 min, protects everything)*
387 tests, zero automation. Add a workflow running `python -m pytest tests/ -q`
on push/PR. Watch for macOS-specific deps (`apsw`, MPS-torch) — start with what
passes on `ubuntu-latest`, skip-mark the rest, or use a `macos` runner.

### P3 — Full-corpus soak run  *(the big unverified path)*
`MEDPREP_MAX_PAGES` defaults to unlimited and incremental dashboard updates are
wired, but a real 7,278-page run (~17 h) has never completed. Verify: memory
growth over ~1,040 chunks, dashboard staying responsive, and **mid-run crash
resume from the SQLite checkpoint** (claimed, never exercised).

### P4 — Make deep insights retrievable  *(highest insight value)*
Biomarker cascades, snowball differential, PGx interaction map, and trajectories
are modal-only: close the popup and they're gone, and none appear in the Word
report. Persist them (they're already computed server-side) and add report
sections with the same provenance treatment as flags.

### P5 — Confidence + provenance on cards; jargon rollout
Every finding carries `confidence` and source file/page; renderers strip both.
Surface them on flag, cross-disc, community, and treatment cards. Extend the
plain-English translator (Body Map) and lab glossary (Labs) to flag descriptions,
diagnosis names, and cross-disc titles.

### P6 — Decide the dead Pass 2
Gemini fallback extraction is verified dead code (see `memory/roadmap-gaps.md`).
Either wire it into the pipeline behind the PII gate or delete it — a half-wired
cloud path is the worst state for a privacy-first tool.

### P7 — Data-quality debts
- LOINC-code-normalized lab dedup (currently name-string only; variant names
  create duplicate panels).
- Replace the discontinued NLM API dependency in `src/standardization/`
  (details in `memory/roadmap-gaps.md`).

### P8 — UI nice-to-haves (deferred by design)
Text-size toggle, light mode, system-health panel ("is Ollama up, which model,
disk space"), sidebar density (16 items). None block daily use after the polish pass.

### Housekeeping
- `CLAUDE.md:83` still references the deleted rebuild plan `nested-leaping-goose.md` — remove the line.
- Verify env assumptions from the 04-15 handoff are still true before relying on
  them: UMLS key present? vault passphrase matches? (Presidio IS installed — the
  cloud gate depends on it.)

## Quick Reference

- Run server: launch config `"hub"` → http://localhost:5050 (never `python app.py` via Bash — use the preview tool)
- Tests: `python3 -m pytest tests/ -q`
- Model: `jwang580/medgemma_27b_q8_0` (~28 GB, Ollama, `keep_alive: "0"`)
- Lab date precedence: `test_date → date → collected_date`
- Labs grouped in frontend (`_groupLabsByName`); `/api/labs` stays flat
- `PINECONE_API_KEY` is global in `~/.zshrc`, NOT in project `.env`
- Design doc: `/Users/owner/docs/plans/2026-02-24-ck-plan-design.md`
