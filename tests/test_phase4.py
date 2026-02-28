"""
Phase 4 Tests — PII Redaction (Pass 1.5)

Tests the regex fallback redaction (works without Presidio installed)
and the structural components of the Redactor.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.privacy.redactor import Redactor


def test_ssn_redaction():
    """SSNs are redacted."""
    redactor = Redactor()
    text = "Patient SSN: 123-45-6789. Metformin 500mg daily."
    result = redactor.redact(text, "test.pdf")

    assert "123-45-6789" not in result
    assert "SSN_REDACTED" in result
    assert "Metformin 500mg" in result  # Clinical data preserved

    print("✓ SSN redacted, medication preserved")


def test_phone_redaction():
    """Phone numbers are redacted."""
    redactor = Redactor()
    text = "Call patient at (555) 123-4567. Labs show A1c 6.5%."
    result = redactor.redact(text, "test.pdf")

    assert "(555) 123-4567" not in result
    assert "PHONE_REDACTED" in result
    assert "A1c 6.5%" in result

    print("✓ Phone number redacted, lab value preserved")


def test_email_redaction():
    """Email addresses are redacted."""
    redactor = Redactor()
    text = "Email john.doe@hospital.com for appointment. Lisinopril 10mg."
    result = redactor.redact(text, "test.pdf")

    assert "john.doe@hospital.com" not in result
    assert "EMAIL_REDACTED" in result
    assert "Lisinopril 10mg" in result

    print("✓ Email redacted, medication preserved")


def test_dob_redaction():
    """Dates of birth are redacted, clinical dates preserved."""
    redactor = Redactor()
    text = "DOB: 03/15/1965. Lab date: 2024-01-15. Glucose 105 mg/dL."
    result = redactor.redact(text, "test.pdf")

    assert "03/15/1965" not in result
    assert "DOB_REDACTED" in result
    # Clinical dates and values preserved
    assert "2024-01-15" in result
    assert "Glucose 105 mg/dL" in result

    print("✓ DOB redacted, clinical dates and lab values preserved")


def test_mrn_redaction():
    """Medical record numbers are redacted."""
    redactor = Redactor()
    text = "MRN: A1234567. Patient diagnosed with hypertension."
    result = redactor.redact(text, "test.pdf")

    assert "A1234567" not in result
    assert "MRN_REDACTED" in result
    assert "hypertension" in result

    print("✓ MRN redacted, diagnosis preserved")


def test_clinical_data_preserved():
    """Clinical content survives redaction intact."""
    redactor = Redactor()

    clinical_text = """
    Active Medications:
    - Metformin 500mg BID
    - Lisinopril 10mg daily
    - Atorvastatin 20mg HS

    Lab Results (2024-01-15):
    - HbA1c: 6.5% (High)
    - LDL Cholesterol: 130 mg/dL
    - eGFR: 85 mL/min/1.73m2
    - TSH: 2.1 mIU/L

    Diagnoses:
    - Type 2 Diabetes (E11.9)
    - Essential Hypertension (I10)
    - Hyperlipidemia (E78.5)
    """

    result = redactor.redact(clinical_text, "test.pdf")

    # All clinical data should be preserved
    assert "Metformin 500mg" in result
    assert "Lisinopril 10mg" in result
    assert "Atorvastatin 20mg" in result
    assert "HbA1c: 6.5%" in result
    assert "LDL Cholesterol: 130" in result
    assert "Type 2 Diabetes" in result
    assert "E11.9" in result
    assert "I10" in result

    print("✓ All clinical data preserved through redaction")


def test_mixed_pii_and_clinical():
    """Mixed text with PII and clinical data."""
    redactor = Redactor()
    text = (
        "Patient: John Smith, DOB: 01/15/1960, SSN: 123-45-6789. "
        "Phone: (555) 234-5678. MRN: JS123456. "
        "Presents with chest pain. BP 140/90. "
        "Currently on Aspirin 81mg and Metoprolol 25mg. "
        "A1c 7.2%, elevated. Refer to cardiology."
    )

    result = redactor.redact(text, "test.pdf")

    # PII should be gone
    assert "123-45-6789" not in result
    assert "(555) 234-5678" not in result
    assert "01/15/1960" not in result

    # Clinical content should remain
    assert "chest pain" in result
    assert "BP 140/90" in result
    assert "Aspirin 81mg" in result
    assert "Metoprolol 25mg" in result
    assert "A1c 7.2%" in result
    assert "cardiology" in result

    print("✓ PII removed from mixed clinical text, all clinical data preserved")


def test_empty_and_none_input():
    """Redactor handles empty/None input gracefully."""
    redactor = Redactor()

    assert redactor.redact("", "test.pdf") == ""
    assert redactor.redact("   ", "test.pdf") == "   "
    assert redactor.redact(None, "test.pdf") is None

    print("✓ Empty/None input handled gracefully")


def test_dict_redaction():
    """Redactor walks and redacts nested dictionaries."""
    redactor = Redactor()

    data = {
        "summary": "SSN: 123-45-6789. Glucose 105 mg/dL.",
        "medications": [
            {"name": "Metformin", "note": "Call (555) 123-4567 for refill"},
        ],
        "lab_value": 6.5,  # Non-string should pass through
        "nested": {
            "deep": "MRN: AB12345. A1c normal."
        }
    }

    result = redactor.redact_dict(data, "test.pdf")

    assert "123-45-6789" not in result["summary"]
    assert "Glucose 105 mg/dL" in result["summary"]
    assert "(555) 123-4567" not in result["medications"][0]["note"]
    assert result["lab_value"] == 6.5  # Unchanged
    assert "AB12345" not in result["nested"]["deep"]
    assert "A1c normal" in result["nested"]["deep"]

    print("✓ Nested dictionary redaction works correctly")


def test_placeholder_types():
    """Different PII types get distinct placeholders."""
    from src.privacy.redactor import Redactor

    assert "NAME" in Redactor._get_placeholder("PERSON")
    assert "SSN" in Redactor._get_placeholder("US_SSN")
    assert "PHONE" in Redactor._get_placeholder("PHONE_NUMBER")
    assert "EMAIL" in Redactor._get_placeholder("EMAIL_ADDRESS")
    assert "ADDRESS" in Redactor._get_placeholder("LOCATION")
    assert "DOB" in Redactor._get_placeholder("DATE_OF_BIRTH")
    assert "MRN" in Redactor._get_placeholder("MEDICAL_RECORD_NUMBER")

    print("✓ All PII types have distinct placeholder labels")


# ── Run All Tests ───────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Phase 4 Tests — PII Redaction")
    print("=" * 60)

    test_ssn_redaction()
    test_phone_redaction()
    test_email_redaction()
    test_dob_redaction()
    test_mrn_redaction()
    test_clinical_data_preserved()
    test_mixed_pii_and_clinical()
    test_empty_and_none_input()
    test_dict_redaction()
    test_placeholder_types()

    print()
    print("=" * 60)
    print("All Phase 4 tests passed ✓")
    print("=" * 60)
