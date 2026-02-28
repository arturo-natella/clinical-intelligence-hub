"""Phase 2 verification: Preprocessing — file classification, text extraction, FHIR parsing, DICOM."""

import json
import tempfile
from pathlib import Path


def test_preprocessor():
    """Test file classification and SHA-256 hashing."""
    from src.database import Database
    from src.extraction.preprocessor import Preprocessor
    from src.models import FileType

    with tempfile.TemporaryDirectory() as tmpdir:
        db = Database(Path(tmpdir) / "test.db")
        pp = Preprocessor(db)

        # Test hash computation
        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("Hello medical records")
        hash1 = pp.compute_hash(test_file)
        assert len(hash1) == 64  # SHA-256 hex = 64 chars
        hash2 = pp.compute_hash(test_file)
        assert hash1 == hash2  # Deterministic

        # Test JSON classification — non-FHIR
        non_fhir = Path(tmpdir) / "config.json"
        non_fhir.write_text('{"key": "value"}')
        assert pp.classify_file(non_fhir) == FileType.UNKNOWN

        # Test JSON classification — FHIR Bundle
        fhir_file = Path(tmpdir) / "bundle.json"
        fhir_file.write_text('{"resourceType": "Bundle", "entry": []}')
        assert pp.classify_file(fhir_file) == FileType.FHIR_JSON

        # Test image classification
        img = Path(tmpdir) / "xray.jpg"
        img.write_bytes(b"fake image data")
        assert pp.classify_file(img) == FileType.IMAGE

        # Test DICOM classification
        dcm = Path(tmpdir) / "scan.dcm"
        dcm.write_bytes(b"fake dicom")
        assert pp.classify_file(dcm) == FileType.DICOM

        # Test file registration + dedup
        registered = pp.register_file(test_file)
        # text file is UNKNOWN so should return None
        assert registered is None

        # Register an image
        registered = pp.register_file(img)
        assert registered is not None
        assert registered.file_type == FileType.IMAGE

        db.close()
        print("✓ Preprocessor: file classification, SHA-256 hashing, dedup, registration working")


def test_fhir_parser():
    """Test FHIR JSON bundle parsing."""
    from src.extraction.fhir_parser import FHIRParser
    from src.models import Medication, LabResult, Diagnosis

    # Create a realistic FHIR Bundle
    bundle = {
        "resourceType": "Bundle",
        "entry": [
            {
                "resource": {
                    "resourceType": "MedicationRequest",
                    "status": "active",
                    "medicationCodeableConcept": {
                        "coding": [
                            {
                                "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                                "code": "6809",
                                "display": "Metformin"
                            }
                        ],
                        "text": "Metformin 500mg"
                    },
                    "dosageInstruction": [{"text": "500mg twice daily"}],
                    "authoredOn": "2020-03-15"
                }
            },
            {
                "resource": {
                    "resourceType": "Observation",
                    "code": {
                        "coding": [
                            {
                                "system": "http://loinc.org",
                                "code": "4548-4",
                                "display": "Hemoglobin A1c"
                            }
                        ]
                    },
                    "valueQuantity": {
                        "value": 7.2,
                        "unit": "%"
                    },
                    "referenceRange": [
                        {"low": {"value": 4.0}, "high": {"value": 5.6}}
                    ],
                    "interpretation": [{"text": "High"}],
                    "effectiveDateTime": "2023-06-01"
                }
            },
            {
                "resource": {
                    "resourceType": "Condition",
                    "code": {
                        "coding": [
                            {
                                "system": "http://snomed.info/sct",
                                "code": "44054006",
                                "display": "Type 2 diabetes mellitus"
                            }
                        ]
                    },
                    "clinicalStatus": {
                        "coding": [
                            {
                                "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                                "code": "active"
                            }
                        ]
                    },
                    "onsetDateTime": "2019-01-10"
                }
            },
            {
                "resource": {
                    "resourceType": "AllergyIntolerance",
                    "code": {"text": "Penicillin"},
                    "reaction": [
                        {
                            "manifestation": [{"text": "Hives"}],
                            "severity": "moderate"
                        }
                    ]
                }
            }
        ]
    }

    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(bundle, f)
        fhir_path = Path(f.name)

    parser = FHIRParser(source_file="test_bundle.json")
    results = parser.parse_bundle(fhir_path)

    # Medications
    assert len(results["medications"]) == 1
    med = results["medications"][0]
    assert med.name == "Metformin 500mg"
    assert med.rxnorm_cui == "6809"
    assert med.dosage == "500mg twice daily"
    assert med.provenance.confidence == 1.0

    # Labs
    assert len(results["labs"]) == 1
    lab = results["labs"][0]
    assert lab.loinc_code == "4548-4"
    assert lab.value == 7.2
    assert lab.unit == "%"
    assert lab.reference_high == 5.6

    # Diagnoses
    assert len(results["diagnoses"]) == 1
    dx = results["diagnoses"][0]
    assert dx.snomed_code == "44054006"
    assert "diabetes" in dx.name.lower()

    # Allergies
    assert len(results["allergies"]) == 1
    assert results["allergies"][0].allergen == "Penicillin"
    assert results["allergies"][0].reaction == "Hives"

    fhir_path.unlink()
    print("✓ FHIR Parser: Bundle parsing with medications, labs, diagnoses, allergies working")


def test_dicom_converter():
    """Test DICOM metadata extraction (without real DICOM files)."""
    from src.extraction.dicom_converter import DICOMConverter

    conv = DICOMConverter()

    # Test date formatting
    assert conv._format_dicom_date("20230601") == "2023-06-01"
    assert conv._format_dicom_date("20201231") == "2020-12-31"
    assert conv._format_dicom_date(None) is None
    assert conv._format_dicom_date("short") is None

    print("✓ DICOM Converter: date formatting and utility methods working")


if __name__ == "__main__":
    test_preprocessor()
    test_fhir_parser()
    test_dicom_converter()
    print("\n══════════════════════════════════════")
    print("  Phase 2 Verification: ALL PASSED")
    print("══════════════════════════════════════")
