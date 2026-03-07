# Clinical Intelligence Hub — Development Standards

## Project Overview

Open-source, local-first medical records analysis tool. Ingests patient records (PDFs, DICOM, FHIR JSON, genetic tests) and produces a comprehensive clinical intelligence report through a 6-pass analysis pipeline.

**Target user:** Non-technical ~60-year-old managing complex medical history.
**Target hardware:** Mac Mini M4 Pro, 64GB unified memory, 2TB SSD.
**License:** BSD 2-Clause.

## Architecture

### 6-Pass Analysis Pipeline
- **Pass 0:** File classification, OCR (Apple Vision → Tesseract fallback), SHA-256 dedup, FHIR parsing
- **Pass 1a:** MedGemma 27B text extraction (local, Ollama)
- **Pass 1b:** MedGemma 4B medical image description (local, Ollama)
- **Pass 1c:** MONAI pre-trained model inference (local, PyTorch)
- **Pass 1.5:** PII redaction (Microsoft Presidio) — before ANY cloud API call
- **Pass 2:** Gemini 3.1 Pro Preview fallback extraction
- **Pass 3-4:** Gemini Deep Research (pattern detection, cross-disciplinary analysis, literature search)
- **Pass 5:** Clinical validation (OpenFDA, DrugBank, PubMed, RxNorm)
- **Pass 6:** 10-section Word document report with provenance

### Key Principles
1. **Clinical provenance on everything.** Every data model carries `source_file`, `source_page`, `date_extracted`, `confidence`.
2. **Sequential model loading.** Only one large model in memory at a time. Use `keep_alive: "0"` with Ollama. Call `gc.collect()` + `torch.mps.empty_cache()` between models. Peak memory must stay under 36GB.
3. **PII redaction before cloud.** Nothing with patient identifiers leaves the machine. Presidio runs before every Gemini/API call.
4. **Graceful degradation.** If a model/API fails, skip that pass and continue. Never crash the pipeline.
5. **State checkpointing.** SQLite tracks processing state. Pipeline resumes from last checkpoint after crash.

## Code Standards

### Models
- All data models in `src/models.py` using Pydantic V2
- Every clinical data type has provenance fields
- Use `model_validate()` not `parse_obj()`

### Database
- SQLite with WAL mode for concurrent reads
- sqlite-vec for vector storage (not ChromaDB)
- All patient data encrypted at rest (AES-256-GCM + Argon2id)

### API Calls
- Gemini model: `gemini-3.1-pro-preview` (NOT `gemini-1.5-pro`)
- Deep Research model: `gemini-deep-research-pro-preview-12-2025`
- All API keys stored in encrypted vault, never plaintext
- Rate limiting and retry with exponential backoff on all external calls

### Frontend
- Flask server with SSE for real-time progress
- Single-page app, dark mode, medical-grade aesthetic
- Designed for a non-technical 60-year-old — large text, no clutter

### Testing
- Tests in `tests/` directory
- Run with: `python -m pytest tests/`

## File Structure

```
src/
├── models.py              # Pydantic V2 data models
├── database.py            # SQLite + sqlite-vec
├── encryption.py          # AES-256-GCM vault
├── extraction/            # Pass 0, 1a: preprocessing + text extraction
├── imaging/               # Pass 1b, 1c: vision + MONAI
├── privacy/               # Pass 1.5: PII redaction
├── analysis/              # Pass 2-4: Gemini + Deep Research
├── validation/            # Pass 5: clinical database validation
├── standardization/       # LOINC, SNOMED CT, RxNorm lookups
├── monitoring/            # Continuous monitoring (daily/weekly)
├── report/                # Pass 6: Word document generation
└── ui/                    # Flask server + static frontend
```

## Design Doc

The authoritative specification is at: `/Users/owner/docs/plans/2026-02-24-ck-plan-design.md`
The rebuild plan is at: `/Users/owner/.Codex/plans/nested-leaping-goose.md`

## Community Data Labeling

Reddit community insights are clearly labeled as "Unverified Community Reports" in ALL outputs — code, UI, and reports. They are NOT clinical data. They are anecdotal signals useful for doctor discussion points.

## Cross-Disciplinary Analysis

The tool searches across 29 medical specialties + 7 adjacent domains for every patient finding. This is a core differentiator — it connects what siloed specialists miss.
