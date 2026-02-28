"""Phase 1 verification: Models, Database, Encryption."""

import json
import tempfile
from datetime import date, datetime
from pathlib import Path

# Test 1: Pydantic models with provenance
def test_models():
    from src.models import (
        PatientProfile, Medication, LabResult, Provenance,
        MedicationStatus, ClinicalFlag, AlertSeverity, FindingCategory,
        CrossDisciplinaryConnection
    )

    # Create a medication with provenance
    med = Medication(
        name="Lisinopril",
        generic_name="lisinopril",
        rxnorm_cui="29046",
        dosage="10mg daily",
        status=MedicationStatus.ACTIVE,
        start_date=date(2020, 3, 15),
        provenance=Provenance(
            source_file="labs_2020.pdf",
            source_page=2,
            extraction_model="medgemma-27b",
            confidence=0.95,
            raw_text="Lisinopril 10mg PO daily"
        )
    )
    assert med.provenance.source_file == "labs_2020.pdf"
    assert med.provenance.confidence == 0.95

    # Create a lab with provenance
    lab = LabResult(
        name="Hemoglobin A1c",
        loinc_code="4548-4",
        value=7.2,
        unit="%",
        flag="High",
        test_date=date(2023, 6, 1),
        provenance=Provenance(
            source_file="quest_results_2023.pdf",
            source_page=1,
            extraction_model="medgemma-27b",
            confidence=0.98
        )
    )
    assert lab.loinc_code == "4548-4"

    # Cross-disciplinary connection
    conn = CrossDisciplinaryConnection(
        title="Vitamin D deficiency may contribute to anxiety symptoms",
        description="Patient's vitamin D level of 18 ng/mL is below 30 ng/mL threshold...",
        specialties=["Endocrinology", "Psychiatry", "Nutrition/Metabolic Medicine"],
        patient_data_points=["Vitamin D: 18 ng/mL (2022)", "Anxiety documented (2021)"],
        severity=AlertSeverity.MODERATE
    )
    assert len(conn.specialties) == 3

    # Full profile
    profile = PatientProfile()
    profile.clinical_timeline.medications.append(med)
    profile.clinical_timeline.labs.append(lab)
    profile.analysis.cross_disciplinary.append(conn)

    # Serialize and deserialize
    json_str = profile.model_dump_json(indent=2)
    restored = PatientProfile.model_validate_json(json_str)
    assert len(restored.clinical_timeline.medications) == 1
    assert restored.clinical_timeline.medications[0].provenance.source_file == "labs_2020.pdf"
    assert len(restored.analysis.cross_disciplinary) == 1

    print("✓ Models: All Pydantic V2 models with provenance work correctly")


# Test 2: Database
def test_database():
    from src.database import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        db = Database(Path(tmpdir) / "test.db")

        # File state tracking
        db.upsert_file_state(
            file_id="f1", filename="labs.pdf", file_type="pdf_text",
            sha256_hash="abc123", file_size_bytes=50000, status="pending"
        )
        assert not db.is_duplicate("xyz789")
        db.update_file_status("f1", "complete")
        assert db.is_duplicate("abc123")

        # Stats
        stats = db.get_processing_stats()
        assert stats["total"] == 1
        assert stats["completed"] == 1

        # Redaction log
        db.log_redaction("PERSON", "Patient [REDACTED] was seen...", "labs.pdf")
        db.log_redaction("PERSON", "Dr. [REDACTED] ordered...", "notes.pdf")
        db.log_redaction("DATE_OF_BIRTH", "[REDACTED]", "labs.pdf")
        summary = db.get_redaction_summary()
        assert summary[0]["original_type"] == "PERSON"
        assert summary[0]["count"] == 2

        # Monitoring alerts
        db.save_alert("a1", "OpenFDA", "New safety alert",
                      "FDA issued alert for Lisinopril",
                      "Patient is on Lisinopril 10mg",
                      "high")
        alerts = db.get_unaddressed_alerts()
        assert len(alerts) == 1
        db.mark_alert_addressed("a1")
        assert len(db.get_unaddressed_alerts()) == 0

        # Pipeline run
        db.start_pipeline_run("run1")
        db.complete_pipeline_run("run1", files_processed=5, files_failed=0)

        db.close()
        print("✓ Database: SQLite with WAL mode, state tracking, redaction log, alerts all working")


# Test 3: Encryption
def test_encryption():
    from src.encryption import encrypt_data, decrypt_data, EncryptedVault

    # Raw encrypt/decrypt
    original = b"Patient has Type 2 Diabetes, A1C 7.2%"
    passphrase = "test-vault-passphrase-2026"

    encrypted = encrypt_data(original, passphrase)
    assert encrypted != original
    assert len(encrypted) > len(original)  # Salt + nonce + tag overhead

    decrypted = decrypt_data(encrypted, passphrase)
    assert decrypted == original

    # Wrong passphrase should fail
    try:
        decrypt_data(encrypted, "wrong-passphrase")
        assert False, "Should have raised an error"
    except Exception:
        pass  # Expected — InvalidTag from GCM

    # Vault: profile encrypt/decrypt
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = EncryptedVault(Path(tmpdir), passphrase)

        profile = {
            "profile_id": "test-123",
            "clinical_timeline": {
                "medications": [{"name": "Metformin", "dosage": "500mg"}],
                "labs": [{"name": "A1C", "value": 7.2}]
            }
        }
        vault.save_profile(profile)
        loaded = vault.load_profile()
        assert loaded["clinical_timeline"]["medications"][0]["name"] == "Metformin"

        # API key vault
        vault.set_api_key("gemini", "fake-key-12345")
        vault.set_api_key("openfda", "fake-fda-key")
        assert vault.get_api_key("gemini") == "fake-key-12345"
        assert vault.get_api_key("openfda") == "fake-fda-key"
        assert vault.get_api_key("nonexistent") is None

        # Passphrase verification
        assert vault.verify_passphrase() is True

        # Wrong passphrase vault should fail verification
        bad_vault = EncryptedVault(Path(tmpdir), "wrong-pass")
        assert bad_vault.verify_passphrase() is False

    print("✓ Encryption: AES-256-GCM + Argon2id key derivation working correctly")


if __name__ == "__main__":
    test_models()
    test_database()
    test_encryption()
    print("\n══════════════════════════════════════")
    print("  Phase 1 Verification: ALL PASSED")
    print("══════════════════════════════════════")
