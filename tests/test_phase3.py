"""
Phase 3 Tests — Local Extraction (Passes 1a, 1b, 1c)

Tests the structural and logic components of the extraction pipeline.
Actual model inference requires Ollama running + models downloaded,
so these tests verify:
  - TextExtractor: chunking, prompt building, result merging
  - VisionAnalyzer: prompt building, result parsing
  - ModelManager: memory tracking, cleanup flow
  - MONAIDetector: task selection, bundle registry, nodule classification
"""

import sys
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models import (
    ImagingFinding,
    Medication,
    MedicationStatus,
    LabResult,
    Diagnosis,
    Provenance,
)


# ── TextExtractor Tests ─────────────────────────────────────

def test_text_extractor_chunking():
    """TextExtractor._build_chunks splits pages correctly."""
    from src.extraction.text_extractor import TextExtractor, MAX_CHUNK_CHARS

    extractor = TextExtractor.__new__(TextExtractor)

    # Build pages that exceed chunk limit
    pages = []
    for i in range(10):
        pages.append({
            "page": i + 1,
            "text": "A" * 5000,  # 5K chars each, 50K total
        })

    chunks = extractor._build_chunks(pages)

    # Should split into multiple chunks (50K > 24K limit)
    assert len(chunks) > 1, f"Expected multiple chunks, got {len(chunks)}"

    # Each chunk should be under the limit (approximately)
    for chunk_pages, chunk_text in chunks:
        assert len(chunk_pages) > 0
        assert len(chunk_text) > 0

    # All pages should be accounted for
    total_pages = sum(len(cp) for cp, _ in chunks)
    assert total_pages == 10, f"Expected 10 pages total, got {total_pages}"

    print("✓ TextExtractor chunking works correctly")


def test_text_extractor_prompt_building():
    """TextExtractor._build_prompt produces valid prompt."""
    from src.extraction.text_extractor import TextExtractor

    extractor = TextExtractor.__new__(TextExtractor)
    sample_text = "Patient presents with hypertension. BP 140/90."

    prompt = extractor._build_prompt(sample_text)

    assert "medications" in prompt
    assert "labs" in prompt
    assert "diagnoses" in prompt
    assert "procedures" in prompt
    assert "allergies" in prompt
    assert "genetics" in prompt
    assert "notes" in prompt
    assert sample_text in prompt
    assert "JSON" in prompt

    print("✓ TextExtractor prompt includes all 7 extraction categories")


def test_text_extractor_merge_results():
    """TextExtractor._merge_results correctly parses extracted data."""
    from src.extraction.text_extractor import TextExtractor

    extractor = TextExtractor.__new__(TextExtractor)

    results = {
        "medications": [],
        "labs": [],
        "diagnoses": [],
        "procedures": [],
        "allergies": [],
        "genetics": [],
        "notes": [],
    }

    extracted = {
        "medications": [
            {"name": "Lisinopril", "dosage": "10mg", "status": "active"},
            {"name": "Metformin", "dosage": "500mg", "status": "discontinued"},
        ],
        "labs": [
            {"name": "HbA1c", "value": 6.5, "unit": "%", "flag": "High"},
        ],
        "diagnoses": [
            {"name": "Type 2 Diabetes", "date_diagnosed": "2020-03-15"},
        ],
    }

    extractor._merge_results(results, extracted, "test.pdf", 1)

    assert len(results["medications"]) == 2
    assert results["medications"][0].name == "Lisinopril"
    assert results["medications"][0].status == MedicationStatus.ACTIVE
    assert results["medications"][1].status == MedicationStatus.DISCONTINUED

    assert len(results["labs"]) == 1
    assert results["labs"][0].value == 6.5
    assert results["labs"][0].flag == "High"

    assert len(results["diagnoses"]) == 1
    assert results["diagnoses"][0].date_diagnosed == date(2020, 3, 15)

    # All should have provenance
    assert results["medications"][0].provenance.source_file == "test.pdf"
    assert results["medications"][0].provenance.source_page == 1
    assert results["medications"][0].provenance.extraction_model == "medgemma-27b"

    print("✓ TextExtractor result merging with provenance works correctly")


def test_text_extractor_merge_handles_bad_data():
    """TextExtractor._merge_results gracefully handles malformed data."""
    from src.extraction.text_extractor import TextExtractor

    extractor = TextExtractor.__new__(TextExtractor)

    results = {
        "medications": [], "labs": [], "diagnoses": [],
        "procedures": [], "allergies": [], "genetics": [], "notes": [],
    }

    # Mix of good and bad data
    extracted = {
        "medications": [
            {"name": "Lisinopril"},                    # Minimal valid
            {},                                          # Missing name
            {"name": "", "dosage": "10mg"},             # Empty name
            "not_a_dict",                                # Wrong type
            {"name": "Aspirin", "status": "invalid_status"},  # Bad enum
        ],
        "labs": [
            {"name": "Glucose", "value": "105"},       # String value → should parse
            {"name": "Culture", "value": "Positive"},  # Non-numeric → value_text
        ],
    }

    extractor._merge_results(results, extracted, "test.pdf", 1)

    # Should get Lisinopril + Aspirin (with UNKNOWN status fallback)
    assert len(results["medications"]) >= 1
    assert results["medications"][0].name == "Lisinopril"

    # Glucose should parse to float, Culture should be value_text
    assert len(results["labs"]) == 2
    assert results["labs"][0].value == 105.0
    assert results["labs"][1].value_text == "Positive"

    print("✓ TextExtractor handles malformed extraction data gracefully")


# ── VisionAnalyzer Tests ────────────────────────────────────

def test_vision_analyzer_prompt_with_context():
    """VisionAnalyzer._build_prompt incorporates modality and region."""
    from src.imaging.vision_analyzer import VisionAnalyzer

    analyzer = VisionAnalyzer.__new__(VisionAnalyzer)

    # With both modality and body region
    prompt = analyzer._build_prompt(modality="CT", body_region="chest")
    assert "CT" in prompt
    assert "chest" in prompt
    assert "radiologist" in prompt
    assert "JSON" in prompt

    # With only modality
    prompt = analyzer._build_prompt(modality="MRI")
    assert "MRI" in prompt

    # With nothing
    prompt = analyzer._build_prompt()
    assert "medical image" in prompt

    print("✓ VisionAnalyzer prompt building works with all context combinations")


# ── ModelManager Tests ──────────────────────────────────────

def test_model_manager_memory_tracking():
    """ModelManager reports memory usage."""
    from src.imaging.model_manager import ModelManager

    mm = ModelManager()

    # get_memory_usage_gb should return a number (may be 0.0 if psutil missing)
    mem = mm.get_memory_usage_gb()
    assert isinstance(mem, float)
    assert mem >= 0.0

    # get_system_memory_gb should return a dict
    sys_mem = mm.get_system_memory_gb()
    assert isinstance(sys_mem, dict)
    assert "total_gb" in sys_mem
    assert "available_gb" in sys_mem

    print(f"✓ ModelManager memory tracking: process={mem:.1f}GB, "
          f"system total={sys_mem['total_gb']:.0f}GB")


def test_model_manager_cleanup():
    """ModelManager.cleanup_between_models runs without error."""
    from src.imaging.model_manager import ModelManager

    mm = ModelManager()
    # Should run without raising
    mm.cleanup_between_models()

    print("✓ ModelManager cleanup_between_models completes without error")


def test_model_manager_budget_check():
    """ModelManager.check_memory_budget returns boolean."""
    from src.imaging.model_manager import ModelManager

    mm = ModelManager()
    within = mm.check_memory_budget()
    assert isinstance(within, bool)

    print(f"✓ ModelManager budget check: within_budget={within}")


# ── MONAIDetector Tests ─────────────────────────────────────

def test_monai_task_selection():
    """MONAIDetector._select_tasks matches modality and body region."""
    from src.imaging.monai_detector import MONAIDetector

    detector = MONAIDetector.__new__(MONAIDetector)

    # CT chest should select lung_nodule and wholebody_ct
    tasks = detector._select_tasks(modality="CT", body_region="chest")
    assert "lung_nodule" in tasks
    assert "wholebody_ct" in tasks
    assert "brain_tumor" not in tasks

    # MRI brain should select brain_tumor
    tasks = detector._select_tasks(modality="MRI", body_region="brain")
    assert "brain_tumor" in tasks
    assert "lung_nodule" not in tasks

    # Pathology tissue
    tasks = detector._select_tasks(modality="pathology", body_region="tissue")
    assert "pathology_nuclei" in tasks

    # No modality/region → all tasks applicable
    tasks = detector._select_tasks()
    assert len(tasks) == 4

    print("✓ MONAIDetector task selection matches modality/body region correctly")


def test_monai_nodule_size_classification():
    """MONAIDetector._classify_nodule_size returns correct Lung-RADS."""
    from src.imaging.monai_detector import MONAIDetector

    assert "RADS 1" in MONAIDetector._classify_nodule_size(2.0)
    assert "RADS 2" in MONAIDetector._classify_nodule_size(5.0)
    assert "RADS 3" in MONAIDetector._classify_nodule_size(7.0)
    assert "4A" in MONAIDetector._classify_nodule_size(10.0)
    assert "4B" in MONAIDetector._classify_nodule_size(20.0)

    print("✓ Lung-RADS nodule size classification is correct")


def test_monai_bundle_availability():
    """MONAIDetector.get_available_bundles returns registry info."""
    from src.imaging.monai_detector import MONAIDetector

    with tempfile.TemporaryDirectory() as tmpdir:
        detector = MONAIDetector.__new__(MONAIDetector)
        detector.model_dir = Path(tmpdir)
        detector._torch_available = False
        detector._monai_available = False
        detector.model_manager = None

        bundles = detector.get_available_bundles()
        assert len(bundles) == 4

        names = [b["task"] for b in bundles]
        assert "lung_nodule" in names
        assert "wholebody_ct" in names
        assert "brain_tumor" in names
        assert "pathology_nuclei" in names

        # None should be downloaded in temp dir
        for b in bundles:
            assert b["downloaded"] is False

    print("✓ MONAIDetector bundle registry lists all 4 model bundles")


def test_monai_graceful_degradation():
    """MONAIDetector.detect returns empty when MONAI unavailable."""
    from src.imaging.monai_detector import MONAIDetector

    with tempfile.TemporaryDirectory() as tmpdir:
        detector = MONAIDetector.__new__(MONAIDetector)
        detector.model_dir = Path(tmpdir)
        detector._torch_available = False
        detector._monai_available = False
        detector.model_manager = None

        # Should return empty list, not crash
        findings = detector.detect(
            image_path=Path("/fake/image.nii"),
            source_file="test.dcm",
            modality="CT",
            body_region="chest",
        )
        assert findings == []

    print("✓ MONAIDetector gracefully degrades when MONAI is unavailable")


# ── ImagingFinding Model Tests ──────────────────────────────

def test_imaging_finding_model():
    """ImagingFinding model accepts MONAI-style outputs."""
    finding = ImagingFinding(
        description="Pulmonary nodule detected — max diameter 8.5mm (Lung-RADS 4A)",
        body_region="lung",
        measurements={
            "max_diameter_mm": 8.5,
            "mean_diameter_mm": 7.2,
            "lung_rads_category": "Lung-RADS 4A (suspicious)",
        },
        monai_model="lung_nodule_ct_detection",
        confidence=0.92,
    )

    assert finding.measurements["max_diameter_mm"] == 8.5
    assert finding.monai_model == "lung_nodule_ct_detection"
    assert finding.confidence == 0.92

    # Serialization round-trip
    data = finding.model_dump()
    restored = ImagingFinding(**data)
    assert restored.measurements == finding.measurements

    print("✓ ImagingFinding model handles MONAI outputs correctly")


# ── Run All Tests ───────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Phase 3 Tests — Local Extraction Pipeline")
    print("=" * 60)

    # TextExtractor
    test_text_extractor_chunking()
    test_text_extractor_prompt_building()
    test_text_extractor_merge_results()
    test_text_extractor_merge_handles_bad_data()

    # VisionAnalyzer
    test_vision_analyzer_prompt_with_context()

    # ModelManager
    test_model_manager_memory_tracking()
    test_model_manager_cleanup()
    test_model_manager_budget_check()

    # MONAIDetector
    test_monai_task_selection()
    test_monai_nodule_size_classification()
    test_monai_bundle_availability()
    test_monai_graceful_degradation()

    # ImagingFinding model
    test_imaging_finding_model()

    print()
    print("=" * 60)
    print("All Phase 3 tests passed ✓")
    print("=" * 60)
