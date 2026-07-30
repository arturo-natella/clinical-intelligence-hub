# Cross-Disciplinary Unification — Design

**Date:** 2026-07-30 · **Approved scope:** Directions 1 (make the promise real) + 3
(conveyance) + ride-along bug fixes. Direction 2 (matching rigor) deferred, except
snapshot caching which lands here as part of unification.

## Problem (verified 2026-07-30)

Three disjoint layers wear the feature's name and never compose:
rule engine (40 triads, live per request, never persisted, never in report),
local-LLM discovery (≤3, PubMed-labeled not filtered, credited to "Gemini" in UI),
and Gemini Pass 3 (only layer reaching the report; zero attached literature,
zero validation). The advertised 29-specialty + 7-domain query engine is dead
code: `pipeline.py:825` passes a literal empty query list to Pass 3. Pass 4
citations go to a flat list never linked back. Report's empty case reads as
clinical reassurance. Model silently drops every layer-specific field
(no `extra` config → Pydantic ignores unknown keys at `model_validate`).

## Phase A — one persisted truth

1. **Model** (`src/models.py`): `CrossDisciplinaryConnection` gains
   `connection_type: str` ("pattern_database" | "local_ai" | "cloud_analysis",
   default "cloud_analysis"), `total_hits: int|None`, `total_possible: int|None`,
   `matched_labs: list[str]`, `evidence_source: str`, `diagnostic_source: str`,
   `pubmed_verified: bool|None`. PubMed citations from local discovery convert
   into `supporting_literature` (`LiteratureCitation`). Regression test pins the
   round-trip (fields survive `model_validate` + `model_dump`).
2. **Rule engine** (`cross_specialty.py`): merge the duplicate APS triads into
   one; `evidence_source` count computed from `len(SYSTEMIC_DISEASE_TRIADS)`;
   both engine paths emit `connection_type`.
3. **Pass 3 wiring** (`pipeline.py`): build queries via
   `CrossDisciplinaryEngine.build_queries(profile)` capped at 60 (priority:
   polypharmacy → med×lab → med×dx → per-entity → adjacent domains, preserving
   builder order), pass to `dr.analyze`. Gemini call already serialized +
   rate-limited (P6).
4. **Pass 4 attachment** (`deep_research.py`): citations fetched for a
   connection attach to that connection's `supporting_literature`; flat
   `results["literature"]` stays for compatibility.
5. **Snapshot + merge**: new module `src/analysis/crossdisc_merge.py` with
   `merge_connections(stored, engine_results)` — dedupe key: casefolded title
   stripped of parentheticals + ≥1 shared specialty; richer entry wins, fields
   merge (citations union). Engine results (rule + local AI) cached as a
   `DeepInsightSnapshot` kind `"cross_specialty"` (same fingerprint pattern as
   the existing four). `/api/cross-disciplinary` serves merged stored+snapshot;
   recompute only on fingerprint change or `?refresh=1`. Report section 8
   renders the same merged set via the shared helper.
6. **Report honesty** (`builder.py` §8): per-connection origin label
   ("Pattern database" / "Local AI + PubMed" / "Cloud analysis"), match
   strength ("N of M known indicators"), matched labs, evidence/diagnostic
   source or attached literature. Empty case: "Cloud pattern analysis did not
   run for this report (offline or no API key). Local pattern checks are shown
   on the dashboard." — never implies well-coordinated care.
7. **Ride-alongs**: Visit Prep 500 (normalize legacy string entries in the
   dedup loop via `_normalize_question_entry`); demo connections aligned to
   real production field shapes.

## Phase B — conveyance

8. **Graph** (`crossdisc_graph.js`): `_sevRadius`/`_sevColor`/gradient defs
   cover all five severities; `_specColors` keys aligned to the canonical
   29-specialty taxonomy (fallback color stays); source block credits
   "your local AI model", not Gemini.
9. **Filters**: severity + specialty chips above the graph (client-side), and
   session-only "Hide for now" per connection. Persistent dismissal deferred
   (PHI-derived preference belongs in the vault, not localStorage);
   pattern↔pattern edges cut as clutter.

## Tests

Model round-trip (silent-drop regression) · APS single entry + dynamic count ·
query wiring (non-empty, capped, ordered) · Pass 4 attachment · merge dedup
(exact, parenthetical, specialty-overlap, field union) · endpoint caching
(second call runs no engine — counter monkeypatch) · report evidence + empty
copy · Visit Prep string-entry regression · graph static contract (5
severities, no "Gemini" in local branch, filter hooks present).

## Out of scope (deferred with reasons)

Matching rigor (abnormal-only labs, negation, synonyms) — Direction 2, own
spec. Persistent dismissals — needs vault-backed prefs. Pass 5 connection
validation — Pass 4 attachment covers literature; a second validator pass
would duplicate it.
