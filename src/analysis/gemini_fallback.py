"""
Clinical Intelligence Hub — Pass 2: Gemini 3 Flash Fallback

When local MedGemma cannot extract sufficient data from a document
(poor OCR, unusual formatting, complex clinical narratives), we fall
back to Gemini 3.1 Pro Preview for cloud-based extraction.

Security model:
  - PII redaction (Pass 1.5) is ALWAYS applied before sending to Gemini
  - Only redacted text is transmitted
  - API key stored in encrypted vault (AES-256-GCM)

Model: gemini-3-flash-preview
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
from src.analysis.gemini_config import (
    GEMINI_MODEL_ID,
    create_client,
    generate_content,
)

logger = logging.getLogger("CIH-Gemini")

# Backward-compatible export used by tests and provenance code.
MODEL_ID = GEMINI_MODEL_ID


class GeminiFallback:
    """
    Pass 2: Cloud fallback extraction using Gemini 3 Flash.

    Called when local extraction (MedGemma) produces insufficient results
    or when document complexity exceeds local model capabilities.
    """

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._client = None
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
            response = generate_content(
                self._client,
                prompt,
                temperature=0.0,
                max_output_tokens=8192,
                response_mime_type="application/json",
            )

            result = json.loads(response.text)
            return self._parse_results(result, source_file)

        except json.JSONDecodeError as e:
            logger.warning(
                "Gemini returned invalid JSON (error_type=%s)",
                type(e).__name__,
            )
            return {}
        except Exception as e:
            logger.error(
                "Gemini extraction failed (error_type=%s)",
                type(e).__name__,
            )
            return {}

    @staticmethod
    def chunk_redacted_text(redacted_text: str,
                            chunk_chars: int = 12_000) -> list[str]:
        """Split the entire redacted document without silently truncating it."""
        if not redacted_text:
            return []
        if chunk_chars <= 0:
            raise ValueError("chunk_chars must be positive")
        return [
            redacted_text[start:start + chunk_chars]
            for start in range(0, len(redacted_text), chunk_chars)
        ]

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
            response = generate_content(
                self._client,
                prompt,
                temperature=0.1,
                max_output_tokens=4096,
            )
            return response.text

        except Exception as e:
            logger.error(
                "Gemini complex analysis failed (error_type=%s)",
                type(e).__name__,
            )
            return None

    # ── Setup ───────────────────────────────────────────────

    def _setup_client(self):
        """Initialize the Gemini API client."""
        try:
            self._client = create_client(self._api_key)
            logger.info(f"Gemini client initialized with model: {MODEL_ID}")

        except ImportError:
            logger.error(
                "google-genai not installed. Run: pip install google-genai"
            )
        except Exception as e:
            logger.error(
                "Failed to initialize Gemini (error_type=%s)",
                type(e).__name__,
            )

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
2. **labs** — name, loinc_code (only when explicitly present), value (numeric), value_text (non-numeric), unit, flag (High/Low/Normal/Critical), test_date (YYYY-MM-DD)
3. **diagnoses** — name, date_diagnosed (YYYY-MM-DD), status (Active/Resolved/Chronic/Ruled out)
4. **procedures** — name, procedure_date (YYYY-MM-DD), outcome
5. **allergies** — allergen, reaction, severity (Mild/Moderate/Severe/Life-threatening)
6. **genetics** — gene, variant, phenotype, clinical_significance, implications
7. **notes** — note_type (visit_summary/referral/patient_log/provider_note), summary, provider, note_date (YYYY-MM-DD)

Rules:
- Extract EVERY clinical entity, no matter how minor
- Conditions listed under a "Pertinent Negatives" heading, or explicitly negated ("denies", "no history of", "negative for", "ruled out"), are conditions the patient does NOT have — set their status to "Ruled out", never "Active"
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
                    item.provenance.extraction_model = MODEL_ID

        return results
