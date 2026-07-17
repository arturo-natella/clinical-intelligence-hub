# MedPrep Session Handoff — 2026-04-15

## What Was Done This Session

### 1. Fixed: MedGemma 404 Spam (1593 silent errors)

**Files:** `src/extraction/text_extractor.py`, `README.md`, `setup.sh`

**Symptom:** Pipeline emitted `MedGemma call failed — model 'jwang580/medgemma_27b_q8_0' not found (status code: 404)` for all 1593 chunks but kept "running."

**Root cause (two-part):**
1. The model wasn't actually pulled in Ollama. User had previously deleted local models.
2. The preflight `_check_ollama` only verified the daemon responded — it did NOT verify the specific model was present. Combined with `except Exception` in the call site, every chunk silently 404'd instead of failing fast.

**Fix:**
- `_check_ollama` rewritten ([src/extraction/text_extractor.py:592-637](src/extraction/text_extractor.py:592)) — no longer `@staticmethod`, walks `ollama.list().models` checking for `MODEL_NAME`, `MODEL_NAME:latest`, and the bare name. Distinguishes "daemon down" vs "model missing" with different remediation messages.
- `__init__` reordered ([src/extraction/text_extractor.py:57-62](src/extraction/text_extractor.py:57)) so `self._progress` is set BEFORE `self._available = self._check_ollama()`, allowing preflight warnings to reach the UI log stream.
- `extract()` ([src/extraction/text_extractor.py:76-83](src/extraction/text_extractor.py:76)) emits a UI-visible "skipped — see startup log for reason" message instead of silently returning empty results.
- `README.md:30` and `setup.sh:45,59` corrected from the wrong `medgemma:27b-q8_0` → the actual `jwang580/medgemma_27b_q8_0` (Hugging Face community variant).
- Pulled the model: 28.7 GB now installed via `ollama pull jwang580/medgemma_27b_q8_0`.

**Why the preflight pattern matters:** A generic "is the daemon up?" check that swallows specific errors converts one fixable startup error into N silent per-call failures. Preflights must verify the actual capability, not just the transport.

---

### 2. Fixed: Lab Dashboard Showing Wrong "Latest" + Sparkline Collapse

**Files:** `src/ui/app.py`, `src/ui/static/js/bodymap3d.js`

**Symptom (user's words):** "I'm seeing multiple low vitamin d for one time period and I feel it's not analyzing data correctly."

**Root cause:** Field-name asymmetry. The Pydantic `LabResult` model ([src/models.py:140-153](src/models.py:140)) uses `test_date`, but three rendering call sites read `lab.get("date")` or `lab.get("collected_date")`. With both missing, fallback returned `""` — so:
- `_get_latest_labs` sorted on empty strings → "latest" was actually arbitrary order (often the oldest)
- `_get_lab_trends` returned points all with empty date → D3's `scaleTime` collapsed them to a single x position, making 3 different Vitamin D values look like 3 alerts at "one time period"

**Fix (three call sites, same pattern):**
- [src/ui/app.py:1532-1547](src/ui/app.py:1532) `_get_latest_labs` — added `lab.get("test_date")` as primary, kept legacy fallbacks
- [src/ui/app.py:1564-1601](src/ui/app.py:1564) `_get_lab_trends` — same precedence + `if not date: continue` to drop undated points before they hit the time scale
- [src/ui/static/js/bodymap3d.js:3635](src/ui/static/js/bodymap3d.js:3635) — body-map labs panel, same precedence

**Why this is a class of bug worth recognizing:** Field-name asymmetry between the canonical data model and the rendering layer is a high-risk pattern because the empty-string fallback succeeds silently on the JSON layer but breaks visualization downstream. Charts using `scaleTime` collapse on `Invalid Date`; sort comparators with `""` produce unstable ordering.

---

## Deferred for Next Session (User-Approved)

### Implement Labs-tab Grouping by Lab Name

**Why deferred:** Out of context budget — user said "Yes on the recommendation but let's do a hand off doc and update pinecone we're running out of context."

**The problem:** The Labs tab still shows every historical measurement as a separate row. A patient with chronically low Vitamin D appears as multiple "LOW" alerts instead of one lab with a trend.

**The plan:**
1. In [src/ui/static/app.js](src/ui/static/app.js) (`renderLabs` area, ~line 1075-1339), group entries by `test_name` before rendering the grid.
2. Show one row per lab with: most recent value + status badge + trend arrow (compare to prior value) + inline sparkline (D3, reuse trends shape).
3. The per-lab "Recent History" expansion already exists at [src/ui/static/app.js:1313-1339](src/ui/static/app.js:1313) — surface historical readings via that existing infrastructure rather than building new UI.
4. Same fix benefits HbA1c, Fasting Glucose, Blood Pressure, and any other repeated-measurement lab.

**Files to touch:**
- `src/ui/static/app.js` — grouping + render changes
- Possibly `src/ui/app.py` `/api/labs` if backend grouping is preferred (currently flat list)

**Acceptance:** A patient with 3 Vitamin D readings shows ONE row in the Labs grid with "Latest: 35 ng/mL Normal ↑ from 28 (4mo)" and a sparkline; clicking expands to see all 3 measurements.

---

## Prior Session — 2026-03-13 (kept for reference)

### 1. Fixed: sqlite-vec Loading on macOS
**File:** `src/database.py`

macOS ships Python's sqlite3 without `SQLITE_ENABLE_LOAD_EXTENSION`. Changed the sqlite-vec loading to use `apsw` (which supports extensions) instead of the built-in sqlite3 module. Falls back gracefully if neither works.

**Status:** `apsw` needs to be installed: `pip install apsw`

---

### 2. Fixed: Duplicate File Processing on Re-upload
**File:** `src/ui/app.py` (line ~793)

Each upload prepended a random UUID to the filename, so re-uploading the same file created duplicates. The uploads folder was never cleared between sessions.

**Fix:** The `/api/upload` endpoint now clears the uploads folder before saving new files. Also filters out `.DS_Store` from the analyze glob.

---

### 3. Fixed: MedGemma JSON Truncation
**File:** `src/extraction/text_extractor.py`

MedGemma was returning truncated/invalid JSON because:
- Chunks were too large (was 24K chars, now `MAX_CHUNK_CHARS = 12000`)
- Output token budget was too small (was 4096, now `num_predict: 16384`)

---

### 4. IN PROGRESS: Removed 50-Page Cap + Added Incremental Dashboard Updates

This is the big change. The tool was capping extraction at 50 of 7,278 pages, which defeated its entire purpose.

**Files changed:**

#### `src/ui/pipeline.py`
- `MEDPREP_MAX_PAGES` default changed from `"50"` to `"0"` (0 = no limit)
- Cap conditional now only applies when `MAX_PAGES_PER_FILE > 0`
- Added time estimate logging for large documents
- Added `profile_update_callback` parameter to `Pipeline.__init__()`
- Added `_publish_profile_snapshot()` method — serializes profile and pushes to UI after each chunk
- **Removed** the post-extraction `_merge_extraction_results()` call — merging now happens per-chunk via `_on_chunk_complete` callback
- Added `_on_chunk_complete` closure in `_pass_1a_text_extraction` that merges each chunk's Pydantic model instances directly into `self._profile.clinical_timeline`

#### `src/extraction/text_extractor.py`
- Added `on_chunk_complete` parameter to `TextExtractor.__init__()`
- After each chunk is processed and merged into the internal `results` accumulator, computes a delta (only newly added items) and fires the callback
- Delta contains Pydantic model instances (already cleaned/validated by `_merge_results`), not raw dicts

#### `src/ui/app.py`
- `_run_pipeline()` now creates a `profile_update_callback` that sets `_profile_data` to the latest snapshot
- This means dashboard API endpoints return real data as chunks complete, not just at the end

#### `src/ui/static/app.js`
- SSE handler now listens for `"profile_updated"` events
- When received, calls `App.loadAllData()` to refresh the dashboard
- This means the UI auto-refreshes every time a MedGemma chunk finishes (~6 min intervals)

---

## What Still Needs Testing

1. **Run a full analysis with the cap removed** — verify the incremental updates work (dashboard populates as chunks complete)
2. **Memory usage over long runs** — 7,278 pages will take ~17 hours. Monitor that `model_dump(mode="json")` snapshots don't cause memory issues as the profile grows
3. **Thread safety** — `_profile_data` is replaced atomically (full dict swap, not in-place mutation). CPython's GIL makes this safe, but watch for edge cases where user-initiated POST endpoints mutate `_profile_data` while the pipeline is also replacing it

## Known Issues Still Open

- **Presidio not installed** — PII redaction won't work. Must be installed before enabling Gemini API keys: `pip install presidio-analyzer presidio-anonymizer`
- **No Gemini API key** — Passes 2-4 (cloud analysis) are skipped
- **No UMLS API key** — Terminology validation returns empty results
- **Vault passphrase mismatch** — `VAULT_PASSPHRASE` env var doesn't match the existing vault. User's API keys may be locked inside
- **PII in logs** — Patient name, MRN, DOB, and address appear in MedGemma text preview logs. Not a problem for local-only processing but would be an issue with cloud APIs enabled

## Processing Time Estimates

At current speed (~6 min/chunk, ~7 pages/chunk):

| Pages | Chunks | Time |
|-------|--------|------|
| 50 | 7 | ~40 min |
| 500 | ~70 | ~7 hours |
| 7,278 | ~1,040 | ~17-18 hours |

The `caffeinate` call already prevents macOS sleep during analysis.

## Environment

- **Hardware:** Mac Mini M4 Pro, 64GB unified memory
- **Model:** MedGemma 27B Q8 (`jwang580/medgemma_27b_q8_0`) via Ollama
- **Python:** venv at `/Users/owner/Desktop/Tech Tools/MedPrep/venv/`
- **Data:** `/Users/owner/Desktop/Tech Tools/MedPrep/data/`

## Key File Locations

- Pipeline orchestrator: `src/ui/pipeline.py`
- MedGemma extractor: `src/extraction/text_extractor.py`
- Flask app: `src/ui/app.py`
- Frontend: `src/ui/static/app.js`
- Data models: `src/models.py`
- Design doc: `/Users/owner/docs/plans/2026-02-24-ck-plan-design.md`
