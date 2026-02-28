"""
Phase 5 Tests — Cloud Analysis (Passes 2, 3, 4)

Tests the structural and logic components of the cloud analysis pipeline.
Actual Gemini/Deep Research calls require API keys, so these tests verify:
  - CrossDisciplinaryEngine: query generation, specialty mapping
  - CommunityInsights: search term building, subreddit mapping
  - GeminiFallback: prompt building
  - DeepResearch: significance mapping
  - Session reset: database clear + profile clear
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models import MedicationStatus, AlertSeverity


# ── CrossDisciplinaryEngine Tests ───────────────────────────

def test_cross_disciplinary_query_generation():
    """CrossDisciplinaryEngine generates queries from patient profile."""
    from src.analysis.cross_disciplinary import CrossDisciplinaryEngine

    engine = CrossDisciplinaryEngine()

    profile = {
        "medications": [
            {"name": "Lisinopril", "status": "active"},
            {"name": "Metformin", "status": "active"},
            {"name": "Atorvastatin", "status": "active"},
        ],
        "labs": [
            {"name": "HbA1c", "value": 7.2, "unit": "%", "flag": "High"},
            {"name": "Vitamin D", "value": 18, "unit": "ng/mL", "flag": "Low"},
        ],
        "diagnoses": [
            {"name": "Type 2 Diabetes", "status": "Active"},
            {"name": "Essential Hypertension", "status": "Active"},
        ],
    }

    queries = engine.build_queries(profile)

    assert len(queries) > 0, "Should generate at least one query"

    # Should include drug interaction query (3 meds)
    ddi_queries = [q for q in queries if "interaction" in q["query"].lower()]
    assert len(ddi_queries) > 0, "Should generate drug interaction query for 3 meds"

    # Should include lab abnormality queries
    lab_queries = [q for q in queries if "vitamin d" in q["query"].lower()
                   or "a1c" in q["query"].lower()]
    assert len(lab_queries) > 0, "Should generate queries for abnormal labs"

    # Every query should have required fields
    for q in queries:
        assert "query" in q
        assert "specialties" in q
        assert "priority" in q
        assert q["priority"] in ("high", "medium", "low")

    print(f"✓ CrossDisciplinaryEngine generated {len(queries)} queries from sample profile")


def test_cross_disciplinary_specialty_mapping():
    """Lab tests map to correct specialties."""
    from src.analysis.cross_disciplinary import CrossDisciplinaryEngine

    specs = CrossDisciplinaryEngine._specialties_for_lab("Vitamin D")
    assert "Endocrinology" in specs
    assert "Psychiatry" in specs  # Vitamin D linked to mood

    specs = CrossDisciplinaryEngine._specialties_for_lab("eGFR")
    assert "Nephrology" in specs

    specs = CrossDisciplinaryEngine._specialties_for_lab("TSH")
    assert "Endocrinology" in specs

    specs = CrossDisciplinaryEngine._specialties_for_lab("LDL Cholesterol")
    assert "Cardiology" in specs

    print("✓ Lab → specialty mapping is correct")


def test_cross_disciplinary_constants():
    """Verify 29 specialties and 7 adjacent domains are defined."""
    from src.analysis.cross_disciplinary import MEDICAL_SPECIALTIES, ADJACENT_DOMAINS

    assert len(MEDICAL_SPECIALTIES) == 29, f"Expected 29 specialties, got {len(MEDICAL_SPECIALTIES)}"
    assert len(ADJACENT_DOMAINS) == 7, f"Expected 7 adjacent domains, got {len(ADJACENT_DOMAINS)}"

    # Key specialties should be present
    assert "Cardiology" in MEDICAL_SPECIALTIES
    assert "Endocrinology" in MEDICAL_SPECIALTIES
    assert "Psychiatry" in MEDICAL_SPECIALTIES
    assert "Pharmacology/Pharmacogenomics" in MEDICAL_SPECIALTIES

    # Key adjacent domains
    assert "Nutrition Science / Dietetics" in ADJACENT_DOMAINS
    assert "Microbiome Science" in ADJACENT_DOMAINS
    assert "Psychoneuroimmunology" in ADJACENT_DOMAINS

    print("✓ All 29 specialties and 7 adjacent domains defined")


def test_polypharmacy_detection():
    """Polypharmacy queries generated for 5+ medications."""
    from src.analysis.cross_disciplinary import CrossDisciplinaryEngine

    engine = CrossDisciplinaryEngine()

    # 6 medications should trigger polypharmacy assessment
    profile = {
        "medications": [
            {"name": f"Drug{i}", "status": "active"} for i in range(6)
        ],
        "labs": [],
        "diagnoses": [],
    }

    queries = engine.build_queries(profile)
    polypharm = [q for q in queries if "polypharmacy" in q["query"].lower()]
    assert len(polypharm) > 0, "Should generate polypharmacy query for 6 meds"
    assert polypharm[0]["priority"] == "high"

    print("✓ Polypharmacy detected for 6+ medications")


# ── CommunityInsights Tests ─────────────────────────────────

def test_community_search_term_building():
    """CommunityInsights builds correct Reddit search terms."""
    from src.analysis.community_insights import CommunityInsights

    insights = CommunityInsights()

    terms = insights._build_search_terms(
        medications=[{"name": "Metformin"}, {"name": "Lisinopril"}],
        diagnoses=[{"name": "Type 2 Diabetes"}],
    )

    assert len(terms) > 0

    # Should have medication-specific searches
    med_terms = [t for t in terms if "metformin" in t["query"].lower()]
    assert len(med_terms) > 0

    # Should have condition-specific searches
    dx_terms = [t for t in terms if "diabetes" in t["query"].lower()]
    assert len(dx_terms) > 0

    # Should have combo search for 2+ meds
    combo_terms = [t for t in terms if "and" in t["query"].lower()]
    assert len(combo_terms) > 0

    print(f"✓ Community search built {len(terms)} queries")


def test_community_subreddit_mapping():
    """Medications and conditions map to relevant subreddits."""
    from src.analysis.community_insights import CommunityInsights

    # Diabetes medication
    subs = CommunityInsights._subreddits_for_medication("Metformin")
    assert "diabetes" in subs

    # Heart medication
    subs = CommunityInsights._subreddits_for_medication("Lisinopril")
    assert "hypertension" in subs

    # SSRI
    subs = CommunityInsights._subreddits_for_medication("Sertraline")
    assert "antidepressants" in subs

    # Condition: diabetes
    subs = CommunityInsights._subreddits_for_condition("Type 2 Diabetes")
    assert "diabetes" in subs

    # Condition: anxiety
    subs = CommunityInsights._subreddits_for_condition("Anxiety disorder")
    assert "Anxiety" in subs

    print("✓ Medication/condition → subreddit mapping correct")


# ── DeepResearch Tests ──────────────────────────────────────

def test_deep_research_significance_mapping():
    """Significance strings map to correct AlertSeverity."""
    from src.analysis.deep_research import DeepResearch

    assert DeepResearch._map_significance("critical") == AlertSeverity.CRITICAL
    assert DeepResearch._map_significance("high") == AlertSeverity.HIGH
    assert DeepResearch._map_significance("moderate") == AlertSeverity.MODERATE
    assert DeepResearch._map_significance("low") == AlertSeverity.LOW
    assert DeepResearch._map_significance("unknown") == AlertSeverity.INFO

    print("✓ Significance → AlertSeverity mapping correct")


# ── GeminiFallback Tests ────────────────────────────────────

def test_gemini_prompt_with_gap_context():
    """GeminiFallback prompt includes local results for gap-filling."""
    from src.analysis.gemini_fallback import GeminiFallback, MODEL_ID

    # Verify correct model ID
    assert MODEL_ID == "gemini-3.1-pro-preview", f"Wrong model: {MODEL_ID}"

    # Test prompt building
    fb = GeminiFallback.__new__(GeminiFallback)

    local_results = {
        "medications": [{"name": "Aspirin"}],
        "labs": [],
        "diagnoses": [{"name": "HTN"}, {"name": "DM"}],
    }

    prompt = fb._build_extraction_prompt("Some medical text", local_results)

    assert "medications: 1 items already extracted" in prompt
    assert "diagnoses: 2 items already extracted" in prompt
    assert "MISSED" in prompt  # Should tell Gemini to fill gaps

    print("✓ GeminiFallback prompt includes gap-filling context")


# ── Session Reset Tests ─────────────────────────────────────

def test_database_clear_patient_data():
    """Database.clear_patient_data wipes all patient data."""
    from src.database import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        db = Database(Path(tmpdir) / "test.db")

        # Insert some data
        db.upsert_file_state("f1", "test.pdf", "pdf_text", "hash1", 1000, "complete")
        db.log_redaction("PERSON", "John in context", "test.pdf")
        db.save_alert("a1", "PubMed", "Alert", "Desc", "Why", "high")
        db.start_pipeline_run("run1")

        # Verify data exists
        stats = db.get_processing_stats()
        assert stats["total"] > 0

        # Clear
        db.clear_patient_data()

        # Verify all patient data is gone
        stats = db.get_processing_stats()
        assert stats["total"] == 0

        redactions = db.get_redaction_summary()
        assert len(redactions) == 0

        alerts = db.get_unaddressed_alerts()
        assert len(alerts) == 0

        db.close()

    print("✓ Database.clear_patient_data wipes all patient data")


def test_vault_clear_patient_profile():
    """EncryptedVault.clear_patient_profile deletes profile, keeps API keys."""
    try:
        from argon2.low_level import hash_secret_raw
    except ImportError:
        print("⊘ Vault test skipped — argon2-cffi not installed (install with: pip install argon2-cffi)")
        return

    from src.encryption import EncryptedVault

    with tempfile.TemporaryDirectory() as tmpdir:
        vault = EncryptedVault(Path(tmpdir), "test-passphrase")

        # Save both profile and API keys
        vault.save_profile({"name": "Test Patient", "diagnoses": ["HTN"]})
        vault.set_api_key("gemini", "test-key-123")

        assert vault.profile_exists()

        # Clear patient profile
        vault.clear_patient_profile()

        assert not vault.profile_exists()

        # API keys should still work
        key = vault.get_api_key("gemini")
        assert key == "test-key-123"

    print("✓ Vault clears profile but keeps API keys")


# ── Run All Tests ───────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Phase 5 Tests — Cloud Analysis Pipeline")
    print("=" * 60)

    # Cross-disciplinary
    test_cross_disciplinary_query_generation()
    test_cross_disciplinary_specialty_mapping()
    test_cross_disciplinary_constants()
    test_polypharmacy_detection()

    # Community insights
    test_community_search_term_building()
    test_community_subreddit_mapping()

    # Deep Research
    test_deep_research_significance_mapping()

    # Gemini fallback
    test_gemini_prompt_with_gap_context()

    # Session reset
    test_database_clear_patient_data()
    test_vault_clear_patient_profile()

    print()
    print("=" * 60)
    print("All Phase 5 tests passed ✓")
    print("=" * 60)
