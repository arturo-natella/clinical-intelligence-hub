# PII Redaction Gateway — Design Spec

**Date:** 2026-07-08
**Status:** Awaiting user review
**Scope decisions (user-confirmed):** PII safety first (staging/cost workflow deferred). Gate every call to cloud AI. Redact identity only — patient clinical data must remain, that's the purpose of the tool. Add a dictionary of clinical terms so condition names aren't mistaken for person names.

## 1. Problem

The audit (2026-07-08) found that the CLAUDE.md guarantee — *"Presidio runs before every Gemini/API call"* — is not met anywhere:

1. **Pass 1.5 is a no-op** (`src/ui/pipeline.py:383-393`): imports `PIIRedactor`, but the class is named `Redactor` → `ImportError` → silently skipped. Even with the name fixed, the pass never calls `.redact()` on anything.
2. **The `Redactor` class is never called from any module.** It is unit-tested dead code relative to the network layer.
3. **12 cloud-AI call sites** exist, several triggered directly from UI endpoints that bypass the pipeline entirely. None redact.
4. The largest exposure — `self._profile.model_dump()` → Deep Research (`pipeline.py:420-428`) — is blocked today only by an unrelated bug (`run_pass3`/`run_pass4` don't exist on `DeepResearch`). **Accidental privacy, not designed privacy.**
5. The profile dump includes `Provenance.raw_text` (unredacted source snippets) and `source_file` (filenames often contain patient names).
6. Two AI sites pass the API key in the URL query string (`symptom_analytics.py:769`, `pubmed_monitor.py:462`).
7. Section 10's redaction audit trail reports 0 redactions — false confidence.

**Live smoke test (2026-07-08, Presidio + en_core_web_lg in venv):**
- Correct: name, DOB, MRN, phone, city/state, insurance ID, provider name all redacted; meds, labs, clinical dates, and in-context eponyms (Parkinson's, Crohn's, Hashimoto, Graves) preserved.
- Over-redaction: "Glasgow Coma Scale" → `[ADDRESS_REDACTED] Coma Scale`; "Romberg negative" → `[NAME_REDACTED] negative`.
- Under-redaction: bare street line "42 Elm Street" survived (only the city/state was caught).

## 2. Goals / Non-goals

**Goals**
- Every cloud-AI call passes through one gateway: redact → verify → send. No exceptions, enforced by test.
- Redact direct identifiers only; preserve all clinical content (the clinical-terms dictionary guarantees eponymous conditions survive).
- Fail closed: if redaction can't be guaranteed, the cloud call is skipped with a visible message (never crash — CLAUDE.md graceful degradation).
- Restore the Section 10 redaction audit trail.

**Non-goals (recorded follow-ups, not in this change)**
- Local→cloud staging / cost-control / resumability workflow (next project; the gateway is the seam it will attach to).
- Non-AI egress: Reddit search queries (med/condition names), clinical-DB lookups (OpenFDA/PubMed/RxNorm), environmental geocoder (**sends county+state — flagged as next-highest priority**), `dbsnp.py` key-in-URL.
- Pass 2 gap-fill orchestration logic (deciding which files need Gemini re-extraction).
- Model-ID consolidation (most sites use `gemini-2.0-flash`; CLAUDE.md mandates `gemini-3.1-pro-preview` — open question, separate decision).

## 3. Redaction policy

| Redacted (identity) | Preserved (clinical) |
|---|---|
| Patient & provider names | Medication names, doses, frequencies |
| Phone, email | Lab names, values, units, reference ranges |
| Street address, city/state (LOCATION) | Diagnoses & codes (SNOMED, ICD-10, LOINC) |
| SSN, driver's license, passport, credit card | Procedures, imaging findings, anatomy |
| Date of birth (labeled) | Clinical dates (lab/imaging/prescription) |
| MRN, insurance/member IDs | Symptoms and patient-reported descriptions* |

\* Free text is still scanned — a name *inside* a symptom description gets redacted; the description survives.

**Clinical-terms dictionary (`src/privacy/clinical_terms.py`):** a curated set (~80 seed terms, extensible) of eponymous diseases (Parkinson, Crohn, Hashimoto, Graves, Addison, Cushing, Sjögren, Raynaud, Barrett, Hodgkin, Paget, Marfan, Ehlers-Danlos, Guillain-Barré, Ménière, Kawasaki, Behçet, Huntington, Wilson, Fabry, Gaucher, Duchenne, Turner, Klinefelter, …), clinical signs/tests/scales (Babinski, Romberg, Glasgow, Apgar, Braden, Snellen, Coombs, Mantoux, Papanicolaou, …), devices/units (Doppler, Holter, Foley, Hounsfield, Celsius, Fahrenheit, Gray, Sievert). Matching is case-insensitive with possessives stripped ("Parkinson's" → "parkinson"). A `PERSON` or `LOCATION` finding whose span matches the dictionary is **not redacted and not logged**. The filter applies identically in the verification pass so eponyms can't trigger false fail-closed blocks.

**Accepted trade-offs:** a provider literally named "Dr. Parkinson" or a patient living in Glasgow would be preserved (rare; preserving the clinical term matters more). Future refinement: never allowlist a term preceded by an honorific (Dr./MD).

**New street-address recognizer:** custom Presidio `PatternRecognizer` for `\d{1,5} <words> (Street|St|Ave|Road|Rd|Drive|Dr|Lane|Ln|Blvd|Court|Ct|Way|Place|Pl)` — closes the smoke-test gap.

## 4. Architecture

### 4.1 `src/privacy/clinical_terms.py` (new)
`CLINICAL_ALLOWLIST: frozenset[str]` + `is_clinical_term(span: str) -> bool`. Pure data + one function; trivially extensible. Future: expand from local SNOMED data in `src/standardization/`.

### 4.2 `src/privacy/redactor.py` (modified)
- Apply the dictionary filter to `PERSON`/`LOCATION` analyzer results before anonymizing/logging.
- Register the street-address recognizer alongside the existing MRN/insurance/DOB recognizers.
- New `verify(text) -> list[Finding]`: re-analyze already-redacted text (dictionary-filtered); non-empty result means identifiers remain.
- The regex fallback path (Presidio missing) remains for defense-in-depth but is **never sufficient for cloud egress** (it misses names and addresses entirely).

### 4.3 `src/privacy/cloud_ai.py` (new — the gateway)
```python
class CloudAI:
    def __init__(self, api_key, db=None): ...   # db → redaction audit log
    def generate(self, prompt, *, model, generation_config=None) -> response
    def redact_profile(self, profile_dict) -> dict   # cloud-safe copy
    def preview(self, prompt) -> str   # what WOULD be sent; nothing transmitted
class CloudBlockedError(Exception): ...
```
- `generate()`: require Presidio active → `redact()` → `verify()` → send via `google.generativeai` SDK (key never in a URL) → return response. Any guarantee failure raises `CloudBlockedError`.
- `redact_profile()`: `redact_dict()` over the profile **plus** strips `Provenance.raw_text` and replaces `source_file` values with opaque doc indexes (`doc_01`, …); `source_page` kept.
- `preview()` supports a future "show me what leaves the machine" UI and manual verification, and is the hook the deferred staging workflow will use.
- Callers catch `CloudBlockedError` and skip gracefully with a visible progress message ("Cloud analysis skipped — PII protection unavailable").

### 4.4 Call-site conversion (all 12 — the complete cloud-AI inventory)
`ai_matcher.py:326`, `community_insights.py:231`, `deep_research.py:127,243`, `diagnostic_engine/cross_specialty.py:1175`, `gemini_fallback.py:73,121`, `snowball_engine.py:1964`, `symptom_analytics.py:769` (REST→SDK), `visit_prep.py:488`, `pubmed_monitor.py:462` (REST→SDK), `ui/app.py:3445`. Each replaces its own `genai.configure(...).generate_content(...)`/REST call with the gateway. REST→SDK conversion fixes both key-in-URL sites as a side effect.

### 4.5 Pipeline wiring (`src/ui/pipeline.py`)
- **Pass 1.5**: fix the import (`Redactor`), build the cloud-safe profile once via `redact_profile()`, cache it on the pipeline for Passes 2–4. Redaction counts flow to the existing `redaction_log` → Section 10 works again.
- **Passes 3–4**: replace the nonexistent `run_pass3`/`run_pass4` calls with the real API: `CrossDisciplinaryEngine.build_queries(redacted_profile)` → `DeepResearch.analyze(profile_summary, queries)` → merge `flags`/`connections`/`literature`/`questions` into `profile.analysis` (including `questions_for_doctor`, currently dropped). `profile_summary` is a compact JSON rendering of the redacted profile.
- Cloud modules receive the redacted profile only; their internals go through the gateway anyway (belt and suspenders).

## 5. Failure handling

| Condition | Behavior |
|---|---|
| Presidio not importable / model missing | All cloud AI blocked; visible message pointing to `setup.sh`; local passes unaffected |
| `verify()` finds residual identifiers | That call blocked + logged; pipeline continues |
| Gemini API error | Unchanged (existing per-pass try/except), but now *logged visibly* instead of `logger.debug` |

## 6. Testing

- **Policy units:** identifiers from the smoke-test corpus are redacted; Parkinson/Crohn/Glasgow/Romberg survive; "42 Elm Street" is caught; lab values and clinical dates intact.
- **Gateway units:** Presidio-inactive → `CloudBlockedError` (monkeypatched); planted residual identifier → blocked; `redact_profile` strips `raw_text` + filenames.
- **Guard test (the bypass lock):** scan `src/` for `generate_content|generativelanguage|genai.configure` outside `src/privacy/cloud_ai.py` → fail with a message telling the author to use the gateway. This converts the failed naming convention into an enforced invariant.
- **Audit:** after `redact_profile`, `redaction_log` has rows and `get_redaction_summary()` is non-empty.
- Existing `tests/test_phase4.py` redactor tests must keep passing.

## 7. Dependencies / setup

- Presidio already pinned (`requirements.txt:32-33`) and installed in the venv with `en_core_web_lg` (verified 2026-07-08). **Nothing to install for this machine.**
- Gap: nothing installs the spaCy model for fresh installs — add `python -m spacy download en_core_web_lg` to `setup.sh` (with a size note, ~600 MB) and a friendly gateway init error referencing it.

## 8. Verification plan

1. `python -m pytest tests/` — all new + existing tests green.
2. Manual: load demo data, run `preview()` on the Pass 3 prompt, eyeball zero identifiers, `verify()` returns empty.
3. Confirm a generated report's Section 10 shows non-zero redaction counts.

## Follow-up queue (out of scope, do not lose)

1. Environmental geocoder sends `demographics.location` (county+state) to OSM/Census/EPA — next privacy priority.
2. Local→cloud staging + cost/resume workflow (attaches at this gateway).
3. Reddit query policy; clinical-DB lookup identifier-scan; `dbsnp.py` key-in-URL.
4. Model-ID consolidation vs CLAUDE.md; 50-page extraction cap.
