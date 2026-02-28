# Changelog

All notable changes to the Clinical Intelligence Hub will be documented in this file.

## [1.0.0] — 2026-02-27

### Added

#### Phase 0: Foundation
- Project structure, governance files (BSD 2-Clause license), dependency manifest
- `setup.sh` one-command environment setup (venv, Playwright, Ollama, Tesseract checks)
- `start.command` double-click launcher with caffeinate and passphrase prompt
- `.gitignore` for medical data protection

#### Phase 1: Data Layer
- Pydantic V2 models with clinical provenance on every data type
- SQLite WAL-mode database with sqlite-vec vector storage
- AES-256-GCM encryption with Argon2id key derivation (EncryptedVault)
- Processing state checkpointing for crash recovery

#### Phase 2: Preprocessing (Pass 0)
- File classification (PDF, DICOM, FHIR JSON, images)
- Dual OCR: Apple Vision framework primary, Tesseract fallback
- SHA-256 deduplication
- FHIR Bundle parsing via fhir.resources
- DICOM metadata extraction and PNG conversion

#### Phase 3: Local Extraction (Passes 1a, 1b, 1c)
- MedGemma 27B text extraction (Pass 1a) via Ollama with keep_alive: "0"
- MedGemma 4B vision analysis (Pass 1b) for clinical images
- MONAI detection (Pass 1c) — lung nodule, whole body CT, brain tumor, cardiac, pancreas, pathology nuclei
- Sequential model load/unload with memory tracking (ModelManager)

#### Phase 4: Privacy (Pass 1.5)
- Microsoft Presidio PII redaction with custom medical recognizers
- Regex fallback for MRNs, patient IDs, SSNs
- Redaction audit log to SQLite

#### Phase 5: Cloud Analysis (Passes 2, 3, 4)
- Gemini 3.1 Pro Preview fallback extraction (Pass 2)
- Deep Research pattern detection and literature search (Passes 3-4)
- 29-specialty + 7-domain cross-disciplinary analysis
- Reddit community insights (clearly labeled as unverified anecdotal reports)
- PII redaction enforced before every cloud API call

#### Phase 6: Clinical Validation (Pass 5)
- OpenFDA adverse events and drug recalls
- DrugBank drug-drug interaction checking
- PubMed E-utilities literature search
- RxNorm medication standardization and interaction API
- Full standardization databases: LOINC (~90K), SNOMED CT (~300K), RxNorm (~100K) with curated seed fallbacks

#### Phase 7: Report Generation (Pass 6)
- 10-section Word document with clinical provenance
- Patient Summary, Health Timeline, Active Conditions/Meds, Lab Trends, Imaging Analysis
- Genetic Profile, Patterns/Flags, Cross-Disciplinary Insights, Questions for Doctor
- Disclaimer and Sources/Methods with PII redaction summary
- Every finding footnoted with source file, page number, and date

#### Phase 8: Clinical Intelligence Hub UI
- Single-page Flask application with 13 views
- Dashboard with patient overview, drop zone, progress bar (SSE)
- 3D Interactive Anatomy Viewer with 4 dissection layers and 8 clickable body regions
- Timeline explorer with type filters
- Medication tracker with drug interaction alerts
- Lab trends table with flagged results
- Imaging studies with MONAI findings
- Genetics table with pharmacogenomic significance
- Patterns and flags with severity-sorted evidence cards
- Cross-disciplinary connections view
- Community insights with unverified warning styling
- RAG clinical assistant chat (sqlite-vec backed)
- Monitoring alerts display
- Report generation and download
- Settings overlay for API key management
- XSS protection via escapeHtml() and DOM-based rendering

#### Phase 9: Continuous Monitoring
- 6 daily API monitors: PubMed, OpenFDA, ClinVar, RxNorm, ClinicalTrials.gov, PharmGKB
- Weekly Playwright monitors: ADA, AHA, USPSTF guideline pages
- Relevance assessor filters alerts against patient profile
- Severity-sorted output with addendum generation for critical/high alerts
- MonitoringScheduler with error isolation per source and CLI entry point

#### Phase 10: Polish
- launchd plists for automated monitoring (daily API at 6 AM, weekly Playwright Sunday 3 AM)
- install_monitors.sh with macOS Keychain passphrase storage
- End-to-end test suite covering all phases
- Full module import chain verification (36 modules)

### Removed
- Gemini prototype code (archived in git history at commit ca7f040)
