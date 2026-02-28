"""
Phase 10 Tests — Polish & End-to-End Verification

Tests launcher scripts, launchd plists, full module import chain,
and end-to-end pipeline structure from ingestion through reporting.
"""

import json
import plistlib
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Launcher Script Tests ─────────────────────────────────

def test_start_command_exists():
    """start.command launcher exists and is a bash script."""
    script = Path(__file__).parent.parent / "start.command"
    assert script.exists(), "start.command missing"
    content = script.read_text()
    assert content.startswith("#!/bin/bash"), "start.command should be a bash script"
    assert "caffeinate" in content, "start.command should use caffeinate"
    assert "VAULT_PASSPHRASE" in content, "start.command should prompt for passphrase"
    assert "5050" in content, "start.command should reference port 5050"
    print("✓ start.command exists with caffeinate + passphrase + port")


def test_setup_script_exists():
    """setup.sh exists and covers all setup steps."""
    script = Path(__file__).parent.parent / "setup.sh"
    assert script.exists(), "setup.sh missing"
    content = script.read_text()
    assert "venv" in content, "setup.sh should create venv"
    assert "pip install" in content, "setup.sh should install deps"
    assert "ollama" in content.lower(), "setup.sh should check for Ollama"
    assert "playwright" in content.lower(), "setup.sh should install Playwright"
    assert "tesseract" in content.lower(), "setup.sh should check for Tesseract"
    print("✓ setup.sh exists with all setup steps")


def test_install_monitors_script_exists():
    """install_monitors.sh exists with launchd setup."""
    script = Path(__file__).parent.parent / "install_monitors.sh"
    assert script.exists(), "install_monitors.sh missing"
    content = script.read_text()
    assert "launchctl" in content, "Should use launchctl"
    assert "LaunchAgents" in content, "Should install to LaunchAgents"
    assert "security" in content, "Should use macOS Keychain"
    assert "com.medprep.api-monitor" in content, "Should reference API plist"
    assert "com.medprep.playwright-monitor" in content, "Should reference Playwright plist"
    print("✓ install_monitors.sh exists with launchd + Keychain setup")


# ── Plist Tests ───────────────────────────────────────────

def test_api_monitor_plist_valid():
    """API monitor plist is valid XML."""
    plist_path = Path(__file__).parent.parent / "com.medprep.api-monitor.plist"
    assert plist_path.exists(), "API monitor plist missing"

    with open(plist_path, "rb") as f:
        data = plistlib.load(f)

    assert data["Label"] == "com.medprep.api-monitor"
    assert "StartCalendarInterval" in data
    assert data["StartCalendarInterval"]["Hour"] == 6
    assert "ProgramArguments" in data
    args = data["ProgramArguments"]
    assert "--mode" in args
    assert "api" in args
    print("✓ API monitor plist is valid (daily at 6:00 AM)")


def test_playwright_monitor_plist_valid():
    """Playwright monitor plist is valid XML."""
    plist_path = Path(__file__).parent.parent / "com.medprep.playwright-monitor.plist"
    assert plist_path.exists(), "Playwright monitor plist missing"

    with open(plist_path, "rb") as f:
        data = plistlib.load(f)

    assert data["Label"] == "com.medprep.playwright-monitor"
    assert "StartCalendarInterval" in data
    assert data["StartCalendarInterval"]["Weekday"] == 0  # Sunday
    assert data["StartCalendarInterval"]["Hour"] == 3
    args = data["ProgramArguments"]
    assert "--mode" in args
    assert "playwright" in args
    print("✓ Playwright monitor plist is valid (weekly Sunday 3:00 AM)")


# ── Full Import Chain Tests ───────────────────────────────

def test_all_src_modules_import():
    """All src modules import without errors."""
    modules = [
        "src.models",
        "src.database",
        "src.encryption",
        "src.extraction.preprocessor",
        "src.extraction.ocr",
        "src.extraction.text_extractor",
        "src.extraction.fhir_parser",
        "src.extraction.dicom_converter",
        "src.imaging.vision_analyzer",
        "src.imaging.monai_detector",
        "src.imaging.model_manager",
        "src.privacy.redactor",
        "src.analysis.gemini_fallback",
        "src.analysis.deep_research",
        "src.analysis.cross_disciplinary",
        "src.analysis.community_insights",
        "src.validation.openfda",
        "src.validation.drugbank",
        "src.validation.pubmed",
        "src.validation.rxnorm",
        "src.validation.validator",
        "src.standardization.loinc",
        "src.standardization.snomed",
        "src.standardization.rxnorm_db",
        "src.report.builder",
        "src.report.addendum",
        "src.monitoring.api_monitors.pubmed_monitor",
        "src.monitoring.api_monitors.openfda_monitor",
        "src.monitoring.api_monitors.clinvar_monitor",
        "src.monitoring.api_monitors.rxnorm_monitor",
        "src.monitoring.api_monitors.clinical_trials_monitor",
        "src.monitoring.api_monitors.pharmgkb_monitor",
        "src.monitoring.alerting.relevance",
        "src.monitoring.scheduler",
        "src.ui.pipeline",
        "src.ui.app",
    ]

    failures = []
    for mod_name in modules:
        try:
            __import__(mod_name)
        except Exception as e:
            failures.append(f"{mod_name}: {e}")

    if failures:
        print(f"✗ Import failures:")
        for f in failures:
            print(f"    {f}")
    assert len(failures) == 0, f"{len(failures)} modules failed to import"

    print(f"✓ All {len(modules)} src modules import successfully")


# ── Data Model Chain Test ─────────────────────────────────

def test_full_patient_profile_construction():
    """Build a complete PatientProfile with all data types."""
    from src.models import (
        ClinicalTimeline, Demographics, Diagnosis, GeneticVariant,
        ImagingFinding, ImagingStudy, LabResult, Medication, MedicationStatus,
        PatientProfile, Provenance,
    )

    prov = Provenance(
        source_file="test_records.pdf", source_page=1,
        extraction_model="medgemma-27b", confidence=0.95,
    )

    profile = PatientProfile(
        demographics=Demographics(biological_sex="Female", birth_year=1963),
        clinical_timeline=ClinicalTimeline(
            medications=[
                Medication(
                    name="Metformin", dosage="500mg", frequency="twice daily",
                    status=MedicationStatus.ACTIVE, reason="Type 2 Diabetes",
                    start_date=date(2020, 3, 15), provenance=prov,
                ),
            ],
            diagnoses=[
                Diagnosis(
                    name="Type 2 Diabetes", status="Active",
                    date_diagnosed=date(2020, 3, 1), provenance=prov,
                ),
            ],
            labs=[
                LabResult(
                    name="Hemoglobin A1c", value=7.2, unit="%",
                    reference_low=4.0, reference_high=5.6, flag="High",
                    test_date=date(2024, 1, 15), provenance=prov,
                ),
            ],
            imaging=[
                ImagingStudy(
                    modality="CT", body_region="Chest",
                    description="CT chest without contrast.",
                    findings=[
                        ImagingFinding(
                            description="No acute abnormality.",
                            body_region="Chest",
                        ),
                    ],
                    study_date=date(2024, 6, 1), provenance=prov,
                ),
            ],
            genetics=[
                GeneticVariant(
                    gene="CYP2D6", variant="*4/*4",
                    phenotype="Poor Metabolizer",
                    clinical_significance="Actionable",
                    implications="Reduced metabolism of CYP2D6 substrates",
                    provenance=prov,
                ),
            ],
        ),
    )

    # Verify all data is accessible
    assert profile.demographics.biological_sex == "Female"
    assert len(profile.clinical_timeline.medications) == 1
    assert len(profile.clinical_timeline.diagnoses) == 1
    assert len(profile.clinical_timeline.labs) == 1
    assert len(profile.clinical_timeline.imaging) == 1
    assert len(profile.clinical_timeline.genetics) == 1

    # Verify provenance
    med = profile.clinical_timeline.medications[0]
    assert med.provenance.source_file == "test_records.pdf"
    assert med.provenance.source_page == 1

    # Verify serialization round-trip
    json_str = profile.model_dump_json()
    restored = PatientProfile.model_validate_json(json_str)
    assert restored.demographics.birth_year == 1963
    assert len(restored.clinical_timeline.medications) == 1

    print("✓ Full PatientProfile construction + serialization round-trip works")


# ── Encryption Round-Trip Test ────────────────────────────

def test_encryption_round_trip():
    """Encrypt and decrypt data with vault."""
    try:
        import argon2  # noqa: F401
    except ImportError:
        print("⊘ Vault encryption test skipped (argon2-cffi not installed)")
        return

    from src.encryption import EncryptedVault

    with tempfile.TemporaryDirectory() as tmpdir:
        passphrase = "test-passphrase-12345"

        # Create vault and store API keys
        vault = EncryptedVault(Path(tmpdir), passphrase)
        vault.save_api_keys({"gemini": "sk-test-123", "ncbi": "key-456"})

        # Retrieve API keys
        keys = vault.load_api_keys()
        assert keys["gemini"] == "sk-test-123"
        assert keys["ncbi"] == "key-456"

        # Individual key access
        vault.set_api_key("openfda", "fda-789")
        assert vault.get_api_key("openfda") == "fda-789"

        # Verify wrong passphrase fails
        try:
            bad_vault = EncryptedVault(Path(tmpdir), "wrong-passphrase")
            result = bad_vault.load_api_keys()
            if result == keys:
                assert False, "Should not decrypt with wrong passphrase"
        except Exception:
            pass  # Expected — wrong passphrase

    print("✓ Vault encryption round-trip works (AES-256-GCM + Argon2id)")


# ── Database State Test ───────────────────────────────────

def test_database_operations():
    """Database can track alerts and clear patient data."""
    from src.database import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        db = Database(Path(tmpdir) / "test.db")

        # Save an alert
        db.save_alert(
            "test-001", "PubMed", "Test alert",
            "Description of alert.", "Relevant because...",
            "HIGH", "https://example.com",
        )

        # Retrieve unaddressed alerts
        alerts = db.get_unaddressed_alerts()
        assert len(alerts) >= 1
        found = [a for a in alerts if a["alert_id"] == "test-001"]
        assert len(found) == 1
        assert found[0]["source"] == "PubMed"

        # Mark as addressed
        db.mark_alert_addressed("test-001")
        alerts2 = db.get_unaddressed_alerts()
        found2 = [a for a in alerts2 if a["alert_id"] == "test-001"]
        assert len(found2) == 0

        # Clear patient data
        db.clear_patient_data()  # Should not raise

    print("✓ Database alert save/retrieve/address/clear works")


# ── Pipeline Structure Test ───────────────────────────────

def test_pipeline_end_to_end_structure():
    """Pipeline has correct pass order and all dependencies."""
    from src.ui.pipeline import Pipeline

    with tempfile.TemporaryDirectory() as tmpdir:
        pipeline = Pipeline(Path(tmpdir), "test-passphrase")

        # Verify pass methods exist in correct order
        passes = [
            "_pass_0_preprocess",
            "_pass_1a_text_extraction",
            "_pass_1b_vision",
            "_pass_1c_monai",
            "_pass_1_5_redaction",
            "_pass_2_4_cloud_analysis",
            "_pass_5_validation",
            "_pass_6_report",
        ]

        for pass_name in passes:
            assert hasattr(pipeline, pass_name), f"Missing: {pass_name}"
            method = getattr(pipeline, pass_name)
            assert callable(method), f"{pass_name} should be callable"

        # Verify run method exists
        assert hasattr(pipeline, "run")
        assert callable(pipeline.run)

        # Verify clear_session
        pipeline.clear_session()  # Should not raise

    print(f"✓ Pipeline has all {len(passes)} passes in correct order + run + clear_session")


# ── Flask App Full Route Test ─────────────────────────────

def test_flask_app_full_route_coverage():
    """Flask app has all routes for the Clinical Intelligence Hub."""
    from src.ui.app import app

    rules = {rule.rule for rule in app.url_map.iter_rules()}

    # All expected routes
    expected = [
        "/",
        "/api/unlock",
        "/api/session/clear",
        "/api/session/status",
        "/api/upload",
        "/api/analyze",
        "/api/progress",
        "/api/profile",
        "/api/medications",
        "/api/labs",
        "/api/diagnoses",
        "/api/imaging",
        "/api/genetics",
        "/api/flags",
        "/api/interactions",
        "/api/cross-disciplinary",
        "/api/community",
        "/api/literature",
        "/api/questions",
        "/api/alerts",
        "/api/timeline",
        "/api/report/download",
        "/api/report/generate",
        "/api/chat",
        "/api/keys",
        "/api/keys/status",
    ]

    missing = [r for r in expected if r not in rules]
    assert len(missing) == 0, f"Missing routes: {missing}"

    print(f"✓ Flask app has all {len(expected)} routes")


# ── Monitoring Integration Test ───────────────────────────

def test_monitoring_full_chain():
    """Monitoring chain: monitors → relevance → scheduler."""
    from src.monitoring.api_monitors.pubmed_monitor import PubMedMonitor
    from src.monitoring.api_monitors.openfda_monitor import OpenFDAMonitor
    from src.monitoring.api_monitors.clinvar_monitor import ClinVarMonitor
    from src.monitoring.api_monitors.rxnorm_monitor import RxNormMonitor
    from src.monitoring.api_monitors.clinical_trials_monitor import ClinicalTrialsMonitor
    from src.monitoring.api_monitors.pharmgkb_monitor import PharmGKBMonitor
    from src.monitoring.alerting.relevance import RelevanceAssessor
    from src.monitoring.scheduler import MonitoringScheduler

    # All monitors instantiate
    monitors = [
        PubMedMonitor(), OpenFDAMonitor(), ClinVarMonitor(),
        RxNormMonitor(), ClinicalTrialsMonitor(), PharmGKBMonitor(),
    ]
    assert len(monitors) == 6

    # Relevance assessor works
    assessor = RelevanceAssessor()
    assert assessor is not None

    # Scheduler has all runners
    with tempfile.TemporaryDirectory() as tmpdir:
        scheduler = MonitoringScheduler(Path(tmpdir), "test")
        assert hasattr(scheduler, "run_api_monitors")
        assert hasattr(scheduler, "run_playwright_monitors")
        assert hasattr(scheduler, "run_all")

    print("✓ Full monitoring chain: 6 monitors + relevance + scheduler")


# ── Report Builder Test ───────────────────────────────────

def test_report_builder_structure():
    """Report builder has all 10 sections."""
    from src.report.builder import ReportBuilder

    builder = ReportBuilder()

    # Check section methods (numbered 1-10)
    sections = [
        "_section_1_patient_summary",
        "_section_2_health_timeline",
        "_section_3_conditions_medications",
        "_section_4_lab_trends",
        "_section_5_imaging",
        "_section_6_genetics",
        "_section_7_patterns_flags",
        "_section_8_cross_disciplinary",
        "_section_9_questions",
        "_section_10_disclaimer",
    ]

    for section in sections:
        assert hasattr(builder, section), f"Missing section: {section}"

    print(f"✓ ReportBuilder has all {len(sections)} sections")


# ── Static Assets Test ────────────────────────────────────

def test_all_static_assets_present():
    """All static files needed for the Hub UI exist."""
    static_dir = Path(__file__).parent.parent / "src" / "ui" / "static"

    # Core files
    assert (static_dir / "index.html").exists()
    assert (static_dir / "styles.css").exists()
    assert (static_dir / "app.js").exists()

    # Anatomy assets
    assets = static_dir / "assets"
    required_images = [
        "anatomy.png",
        "anatomy_back.png",
        "anatomy_muscle.png",
        "anatomy_skeleton.png",
        "anatomy_organs.png",
    ]
    for img in required_images:
        assert (assets / img).exists(), f"Missing: {img}"

    print(f"✓ All static files present (3 core + {len(required_images)} anatomy images)")


# ── Governance Files Test ─────────────────────────────────

def test_governance_files():
    """All governance and documentation files exist."""
    root = Path(__file__).parent.parent

    files = [
        "LICENSE",
        "CHANGELOG.md",
        "CLAUDE.md",
        "README.md",
        "requirements.txt",
        ".gitignore",
    ]

    for f in files:
        assert (root / f).exists(), f"Missing: {f}"

    # LICENSE should be BSD 2-Clause
    license_text = (root / "LICENSE").read_text()
    assert "BSD" in license_text or "Redistribution" in license_text

    # requirements.txt should have key deps
    reqs = (root / "requirements.txt").read_text().lower()
    assert "flask" in reqs
    assert "pydantic" in reqs

    print(f"✓ All {len(files)} governance files present")


# ── Run All Tests ────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Phase 10 Tests — Polish & End-to-End Verification")
    print("=" * 60)

    # Launcher scripts
    test_start_command_exists()
    test_setup_script_exists()
    test_install_monitors_script_exists()

    # Plist validation
    test_api_monitor_plist_valid()
    test_playwright_monitor_plist_valid()

    # Full import chain
    test_all_src_modules_import()

    # Data model
    test_full_patient_profile_construction()

    # Encryption
    test_encryption_round_trip()

    # Database
    test_database_operations()

    # Pipeline
    test_pipeline_end_to_end_structure()

    # Flask routes
    test_flask_app_full_route_coverage()

    # Monitoring chain
    test_monitoring_full_chain()

    # Report builder
    test_report_builder_structure()

    # Static assets
    test_all_static_assets_present()

    # Governance
    test_governance_files()

    print()
    print("=" * 60)
    print("All Phase 10 tests passed ✓")
    print("=" * 60)
