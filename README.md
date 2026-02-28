# Clinical Intelligence Hub

An open-source, local-first medical records analysis tool that transforms decades of patient records into actionable clinical intelligence.

## What It Does

Drop your medical records (PDFs, DICOM images, FHIR data, genetic tests) and the Hub:

1. **Extracts** clinical data using local AI models (MedGemma 27B/4B)
2. **Detects** findings in medical images (MONAI pre-trained models)
3. **Redacts** personal information before any cloud processing
4. **Analyzes** patterns across 29 medical specialties + 7 adjacent domains
5. **Validates** against FDA, DrugBank, PubMed, and clinical databases
6. **Generates** a 10-section report with provenance-traced citations
7. **Monitors** for new research, drug alerts, and guideline changes

## Key Features

- **Clinical Intelligence Dashboard** — Patient overview, monitoring alerts, quick actions
- **3D Anatomy Viewer** — Interactive body map with findings mapped to regions
- **Timeline Explorer** — Chronological view of all medical events
- **Cross-Disciplinary Connections** — What individual specialists miss
- **Lab Trends** — Values charted over time with threshold indicators
- **Medication Tracker** — Active meds, interactions, pharmacogenomic flags
- **Community Insights** — Reddit pattern detection (clearly labeled as anecdotal)
- **Clinical AI Chat** — Ask questions about your records
- **Continuous Monitoring** — Daily/weekly checks for relevant new findings

## Privacy First

- All AI extraction runs **locally** on your machine (MedGemma, MONAI)
- Patient data is **encrypted at rest** (AES-256-GCM + Argon2id)
- **PII is stripped** before any cloud API call (Microsoft Presidio)
- No data leaves your machine without redaction

## Requirements

- macOS (Apple Silicon — M4 Pro recommended)
- 64GB unified memory minimum
- Python 3.12+
- Ollama (for local model inference)
- Google API key (for Gemini 3.1 Pro + Deep Research)

## Quick Start

```bash
chmod +x setup.sh && ./setup.sh
# Then double-click start.command
```

## License

BSD 2-Clause — see [LICENSE](LICENSE).

## Disclaimer

This tool is for **informational purposes only**. It is NOT a medical device, does NOT provide diagnoses, and does NOT replace professional medical advice. Always consult qualified healthcare providers for medical decisions. AI-generated findings may contain errors and must be verified by a licensed physician.
