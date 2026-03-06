# Clinical Intelligence Hub

An open-source, local-first medical records analysis tool that transforms decades of patient records into actionable clinical intelligence.

## What It Does

Drop your medical records (PDFs, DICOM images, FHIR data, genetic tests) and the Hub:

1. **Extracts** clinical data using local AI models (MedGemma 27B/4B)
2. **Detects** findings in medical images (MONAI pre-trained models)
3. **Redacts** personal information before any cloud processing
4. **Analyzes** patterns across 29 medical specialties + 7 adjacent domains
5. **Validates** against 26 clinical databases (FDA, DrugBank, PubMed, ClinVar, OMIM, PharmGKB, and 20 more)
6. **Generates** a 10-section report with provenance-traced citations
7. **Monitors** for new research, drug alerts, and guideline changes

## How to Use It

### Setup

```bash
# 1. Clone or download the repository
git clone https://github.com/arturo-natella/clinical-intelligence-hub.git
cd clinical-intelligence-hub

# 2. Run the setup script (creates venv, installs dependencies, checks for Ollama)
chmod +x setup.sh && ./setup.sh

# 3. Install the local AI models via Ollama
ollama pull medgemma:27b-q8_0   # ~28GB — primary text extraction
ollama pull medgemma:4b          # ~4GB  — vision analysis
```

### Running the App

```bash
# Double-click start.command in Finder, or:
./start.command
```

1. The terminal will prompt for a **vault passphrase** — this encrypts all patient data on disk.
   - First run: choose any passphrase (it creates a new vault).
   - Subsequent runs: enter the same passphrase to decrypt your data.
2. Your browser opens to `http://127.0.0.1:5050`.

### Processing Records

1. From the **Dashboard**, drag and drop your medical files into the upload zone.
   - Accepted formats: PDF, DICOM (.dcm), FHIR JSON bundles, images (JPEG/PNG), genetic test reports.
2. The pipeline runs automatically in 7 passes:
   - **Pass 0** — File classification, OCR, deduplication
   - **Pass 1a** — MedGemma 27B text extraction (local)
   - **Pass 1b** — MedGemma 4B vision analysis (local)
   - **Pass 1c** — MONAI medical image detection (local)
   - **Pass 1.5** — PII redaction (Presidio)
   - **Pass 2** — Gemini cloud analysis (on redacted data only)
   - **Pass 3–4** — Deep Research pattern detection
   - **Pass 5** — 26-source clinical validation
   - **Pass 6** — Report generation
3. Progress updates stream in real-time via SSE on the Dashboard.

### Navigating the App

Use the sidebar to switch between views:

| View | What It Shows |
|------|---------------|
| **Dashboard** | Patient overview: risk score, medication count, conditions, flags, lab trends, overdue tests |
| **Body Map** | 3D interactive anatomy model (Z-Anatomy, 2,749 muscle meshes) with 6 dissection layers, HDR lighting, SSAO, and clinical findings pinned to body regions. ⚠️ *Under active development — see [CHANGELOG](CHANGELOG.md).* |
| **Timeline** | D3.js swim-lane visualization of your medical history — medications, diagnoses, labs, procedures, imaging, symptoms — with zoom and brush navigation |
| **Medications** | Active medications, drug-drug interactions, pharmacogenomic alerts |
| **Labs** | Lab results table with flagged values and trends over time |
| **Imaging** | Medical imaging studies with MONAI detection findings |
| **Symptoms** | Symptom tracking and episode analysis |
| **Environment** | Environmental health risk factors |
| **Health Tracker** | Log vitals (BP, heart rate, glucose, weight, temperature, O2 sat, A1C), view sparkline trends, and a composite risk score breakdown |
| **Genetics** | Genetic markers with pharmacogenomic significance |
| **Flags** | All clinical findings sorted by severity (critical/high/moderate/low) with evidence cards |
| **Cross-Disciplinary** | Force-directed graph showing connections between findings across specialties — what individual doctors miss |
| **Community** | Reddit community pattern detection (clearly labeled as anecdotal, unverified) |
| **Alerts** | Monitoring alerts from daily/weekly checks for new research and drug safety updates |
| **Report** | Generate and download a Word document report with provenance-traced citations |

### Chat

The embedded **Clinical Assistant** (bottom-right of Dashboard) lets you ask questions about your records using RAG retrieval over your data.

### Settings

Click the gear icon in the sidebar to configure your Google API key (needed for Gemini analysis and Deep Research).

## Key Features in Detail

### 3D Anatomy Viewer

Interactive Three.js body map with 6 dissection layers (skin, muscle, fascia, skeleton, vasculature, nerves) plus on-demand organ loading. Features HDR environment lighting, SSAO contact shadows, bloom post-processing, and PBR materials per tissue type. Clinical findings are pinned to anatomical regions. Click any region to zoom in, view findings, and see AI-generated explanations of what they mean in plain English. Toggle between your findings and a healthy baseline with "Show Healthy / Show My State."

> **Status (March 2026):** The Body Map is under active development. We're aware of visual and interaction issues and are shipping fixes rapidly — see [CHANGELOG.md](CHANGELOG.md) for the latest. A dedicated female anatomy model is planned. If you have suggestions or encounter bugs, email **arturo@goamaru.com**.

### 26-Source Clinical Validation

Every finding is cross-checked against independent medical databases:

- **Drug & Pharmacology (7)**: OpenFDA, DrugBank, RxNorm, DailyMed, DDinter, PharmGKB, PubChem
- **Literature & Evidence (2)**: PubMed (E-utilities), ClinicalTrials.gov
- **Genetics & Genomics (5)**: ClinVar, dbSNP, gnomAD, OMIM, DisGeNET
- **Ontology & Terminology (6)**: SNOMED CT, ICD-11, MeSH, HPO, LOINC, UMLS
- **Rare Disease (2)**: Orphanet, GARD
- **Molecular & Network (3)**: BioGRID, Open Targets, UniProt
- **Side Effects (1)**: SIDER

### Continuous Monitoring

After initial analysis, the Hub checks for updates relevant to your profile:

- **Daily** (6 AM): PubMed, OpenFDA, ClinVar, RxNorm, ClinicalTrials.gov, PharmGKB
- **Weekly** (Sunday 3 AM): ADA, AHA, USPSTF guideline pages via Playwright

Alerts are filtered by relevance to your conditions and medications, then sorted by severity.

### Snowball Differential Diagnostician

Graph-theory differential diagnosis engine with a 20-condition knowledge base. Seeds patient findings, matches against condition patterns, expands related conditions, ranks by confidence, and builds a D3.js force-directed visualization. Click any condition node to see matched/missing findings and suggested tests.

## Privacy & Security

- **Local-first AI**: MedGemma and MONAI run entirely on your machine via Ollama. No patient data is sent to external services for extraction or detection.
- **Encryption at rest**: AES-256-GCM with Argon2id key derivation (OWASP parameters: time=3, memory=64MB, parallelism=4). All patient data stored in `.enc` files.
- **PII redaction**: Microsoft Presidio strips names, dates, MRNs, SSNs, and other identifiers before any cloud API call (Gemini). Custom medical recognizers + regex fallback.
- **Redaction audit log**: Every redaction is logged to SQLite for provenance.
- **XSS protection**: All user-facing text rendered via `escapeHtml()` and DOM-based insertion. No raw `innerHTML` with user content.

## Requirements

### Hardware

- **macOS** (Apple Silicon — M4 Pro recommended)
- **64GB unified memory** minimum (MedGemma 27B Q8 uses ~28GB during inference)
- ~40GB disk space for models

### Software

| Dependency | Version | Purpose |
|-----------|---------|---------|
| Python | 3.12+ | Runtime |
| Ollama | Latest | Local model inference (MedGemma 27B/4B) |
| Tesseract | Optional | OCR fallback (Apple Vision is primary) |
| Google API key | — | Gemini 3.1 Pro analysis + Deep Research |

### Python Dependencies

| Package | Purpose |
|---------|---------|
| Flask 3.0+ | Web application server |
| Pydantic 2.5+ | Data models with clinical provenance |
| google-genai 1.0+ | Gemini 3.1 Pro + Deep Research |
| ollama 0.4+ | Local model inference |
| monai 1.3+ / torch 2.2+ | Medical image detection (MONAI pre-trained models) |
| PyMuPDF 1.24+ | PDF text extraction |
| python-docx 1.1+ | Word document report generation |
| pydicom 2.4+ | DICOM medical image parsing |
| fhir.resources 7.0+ | FHIR JSON bundle parsing |
| cryptography 42.0+ | AES-256-GCM encryption |
| argon2-cffi 23.1+ | Argon2id key derivation |
| presidio-analyzer/anonymizer 2.2+ | PII redaction |
| sqlite-vec 0.1+ | Vector search for RAG |
| playwright 1.40+ | Guideline monitoring via browser automation |
| pyobjc-framework-Vision 10.0+ | Apple Vision OCR (macOS native) |

### Optional Standardization Databases

Full-size databases can be downloaded for higher accuracy (the tool includes curated seed databases as fallback):

- **LOINC** (~90K codes): https://loinc.org/downloads/
- **SNOMED CT** (~300K concepts): https://www.nlm.nih.gov/healthit/snomedct/
- **RxNorm** (~100K terms): https://www.nlm.nih.gov/research/umls/rxnorm/

All require free NLM UMLS registration at https://uts.nlm.nih.gov/uts/

## Architecture

```
src/
├── analysis/           # AI analysis engines
│   ├── cross_disciplinary.py    # 29-specialty + 7-domain analysis
│   ├── deep_research.py         # Gemini Deep Research integration
│   ├── snowball_engine.py       # Differential diagnosis graph engine
│   ├── symptom_analytics.py     # Symptom pattern analysis
│   ├── visit_prep.py            # Doctor visit preparation
│   └── diagnostic_engine/       # Cross-specialty + pharmacogenomics
├── extraction/         # Data ingestion (PDF, DICOM, FHIR, images)
│   ├── preprocessor.py          # File classification + deduplication
│   ├── text_extractor.py        # MedGemma 27B text extraction
│   ├── ocr.py                   # Apple Vision + Tesseract OCR
│   ├── fhir_parser.py           # FHIR Bundle parsing
│   └── dicom_converter.py       # DICOM metadata + PNG conversion
├── imaging/            # Medical image analysis
│   ├── monai_detector.py        # MONAI pre-trained model inference
│   ├── model_manager.py         # Sequential model load/unload
│   ├── vision_analyzer.py       # MedGemma 4B image analysis
│   └── volumetric_renderer.py   # DICOM → MONAI → GLB 3D export
├── privacy/            # PII redaction
│   └── redactor.py              # Microsoft Presidio + regex
├── validation/         # 26 independent API clients
│   ├── validator.py             # Orchestrator (14 validation steps)
│   ├── _http.py                 # Shared HTTP with certifi SSL
│   ├── openfda.py, drugbank.py, rxnorm.py, ...  # Individual clients
│   └── (26 source modules)
├── standardization/    # Medical terminology mapping
│   ├── loinc.py, snomed.py, rxnorm_db.py
├── monitoring/         # Continuous alerting
│   ├── api_monitors/            # Daily: PubMed, FDA, ClinVar, etc.
│   ├── playwright_monitors/     # Weekly: ADA, AHA, USPSTF
│   └── scheduler.py             # Monitoring scheduler
├── report/             # Word document generation
│   └── builder.py               # 10-section report with provenance
├── ui/                 # Flask web application
│   ├── app.py                   # Routes + API endpoints
│   ├── pipeline.py              # Processing pipeline orchestration
│   └── static/                  # Frontend (HTML, CSS, JS, D3.js)
├── database.py         # SQLite WAL-mode + sqlite-vec
├── encryption.py       # AES-256-GCM vault
└── models.py           # Pydantic V2 data models
```

## Quick Start

```bash
chmod +x setup.sh && ./setup.sh
# Then double-click start.command
```

## License

BSD 2-Clause — see [LICENSE](LICENSE).

## Disclaimer

This tool is for **informational purposes only**. It is NOT a medical device, does NOT provide diagnoses, and does NOT replace professional medical advice. Always consult qualified healthcare providers for medical decisions. AI-generated findings may contain errors and must be verified by a licensed physician.
