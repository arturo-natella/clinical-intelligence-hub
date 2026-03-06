# Changelog

All notable changes to the Clinical Intelligence Hub will be documented in this file.

## [2.2.0] — 2026-03-06

### Added

#### Renderer Upgrade — Production-Level 3D Rendering
- HDR studio environment (Poly Haven studio_small_08, CC0, 2K) via RGBELoader + PMREMGenerator
- EffectComposer post-processing pipeline: RenderPass → SSAO → UnrealBloom → OutputPass
- SSAO contact shadows (kernelRadius 0.5) — visible between ribs, organ boundaries, joint surfaces
- Subtle bloom (strength 0.15, threshold 0.85) — specular highlight glow on wet tissue surfaces
- Per-tissue HDR env map reflections: skin 0.5, muscle 0.4, skeleton 0.35, vasculature 0.6, nerves 0.3, organs 0.45

### Changed

#### Material Upgrades
- Muscles: MeshStandardMaterial → MeshPhysicalMaterial with clearcoat (0.08) + sheen (0.25) for wet muscle appearance
- Organs: MeshStandardMaterial → MeshPhysicalMaterial with clearcoat (0.08) for moist organ surfaces
- Skeleton: roughness 0.55 → 0.5, clearcoat 0.1 → 0.12 — waxy porcelain bone surface
- Vasculature: roughness lowered, clearcoat raised — wet taut membrane appearance
- Nerves: clearcoat 0.08 → 0.1 — myelin sheath subtle sheen

### Fixed
- Muscles + organs no longer bypass ACES Filmic tone mapping (removed `toneMapped: false`)
- All materials now receive HDR env reflections (removed `envMapIntensity: 0.0` overrides)
- Muscle base colors bumped ~10% to compensate for ACES tone mapping darkening

---

## [2.1.0] — 2026-03-03

### Added

#### 3D Anatomy Viewer — Z-Anatomy Integration (Body Map)
- Full Z-Anatomy model support (CC BY-SA 4.0): 11,356 meshes, Draco compressed, 28.5MB GLB
- 6 dissection layers (was 4): Skin, Muscle, Skeleton, Organs, Vasculature, Nervous system
- Blender export pipeline (`export_zanatomy.py`): Z-Anatomy `.blend` → name-prefixed, color-coded GLB
- Name-prefix layer system (SKEL__, MUSC__, ORGN__, VASC__, NERV__, SKIN__) for reliable JS parsing
- 3-point studio lighting (hemisphere + key + fill + rim) for realistic skin rendering
- Gender toggle (♂/♀) with model fallback cascade: full → basic → male fallback → placeholder
- Gender-aware organ filtering (hides opposite-sex organs client-side)
- Zoom in/out toolbar buttons
- ResizeObserver for SPA visibility changes (fixes canvas sizing when section first becomes visible)

### Fixed

#### Body Map Rendering
- Z-Anatomy text labels (FONT objects converted to meshes by GLTF exporter) no longer render as floating 3D text. Two-layer defense: regex glyph filter + geometric flatness filter for unprefixed meshes.
- Model centering: fixed double-counting bug where world-space bounding box included prior offset, causing body to shift right. Wrapper position now reset before computing center.
- Toolbar wraps on smaller viewports (`flex-wrap`)

### Known Issues
- **Z-Anatomy text labels in 3D model**: The Z-Anatomy source data contains 3D font objects (region labels like "BRACHIAL REGION", "MUSCLES OF THORAX") that get converted to meshes by Blender's GLTF exporter. These are filtered out at runtime by a two-layer system (regex + flatness heuristic), but the filter is heuristic — some edge cases may slip through on future Z-Anatomy updates. If unexpected floating text appears, check the glyph detection logic in `bodymap3d.js`.
- **Female model GLB not yet generated**: The gender toggle infrastructure is complete (UI, JS loader, organ filtering), but the female-specific GLB has not been exported yet. When female is selected, it falls back to the male model with female organ filtering applied client-side.
- **WebGL screenshots**: `preview_screenshot` cannot capture the Three.js canvas (shows blank). Must test in actual browser.

## [2.0.0] — 2026-03-02

### Added

#### 26-Source Clinical Validation Pipeline (was 4)
- Expanded from 4 validation sources to 26 independent API clients, each in its own module under `src/validation/`
- Shared HTTP utility (`_http.py`) with certifi SSL for macOS Python compatibility
- **Drug & Pharmacology (7)**: OpenFDA, DrugBank, RxNorm, DailyMed, DDinter, PharmGKB, PubChem
- **Literature & Evidence (2)**: PubMed (E-utilities), ClinicalTrials.gov
- **Genetics & Genomics (5)**: ClinVar, dbSNP, gnomAD, OMIM, DisGeNET
- **Ontology & Terminology (6)**: SNOMED CT, ICD-11, MeSH, HPO, LOINC, UMLS
- **Rare Disease (2)**: Orphanet, GARD
- **Molecular & Network (3)**: BioGRID, Open Targets, UniProt
- **Side Effects (1)**: SIDER (dual mode: local TSV + API)
- MIMIC-IV placeholder module (awaiting PhysioNet credentialing)

#### Validator Orchestrator Expansion
- `validator.py` now runs 14 validation steps (was 7) across all 26 sources
- New result keys: `drug_labels`, `interaction_severity`, `pharmacogenomics`, `mechanisms`, `genetic_variants`, `disease_network`, `cross_vocabulary`
- 7 new enrichment methods: drug label analysis, interaction severity scoring, pharmacogenomics profiling, mechanism-of-action mapping, genetic variant analysis, disease network construction, cross-vocabulary resolution
- All clients use graceful degradation (return None/[] on failure, never crash the pipeline)

#### Cross-Disciplinary Connections Graph
- D3.js v7 force-directed network visualization showing how findings connect across medical specialties
- Node coloring by discipline, edge thickness by connection strength
- Zoom/pan/drag with collision detection

#### Flowing Timeline Visualization
- D3.js swim-lane timeline with 6 lanes: medication, diagnosis, lab, procedure, imaging, symptom
- Time axis with zoom (0.5x–20x) via `d3.zoom()`, mini-map with brush navigation via `d3.brushX()`
- Flow/List toggle preserving both visualization modes
- Safe DOM rendering (no innerHTML) — all user content via `textContent`

#### Health Tracker with Vitals Logging
- 8 vital types: blood pressure (sys/dia), heart rate, blood glucose, weight, temperature, oxygen saturation, A1C
- Full CRUD API: log entries with validation (type + range checks), delete, list with filters
- Trend sparklines per vital type (latest value, average, count)
- Risk Score Breakdown: factor-by-factor analysis (polypharmacy, drug interactions, critical/high/moderate flags, missing monitoring) with 0–100 composite score
- Encrypted vault persistence for all vitals data

#### PubMed Citation Verification
- Every validation finding now carries PubMed citation links
- UI badges showing verification source count per finding
- Citation tooltips with PMID, title, and journal

#### UI Enhancements
- GNOME/Adwaita dark theme design system with CSS custom properties
- Collapsible sidebar navigation replacing top tabs
- Dashboard diagnostic command center with analytics grid
- Environmental health risks as dedicated nav tab
- Embedded chat panel in dashboard

### Changed
- Validation pipeline completely rewritten from monolithic to modular architecture
- Each data source is an independent client class with consistent interface
- Timeline view upgraded from flat list to interactive D3 swim-lane chart

## [1.2.0] — 2026-02-28

### Added

#### Snowball Differential Diagnostician
- `src/analysis/snowball_engine.py`: Graph-theory differential diagnosis engine with 20-condition knowledge base (cardiac, pulmonary, hepatic, endocrine, renal, hematologic, vascular, neurologic, autoimmune, infectious, GI, musculoskeletal)
- `src/ui/static/js/snowball.js`: D3.js v7 force-directed network visualization with zoom/pan/drag, ranked differentials sidebar, and per-condition detail panel
- `/api/snowball-diagnoses` POST endpoint in app.py
- Algorithm: seed patient findings → match against condition patterns → expand related conditions → rank by confidence → build D3-compatible graph
- Each condition scores by match ratio weighted by severity; contradicting evidence triggers rule-out (80% penalty)
- Click any condition node to see matched/missing findings, confidence bar, and "consider ordering" suggestions
- "Differential Dx" button in Body Map toolbar (amethyst accent)
- Full CSS for snowball overlay, graph, detail panel, ranked list, legend, and disclaimer

## [1.1.0] — 2026-02-28

### Added

#### Body Map Enhancements
- Before/After toggle: "Show Healthy" / "Show My State" button instantly switches between healthy baseline and patient's deformed organ state. Uses cached findings to avoid re-fetching.
- AI Body Translation panel: "What does this mean?" button on findings panel generates plain-English explanations of organ damage. Cascading provider: Gemini -> Ollama (MedGemma) -> static fallback. Includes suggested doctor questions.
- "Why Does This Hurt?" symptom mapping: 40+ condition-to-symptom lookup table correlates clinical findings (e.g. cirrhosis, heart failure) with patient-experienced symptoms (e.g. fatigue, shortness of breath). Shows in findings panel with source attribution.

#### Volumetric Renderer Pipeline
- `VolumetricRenderer` class in `src/imaging/volumetric_renderer.py`: DICOM -> MONAI segmentation -> marching cubes -> GLB export
- MPS (Apple Silicon) accelerated inference with aggressive memory management
- DICOM series validation (dimension consistency, slice sorting)
- Per-organ marching cubes with configurable step size (1=full, 2=fast)
- Trimesh-based GLB export with organ-layer naming for Three.js integration
- JSON metadata sidecar for scan provenance
- CLI entry point for standalone pipeline execution

#### Backend
- `/api/body-translation` endpoint: Generates patient-friendly organ explanations via Gemini, Ollama, or static fallback

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
