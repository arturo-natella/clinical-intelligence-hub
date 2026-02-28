"""
Phase 9 Tests — Continuous Monitoring

Tests monitor structure, relevance assessment, and scheduler logic.
Actual API calls are not tested here (they require network access
and would be flaky in CI).
"""

import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models import (
    AlertSeverity,
    ClinicalTimeline,
    Demographics,
    Diagnosis,
    GeneticVariant,
    Medication,
    MedicationStatus,
    MonitoringAlert,
    PatientProfile,
    Provenance,
)


def _sample_profile() -> PatientProfile:
    """Create a sample patient profile for monitoring tests."""
    prov = Provenance(
        source_file="test.pdf", source_page=1,
        extraction_model="medgemma-27b", confidence=0.95,
    )
    return PatientProfile(
        demographics=Demographics(biological_sex="Female", birth_year=1963),
        clinical_timeline=ClinicalTimeline(
            medications=[
                Medication(
                    name="Metformin", dosage="500mg", frequency="twice daily",
                    status=MedicationStatus.ACTIVE, reason="Type 2 Diabetes",
                    start_date=date(2020, 3, 15), provenance=prov,
                ),
                Medication(
                    name="Lisinopril", dosage="10mg", frequency="daily",
                    status=MedicationStatus.ACTIVE, reason="Hypertension",
                    start_date=date(2019, 6, 1), provenance=prov,
                ),
            ],
            diagnoses=[
                Diagnosis(
                    name="Type 2 Diabetes", status="Active",
                    date_diagnosed=date(2020, 3, 1), provenance=prov,
                ),
                Diagnosis(
                    name="Essential Hypertension", status="Active",
                    date_diagnosed=date(2019, 5, 15), provenance=prov,
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


# ── Monitor Import Tests ───────────────────────────────────

def test_pubmed_monitor_import():
    """PubMed monitor imports correctly."""
    from src.monitoring.api_monitors.pubmed_monitor import PubMedMonitor
    monitor = PubMedMonitor()
    assert monitor is not None
    print("✓ PubMedMonitor imports")


def test_openfda_monitor_import():
    """OpenFDA monitor imports correctly."""
    from src.monitoring.api_monitors.openfda_monitor import OpenFDAMonitor
    monitor = OpenFDAMonitor()
    assert monitor is not None
    print("✓ OpenFDAMonitor imports")


def test_clinvar_monitor_import():
    """ClinVar monitor imports correctly."""
    from src.monitoring.api_monitors.clinvar_monitor import ClinVarMonitor
    monitor = ClinVarMonitor()
    assert monitor is not None
    print("✓ ClinVarMonitor imports")


def test_rxnorm_monitor_import():
    """RxNorm monitor imports correctly."""
    from src.monitoring.api_monitors.rxnorm_monitor import RxNormMonitor
    monitor = RxNormMonitor()
    assert monitor is not None
    print("✓ RxNormMonitor imports")


def test_clinical_trials_monitor_import():
    """ClinicalTrials.gov monitor imports correctly."""
    from src.monitoring.api_monitors.clinical_trials_monitor import ClinicalTrialsMonitor
    monitor = ClinicalTrialsMonitor()
    assert monitor is not None
    print("✓ ClinicalTrialsMonitor imports")


def test_pharmgkb_monitor_import():
    """PharmGKB monitor imports correctly."""
    from src.monitoring.api_monitors.pharmgkb_monitor import PharmGKBMonitor
    monitor = PharmGKBMonitor()
    assert monitor is not None
    print("✓ PharmGKBMonitor imports")


# ── PubMed Monitor Logic Tests ─────────────────────────────

def test_pubmed_builds_queries():
    """PubMed monitor builds queries from patient profile."""
    from src.monitoring.api_monitors.pubmed_monitor import PubMedMonitor
    monitor = PubMedMonitor()
    profile = _sample_profile()

    queries = monitor._build_queries(profile)
    assert len(queries) > 0, "Should build queries from patient data"

    # Should have medication safety queries
    med_queries = [q for q in queries if "Metformin" in q["query"] or "Lisinopril" in q["query"]]
    assert len(med_queries) >= 2, "Should query for each active medication"

    # Should have diagnosis queries
    dx_queries = [q for q in queries if "Type 2 Diabetes" in q["query"] or "Hypertension" in q["query"]]
    assert len(dx_queries) >= 1, "Should query for active diagnoses"

    # Should have genetic queries
    pgx_queries = [q for q in queries if "CYP2D6" in q["query"]]
    assert len(pgx_queries) >= 1, "Should query for actionable variants"

    print("✓ PubMed monitor builds queries from profile")


def test_pubmed_empty_profile():
    """PubMed monitor handles empty profile."""
    from src.monitoring.api_monitors.pubmed_monitor import PubMedMonitor
    monitor = PubMedMonitor()
    profile = PatientProfile()

    queries = monitor._build_queries(profile)
    assert queries == [], "Empty profile should produce no queries"

    print("✓ PubMed monitor handles empty profile")


# ── Relevance Assessment Tests ─────────────────────────────

def test_relevance_import():
    """RelevanceAssessor imports correctly."""
    from src.monitoring.alerting.relevance import RelevanceAssessor
    assessor = RelevanceAssessor()
    assert assessor is not None
    print("✓ RelevanceAssessor imports")


def test_relevance_medication_match():
    """RelevanceAssessor detects medication-relevant alerts."""
    from src.monitoring.alerting.relevance import RelevanceAssessor
    assessor = RelevanceAssessor()
    profile = _sample_profile()

    alert = MonitoringAlert(
        source="OpenFDA",
        title="Drug recall: Metformin batch",
        description="FDA recall for certain Metformin batches.",
        relevance_explanation="May affect patients taking Metformin.",
        severity=AlertSeverity.HIGH,
    )

    result = assessor.assess(alert, profile)
    assert result["relevant"] is True, "Should detect Metformin relevance"
    assert result["confidence"] > 0.5
    assert "metformin" in result["explanation"].lower()

    print("✓ RelevanceAssessor detects medication matches")


def test_relevance_condition_match():
    """RelevanceAssessor detects condition-relevant alerts."""
    from src.monitoring.alerting.relevance import RelevanceAssessor
    assessor = RelevanceAssessor()
    profile = _sample_profile()

    alert = MonitoringAlert(
        source="ADA",
        title="Updated diabetes guidelines",
        description="New ADA guidelines for Type 2 Diabetes management.",
        relevance_explanation="Updated clinical practice guidelines.",
        severity=AlertSeverity.MODERATE,
    )

    result = assessor.assess(alert, profile)
    assert result["relevant"] is True, "Should detect diabetes relevance"

    print("✓ RelevanceAssessor detects condition matches")


def test_relevance_genetic_match():
    """RelevanceAssessor detects genetics-relevant alerts."""
    from src.monitoring.alerting.relevance import RelevanceAssessor
    assessor = RelevanceAssessor()
    profile = _sample_profile()

    alert = MonitoringAlert(
        source="PharmGKB",
        title="CYP2D6 guideline update",
        description="Updated CYP2D6 pharmacogenomic dosing guidelines.",
        relevance_explanation="Updated PGx dosing guidance.",
        severity=AlertSeverity.HIGH,
    )

    result = assessor.assess(alert, profile)
    assert result["relevant"] is True, "Should detect CYP2D6 relevance"
    assert result["generate_addendum"] is True, "PGx alerts should generate addendums"

    print("✓ RelevanceAssessor detects genetic matches + addendum flag")


def test_relevance_irrelevant_alert():
    """RelevanceAssessor correctly identifies irrelevant alerts."""
    from src.monitoring.alerting.relevance import RelevanceAssessor
    assessor = RelevanceAssessor()
    profile = _sample_profile()

    alert = MonitoringAlert(
        source="PubMed",
        title="New study on Bevacizumab",
        description="Phase 3 trial results for Bevacizumab in oncology.",
        relevance_explanation="New oncology treatment data.",
        severity=AlertSeverity.LOW,
    )

    result = assessor.assess(alert, profile)
    assert result["relevant"] is False, "Should reject irrelevant alert"

    print("✓ RelevanceAssessor correctly rejects irrelevant alerts")


def test_relevance_filter():
    """RelevanceAssessor filters a batch of alerts."""
    from src.monitoring.alerting.relevance import RelevanceAssessor
    assessor = RelevanceAssessor()
    profile = _sample_profile()

    alerts = [
        MonitoringAlert(source="OpenFDA", title="Metformin recall",
                        description="Recall for Metformin.",
                        relevance_explanation="Drug recall notice.",
                        severity=AlertSeverity.HIGH),
        MonitoringAlert(source="PubMed", title="Unrelated oncology study",
                        description="Cancer therapy results.",
                        relevance_explanation="Oncology research.",
                        severity=AlertSeverity.LOW),
        MonitoringAlert(source="ClinVar", title="CYP2D6 reclassification",
                        description="Updated CYP2D6 variant interpretation.",
                        relevance_explanation="Genetic variant update.",
                        severity=AlertSeverity.MODERATE),
    ]

    relevant = assessor.filter_alerts(alerts, profile)
    assert len(relevant) == 2, f"Should find 2 relevant (got {len(relevant)})"

    # Should be sorted by severity (HIGH before MODERATE)
    assert relevant[0][0].severity == AlertSeverity.HIGH
    assert relevant[1][0].severity == AlertSeverity.MODERATE

    print("✓ RelevanceAssessor filters and sorts alerts correctly")


# ── Scheduler Tests ────────────────────────────────────────

def test_scheduler_import():
    """MonitoringScheduler imports correctly."""
    from src.monitoring.scheduler import MonitoringScheduler
    assert MonitoringScheduler is not None
    print("✓ MonitoringScheduler imports")


def test_scheduler_init():
    """MonitoringScheduler initializes correctly."""
    from src.monitoring.scheduler import MonitoringScheduler

    with tempfile.TemporaryDirectory() as tmpdir:
        scheduler = MonitoringScheduler(Path(tmpdir), "test-passphrase")
        assert scheduler.data_dir == Path(tmpdir)

    print("✓ MonitoringScheduler initializes")


def test_scheduler_has_all_runners():
    """MonitoringScheduler has runners for all monitors."""
    from src.monitoring.scheduler import MonitoringScheduler

    with tempfile.TemporaryDirectory() as tmpdir:
        scheduler = MonitoringScheduler(Path(tmpdir), "test")

        assert hasattr(scheduler, "_run_pubmed")
        assert hasattr(scheduler, "_run_openfda")
        assert hasattr(scheduler, "_run_clinvar")
        assert hasattr(scheduler, "_run_rxnorm")
        assert hasattr(scheduler, "_run_clinical_trials")
        assert hasattr(scheduler, "_run_pharmgkb")
        assert hasattr(scheduler, "run_api_monitors")
        assert hasattr(scheduler, "run_playwright_monitors")
        assert hasattr(scheduler, "run_all")

    print("✓ MonitoringScheduler has all 6 API monitor runners + orchestration methods")


# ── Guideline Monitor Test ─────────────────────────────────

def test_guideline_monitor_import():
    """GuidelineMonitor imports (even if Playwright isn't installed)."""
    try:
        from src.monitoring.playwright_monitors.guideline_monitor import GuidelineMonitor
        monitor = GuidelineMonitor()
        assert monitor is not None
        print("✓ GuidelineMonitor imports")
    except ImportError:
        print("⊘ GuidelineMonitor skipped (Playwright not installed)")


# ── Run All Tests ────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Phase 9 Tests — Continuous Monitoring")
    print("=" * 60)

    # Monitor imports
    test_pubmed_monitor_import()
    test_openfda_monitor_import()
    test_clinvar_monitor_import()
    test_rxnorm_monitor_import()
    test_clinical_trials_monitor_import()
    test_pharmgkb_monitor_import()

    # PubMed logic
    test_pubmed_builds_queries()
    test_pubmed_empty_profile()

    # Relevance assessment
    test_relevance_import()
    test_relevance_medication_match()
    test_relevance_condition_match()
    test_relevance_genetic_match()
    test_relevance_irrelevant_alert()
    test_relevance_filter()

    # Scheduler
    test_scheduler_import()
    test_scheduler_init()
    test_scheduler_has_all_runners()

    # Playwright
    test_guideline_monitor_import()

    print()
    print("=" * 60)
    print("All Phase 9 tests passed ✓")
    print("=" * 60)
