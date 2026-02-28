"""
Clinical Intelligence Hub — Pass 2: Gemini 3.1 Pro Preview Fallback

When local MedGemma cannot extract sufficient data from a document
(poor OCR, unusual formatting, complex clinical narratives), we fall
back to Gemini 3.1 Pro Preview for cloud-based extraction.

Security model:
  - PII redaction (Pass 1.5) is ALWAYS applied before sending to Gemini
  - Only redacted text is transmitted
  - API key stored in encrypted vault (AES-256-GCM)

Model: gemini-3.1-pro-preview (NOT gemini-1.5-pro — the old prototype
used the wrong model everywhere)
"""

import json
import logging
from typing import Optional

from src.models import (
    Allergy,
    ClinicalNote,
    Diagnosis,
    GeneticVariant,
    LabResult,
    Medication,
    MedicationStatus,
    Procedure,
    Provenance,
)

logger = logging.getLogger("CIH-Gemini")

# Correct model ID — NOT gemini-1.5-pro
MODEL_ID = "gemini-3.1-pro-preview"


class GeminiFallback:
    """
    Pass 2: Cloud fallback extraction using Gemini 3.1 Pro Preview.

    Called when local extraction (MedGemma) produces insufficient results
    or when document complexity exceeds local model capabilities.
    """

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._client = None
        self._model = None
        self._setup_client()

    def extract(self, redacted_text: str, source_file: str,
                local_results: dict = None) -> dict:
        """
        Extract clinical data from PII-redacted text using Gemini.

        Args:
            redacted_text: Text with PII already stripped
            source_file: Original filename for provenance
            local_results: Previous MedGemma results (for gap-filling)

        Returns:
            dict with clinical data lists (same format as TextExtractor)
        """
        if not self._client:
            logger.error("Gemini client not initialized")
            return {}

        prompt = self._build_extraction_prompt(redacted_text, local_results)

        try:
            response = self._model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.0,
                    "max_output_tokens": 8192,
                    "response_mime_type": "application/json",
                },
            )

            result = json.loads(response.text)
            return self._parse_results(result, source_file)

        except json.JSONDecodeError as e:
            logger.warning(f"Gemini returned invalid JSON: {e}")
            return {}
        except Exception as e:
            logger.error(f"Gemini extraction failed: {e}")
            return {}

    def analyze_complex_document(self, redacted_text: str,
                                 source_file: str) -> Optional[str]:
        """
        For documents that resist structured extraction (complex narratives,
        multi-provider notes, etc.), get a structured clinical summary.
        """
        if not self._client:
            return None

        prompt = f"""You are a clinical data analyst reviewing a medical document.
This text has been PII-redacted for privacy.

Provide a structured clinical summary covering:
1. Key diagnoses and conditions mentioned
2. Medications and dosages
3. Lab results and vital signs
4. Procedures performed or planned
5. Provider recommendations
6. Any follow-up actions needed

Be thorough — extract every clinical detail, no matter how minor.
Flag any concerning findings or potential interactions.

PII-Redacted Document:
\"\"\"{redacted_text}\"\"\"

Provide your analysis as a detailed clinical summary."""

        try:
            response = self._model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.1,
                    "max_output_tokens": 4096,
                },
            )
            return response.text

        except Exception as e:
            logger.error(f"Gemini complex analysis failed: {e}")
            return None

    # ── Setup ───────────────────────────────────────────────

    def _setup_client(self):
        """Initialize the Gemini API client."""
        try:
            import google.generativeai as genai

            genai.configure(api_key=self._api_key)
            self._client = genai
            self._model = genai.GenerativeModel(MODEL_ID)
            logger.info(f"Gemini client initialized with model: {MODEL_ID}")

        except ImportError:
            logger.error(
                "google-generativeai not installed. "
                "Run: pip install google-generativeai"
            )
        except Exception as e:
            logger.error(f"Failed to initialize Gemini: {e}")

    # ── Prompt Building ─────────────────────────────────────

    def _build_extraction_prompt(self, redacted_text: str,
                                 local_results: dict = None) -> str:
        """Build the Gemini extraction prompt, optionally gap-filling."""
        gap_context = ""
        if local_results:
            # Tell Gemini what we already found so it can focus on gaps
            found = []
            for key, items in local_results.items():
                if items:
                    found.append(f"  - {key}: {len(items)} items already extracted")
            if found:
                gap_context = (
                    "\n\nThe local AI has already extracted the following. "
                    "Focus on anything it MISSED:\n"
                    + "\n".join(found)
                )

        return f"""You are an expert clinical data extractor. Extract ALL clinical
entities from this PII-redacted medical document into strict JSON.
{gap_context}

Extract these categories:
1. **medications** — name, generic_name, dosage, frequency, route, status (active/discontinued/prn), reason
2. **labs** — name, value (numeric), value_text (non-numeric), unit, flag (High/Low/Normal/Critical), test_date (YYYY-MM-DD)
3. **diagnoses** — name, date_diagnosed (YYYY-MM-DD), status (Active/Resolved/Chronic)
4. **procedures** — name, procedure_date (YYYY-MM-DD), outcome
5. **allergies** — allergen, reaction, severity (Mild/Moderate/Severe/Life-threatening)
6. **genetics** — gene, variant, phenotype, clinical_significance, implications
7. **notes** — note_type (visit_summary/referral/patient_log/provider_note), summary, provider, note_date (YYYY-MM-DD)

Rules:
- Extract EVERY clinical entity, no matter how minor
- Use null for fields you cannot determine
- Dates in YYYY-MM-DD format
- Do NOT invent data
- Note: PII has been redacted ([NAME_REDACTED], [DOB_REDACTED], etc.) — ignore these placeholders

PII-Redacted Medical Record:
\"\"\"{redacted_text}\"\"\"

Output strictly valid JSON with the 7 keys above."""

    # ── Result Parsing ──────────────────────────────────────

    def _parse_results(self, result: dict, source_file: str) -> dict:
        """Parse Gemini JSON output into Pydantic models."""
        from src.extraction.text_extractor import TextExtractor

        # Reuse TextExtractor's merge logic
        extractor = TextExtractor.__new__(TextExtractor)
        results = {
            "medications": [], "labs": [], "diagnoses": [],
            "procedures": [], "allergies": [], "genetics": [], "notes": [],
        }

        # Override provenance to show Gemini as source
        extractor._merge_results(results, result, source_file, None)

        # Fix provenance to indicate Gemini model
        for category in results.values():
            for item in category:
                if hasattr(item, 'provenance'):
                    item.provenance.extraction_model = "gemini-3.1-pro-preview"

        return results
