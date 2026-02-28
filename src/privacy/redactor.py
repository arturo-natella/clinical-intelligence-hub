"""
Clinical Intelligence Hub — Pass 1.5: PII Redaction

Uses Microsoft Presidio to strip personally identifiable information
before any data leaves the machine for cloud APIs (Gemini, Deep Research).

What gets redacted:
  - Patient names, provider names
  - Dates of birth (not clinical dates like lab dates)
  - Social Security numbers
  - Phone numbers, email addresses
  - Physical addresses
  - Medical Record Numbers (MRN) — custom recognizer
  - Patient account/ID numbers — custom recognizer

What is preserved:
  - Medication names, dosages
  - Lab values and units
  - Diagnosis names and codes (SNOMED, ICD-10, LOINC)
  - Procedure names
  - Clinical dates (lab dates, imaging dates, prescription dates)
  - Anatomical terms

Every redaction is logged to SQLite for the Section 10 audit trail.
"""

import logging
import re
from typing import Optional

from src.models import RedactionEntry

logger = logging.getLogger("CIH-Redactor")


class Redactor:
    """
    Pass 1.5: PII redaction with Microsoft Presidio + custom medical recognizers.

    Must be called before any cloud API call (Gemini, Deep Research, etc.).
    Logs all redactions to the database for the report's audit trail.
    """

    def __init__(self, db=None):
        """
        Args:
            db: Optional Database instance for logging redactions to SQLite
        """
        self.db = db
        self._presidio_available = False
        self._analyzer = None
        self._anonymizer = None
        self._setup_presidio()

    def redact(self, text: str, source_file: str = "unknown") -> str:
        """
        Redact PII from text while preserving clinical content.

        Args:
            text: Raw clinical text that may contain PII
            source_file: Source filename for audit trail

        Returns:
            Text with PII replaced by type-specific placeholders
        """
        if not text or not text.strip():
            return text

        # Try Presidio first, fall back to regex
        if self._presidio_available:
            return self._redact_with_presidio(text, source_file)
        else:
            return self._redact_with_regex(text, source_file)

    def redact_dict(self, data: dict, source_file: str = "unknown") -> dict:
        """
        Recursively redact PII from a dictionary of clinical data.

        Walks through all string values and redacts them.
        Preserves structure and non-string values.
        """
        return self._walk_and_redact(data, source_file)

    def get_redaction_summary(self) -> dict:
        """Get summary of all redactions performed (from database)."""
        if self.db:
            return self.db.get_redaction_summary()
        return {}

    # ── Presidio Setup ──────────────────────────────────────

    def _setup_presidio(self):
        """Initialize Microsoft Presidio with custom medical recognizers."""
        try:
            from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
            from presidio_anonymizer import AnonymizerEngine
            from presidio_anonymizer.entities import OperatorConfig

            # Create analyzer with custom recognizers
            self._analyzer = AnalyzerEngine()

            # Add custom medical recognizers
            self._add_medical_recognizers()

            # Create anonymizer with type-specific replacements
            self._anonymizer = AnonymizerEngine()

            self._presidio_available = True
            logger.info("Presidio PII redaction engine initialized")

        except ImportError:
            logger.warning(
                "Presidio not available. Install with: "
                "pip install presidio-analyzer presidio-anonymizer"
            )
            self._presidio_available = False

    def _add_medical_recognizers(self):
        """Add custom recognizers for medical-specific PII patterns."""
        from presidio_analyzer import PatternRecognizer, Pattern

        # Medical Record Number (MRN) — common patterns
        mrn_recognizer = PatternRecognizer(
            supported_entity="MEDICAL_RECORD_NUMBER",
            name="MRN Recognizer",
            patterns=[
                Pattern(
                    name="mrn_labeled",
                    regex=r"(?i)(?:MRN|Medical Record(?:\s+Number)?|Patient\s+ID"
                          r"|Account\s*#?|Chart\s*#?)\s*[:#]?\s*([A-Z0-9]{4,15})",
                    score=0.85,
                ),
                Pattern(
                    name="mrn_format",
                    regex=r"\b[A-Z]{1,3}\d{6,10}\b",
                    score=0.4,  # Lower confidence for bare patterns
                ),
            ],
            context=["mrn", "medical record", "patient id", "account", "chart"],
        )

        # Health insurance ID numbers
        insurance_recognizer = PatternRecognizer(
            supported_entity="INSURANCE_ID",
            name="Insurance ID Recognizer",
            patterns=[
                Pattern(
                    name="insurance_labeled",
                    regex=r"(?i)(?:Insurance|Policy|Member|Subscriber|Group)"
                          r"\s*(?:ID|#|Number|No\.?)\s*[:#]?\s*([A-Z0-9]{5,20})",
                    score=0.8,
                ),
            ],
            context=["insurance", "policy", "member", "subscriber", "group"],
        )

        # Date of Birth (distinguish from clinical dates)
        dob_recognizer = PatternRecognizer(
            supported_entity="DATE_OF_BIRTH",
            name="DOB Recognizer",
            patterns=[
                Pattern(
                    name="dob_labeled",
                    regex=r"(?i)(?:DOB|Date\s+of\s+Birth|Birth\s*Date|Born)"
                          r"\s*[:#]?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})",
                    score=0.95,
                ),
                Pattern(
                    name="dob_labeled_iso",
                    regex=r"(?i)(?:DOB|Date\s+of\s+Birth|Birth\s*Date|Born)"
                          r"\s*[:#]?\s*(\d{4}[/\-]\d{1,2}[/\-]\d{1,2})",
                    score=0.95,
                ),
            ],
            context=["dob", "birth", "born", "age"],
        )

        # Register all custom recognizers
        registry = self._analyzer.registry
        registry.add_recognizer(mrn_recognizer)
        registry.add_recognizer(insurance_recognizer)
        registry.add_recognizer(dob_recognizer)

        logger.debug("Added 3 custom medical PII recognizers")

    # ── Presidio Redaction ──────────────────────────────────

    def _redact_with_presidio(self, text: str, source_file: str) -> str:
        """Redact using Microsoft Presidio NLP engine."""
        from presidio_anonymizer.entities import OperatorConfig

        # Entities to detect
        entities = [
            "PERSON",
            "PHONE_NUMBER",
            "EMAIL_ADDRESS",
            "US_SSN",
            "LOCATION",
            "DATE_OF_BIRTH",
            "MEDICAL_RECORD_NUMBER",
            "INSURANCE_ID",
            "US_DRIVER_LICENSE",
            "CREDIT_CARD",
            "US_PASSPORT",
        ]

        # Analyze text for PII
        results = self._analyzer.analyze(
            text=text,
            entities=entities,
            language="en",
            score_threshold=0.5,
        )

        if not results:
            return text

        # Build type-specific replacement operators
        operators = {}
        for entity_type in set(r.entity_type for r in results):
            placeholder = self._get_placeholder(entity_type)
            operators[entity_type] = OperatorConfig(
                "replace", {"new_value": placeholder}
            )

        # Anonymize
        anonymized = self._anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators=operators,
        )

        # Log each redaction
        for result in results:
            original_snippet = text[result.start:result.end]
            context_start = max(0, result.start - 30)
            context_end = min(len(text), result.end + 30)
            context = (
                text[context_start:result.start]
                + self._get_placeholder(result.entity_type)
                + text[result.end:context_end]
            )

            self._log_redaction(
                entity_type=result.entity_type,
                context=context,
                source_file=source_file,
            )

        redacted_text = anonymized.text
        logger.info(
            f"Redacted {len(results)} PII entities from {source_file}"
        )
        return redacted_text

    # ── Regex Fallback ──────────────────────────────────────

    def _redact_with_regex(self, text: str, source_file: str) -> str:
        """
        Fallback PII redaction using regex patterns.
        Used when Presidio is not installed.
        """
        redaction_count = 0

        # SSN: XXX-XX-XXXX
        ssn_pattern = r'\b\d{3}-\d{2}-\d{4}\b'
        matches = re.findall(ssn_pattern, text)
        if matches:
            text = re.sub(ssn_pattern, '[SSN_REDACTED]', text)
            redaction_count += len(matches)
            for m in matches:
                self._log_redaction("US_SSN", "[SSN_REDACTED]", source_file)

        # Phone numbers (US format)
        phone_pattern = r'\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'
        matches = re.findall(phone_pattern, text)
        if matches:
            text = re.sub(phone_pattern, '[PHONE_REDACTED]', text)
            redaction_count += len(matches)
            for m in matches:
                self._log_redaction("PHONE_NUMBER", "[PHONE_REDACTED]", source_file)

        # Email addresses
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        matches = re.findall(email_pattern, text)
        if matches:
            text = re.sub(email_pattern, '[EMAIL_REDACTED]', text)
            redaction_count += len(matches)
            for m in matches:
                self._log_redaction("EMAIL_ADDRESS", "[EMAIL_REDACTED]", source_file)

        # DOB with label
        dob_pattern = (
            r'(?i)(?:DOB|Date\s+of\s+Birth|Birth\s*Date|Born)'
            r'\s*[:#]?\s*\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}'
        )
        matches = re.findall(dob_pattern, text)
        if matches:
            text = re.sub(dob_pattern, 'DOB: [DOB_REDACTED]', text)
            redaction_count += len(matches)
            for m in matches:
                self._log_redaction("DATE_OF_BIRTH", "[DOB_REDACTED]", source_file)

        # MRN with label
        mrn_pattern = (
            r'(?i)(?:MRN|Medical Record\s*(?:Number)?|Patient\s*ID'
            r'|Account\s*#?|Chart\s*#?)\s*[:#]?\s*[A-Z0-9]{4,15}'
        )
        matches = re.findall(mrn_pattern, text)
        if matches:
            text = re.sub(mrn_pattern, 'MRN: [MRN_REDACTED]', text)
            redaction_count += len(matches)
            for m in matches:
                self._log_redaction("MEDICAL_RECORD_NUMBER", "[MRN_REDACTED]", source_file)

        if redaction_count > 0:
            logger.info(
                f"Regex fallback redacted {redaction_count} patterns from {source_file}"
            )
        return text

    # ── Helpers ──────────────────────────────────────────────

    @staticmethod
    def _get_placeholder(entity_type: str) -> str:
        """Get a type-specific placeholder for redacted content."""
        placeholders = {
            "PERSON": "[NAME_REDACTED]",
            "PHONE_NUMBER": "[PHONE_REDACTED]",
            "EMAIL_ADDRESS": "[EMAIL_REDACTED]",
            "US_SSN": "[SSN_REDACTED]",
            "LOCATION": "[ADDRESS_REDACTED]",
            "DATE_OF_BIRTH": "[DOB_REDACTED]",
            "MEDICAL_RECORD_NUMBER": "[MRN_REDACTED]",
            "INSURANCE_ID": "[INSURANCE_ID_REDACTED]",
            "US_DRIVER_LICENSE": "[DL_REDACTED]",
            "CREDIT_CARD": "[CC_REDACTED]",
            "US_PASSPORT": "[PASSPORT_REDACTED]",
        }
        return placeholders.get(entity_type, f"[{entity_type}_REDACTED]")

    def _log_redaction(self, entity_type: str, context: str, source_file: str):
        """Log a redaction event to the database audit trail."""
        if self.db:
            self.db.log_redaction(
                original_type=entity_type,
                context=context[:200],  # Truncate context for storage
                file_source=source_file,
            )

    def _walk_and_redact(self, obj, source_file: str):
        """Recursively walk a data structure and redact string values."""
        if isinstance(obj, str):
            return self.redact(obj, source_file)
        elif isinstance(obj, dict):
            return {k: self._walk_and_redact(v, source_file) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._walk_and_redact(item, source_file) for item in obj]
        return obj
