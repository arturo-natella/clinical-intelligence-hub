"""
Tests for Clinical Intelligence Hub — Anomaly Investigation Engine

Covers:
  - Anomaly detection with known spikes
  - Anomaly detection with direction reversals
  - No anomalies on clean trajectories
  - Investigation window calculation per lab type
  - Event aggregation from multiple sources
  - Empty investigation (no events found)
  - Correlation summary generation
"""

import sys
from pathlib import Path

# Ensure src/ is importable
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
from src.analysis.anomaly_investigator import AnomalyInvestigator, INVESTIGATION_WINDOWS


# ── Fixtures ──────────────────────────────────────────────────

def _make_trajectory(data_points, trend_direction="rising", r_squared=0.85):
    """
    Build a minimal trajectory dict that mimics TrajectoryForecaster output.
    Computes trend_line from a simple linear regression of the data points.
    """
    if len(data_points) < 2:
        return {
            "test_name": "TestLab",
            "data_points": data_points,
            "trend": {"direction": trend_direction, "r_squared": r_squared},
            "trend_line": [],
            "reference_range": {"low": 4.0, "high": 5.6},
        }

    # Simple regression
    from datetime import datetime
    first_date = datetime.strptime(data_points[0]["date"], "%Y-%m-%d").date()
    xs = []
    ys = []
    for dp in data_points:
        d = datetime.strptime(dp["date"], "%Y-%m-%d").date()
        xs.append((d - first_date).days)
        ys.append(dp["value"])

    n = len(xs)
    sum_x = sum(xs)
    sum_y = sum(ys)
    sum_xy = sum(x * y for x, y in zip(xs, ys))
    sum_x2 = sum(x * x for x in xs)
    denom = n * sum_x2 - sum_x * sum_x

    if denom == 0:
        slope = 0
        intercept = sum_y / n
    else:
        slope = (n * sum_xy - sum_x * sum_y) / denom
        intercept = (sum_y - slope * sum_x) / n

    last_x = xs[-1]
    proj_x = last_x + 365  # project 12 months

    return {
        "test_name": "TestLab",
        "data_points": data_points,
        "trend": {
            "direction": trend_direction,
            "slope_per_month": round(slope * 30.44, 4),
            "r_squared": r_squared,
            "confidence": "high" if r_squared > 0.7 else "moderate",
        },
        "trend_line": [
            {"date": data_points[0]["date"], "value": round(intercept, 2)},
            {"date": _add_days(data_points[0]["date"], proj_x), "value": round(slope * proj_x + intercept, 2)},
        ],
        "reference_range": {"low": 4.0, "high": 5.6},
    }


def _add_days(iso_date, days):
    """Add days to an ISO date string."""
    from datetime import datetime, timedelta
    d = datetime.strptime(iso_date, "%Y-%m-%d").date()
    return (d + timedelta(days=days)).isoformat()


@pytest.fixture
def investigator():
    return AnomalyInvestigator()


@pytest.fixture
def clean_trajectory():
    """A trajectory with no anomalies — smooth linear progression."""
    return _make_trajectory([
        {"date": "2025-01-01", "value": 5.0, "days_from_first": 0},
        {"date": "2025-03-01", "value": 5.2, "days_from_first": 59},
        {"date": "2025-05-01", "value": 5.4, "days_from_first": 120},
        {"date": "2025-07-01", "value": 5.6, "days_from_first": 181},
        {"date": "2025-09-01", "value": 5.8, "days_from_first": 243},
    ], trend_direction="rising")


@pytest.fixture
def spike_trajectory():
    """A trajectory with a clear spike (outlier) at the 4th point."""
    return _make_trajectory([
        {"date": "2025-01-01", "value": 5.0, "days_from_first": 0},
        {"date": "2025-03-01", "value": 5.2, "days_from_first": 59},
        {"date": "2025-05-01", "value": 5.4, "days_from_first": 120},
        {"date": "2025-07-01", "value": 8.5, "days_from_first": 181},   # <-- spike
        {"date": "2025-09-01", "value": 5.8, "days_from_first": 243},
    ], trend_direction="rising")


@pytest.fixture
def reversal_trajectory():
    """A trajectory showing improvement then sudden worsening."""
    return _make_trajectory([
        {"date": "2025-01-01", "value": 9.0, "days_from_first": 0},
        {"date": "2025-03-01", "value": 8.5, "days_from_first": 59},
        {"date": "2025-05-01", "value": 8.0, "days_from_first": 120},
        {"date": "2025-07-01", "value": 7.5, "days_from_first": 181},
        {"date": "2025-09-01", "value": 8.8, "days_from_first": 243},   # <-- reversal
    ], trend_direction="falling")


@pytest.fixture
def rich_profile():
    """Profile data with events across the clinical timeline."""
    return {
        "clinical_timeline": {
            "diagnoses": [
                {
                    "name": "Type 2 Diabetes",
                    "date_diagnosed": "2025-06-15",
                    "severity": "high",
                    "icd10": "E11.65",
                    "provider": "Dr. Smith",
                    "source_file": "discharge_summary.pdf",
                    "source_page": 3,
                },
                {
                    "name": "Hypertension",
                    "date_diagnosed": "2024-01-10",
                    "severity": "moderate",
                    "provider": "Dr. Jones",
                },
            ],
            "procedures": [
                {
                    "name": "Cardiac Stress Test",
                    "procedure_date": "2025-06-20",
                    "provider": "Dr. Chen",
                    "notes": "Normal results",
                    "source_file": "cardiology_report.pdf",
                    "source_page": 1,
                },
            ],
            "medications": [
                {
                    "name": "Metformin",
                    "dose": "1000mg",
                    "frequency": "twice daily",
                    "start_date": "2025-06-15",
                    "status": "active",
                    "prescriber": "Dr. Smith",
                    "reason": "Glycemic control",
                },
                {
                    "name": "Glipizide",
                    "dose": "5mg",
                    "start_date": "2024-01-01",
                    "end_date": "2025-06-10",
                    "status": "discontinued",
                    "prescriber": "Dr. Smith",
                    "reason": "Replaced by metformin",
                },
            ],
            "symptoms": [
                {
                    "symptom_name": "Fatigue",
                    "episodes": [
                        {
                            "episode_date": "2025-06-18",
                            "intensity": "high",
                            "description": "Extreme tiredness after meals",
                            "triggers": "High-carb lunch",
                        },
                        {
                            "episode_date": "2025-06-25",
                            "intensity": "mid",
                            "description": "Afternoon energy crash",
                            "triggers": "Skipped breakfast",
                        },
                    ],
                },
                {
                    "symptom_name": "Blurred vision",
                    "episodes": [
                        {
                            "episode_date": "2025-06-22",
                            "intensity": "mid",
                            "description": "Difficulty reading fine print",
                            "triggers": "Morning, after high glucose",
                        },
                    ],
                },
            ],
            "labs": [
                {"test_name": "HbA1c", "value": "8.5", "date": "2025-07-01"},
                {"test_name": "HbA1c", "value": "7.8", "date": "2025-04-01"},
                {"test_name": "HbA1c", "value": "7.5", "date": "2025-01-01"},
            ],
        },
    }


# ── Test: Anomaly Detection with Known Spike ─────────────────

class TestAnomalyDetection:

    def test_detects_spike(self, investigator, spike_trajectory):
        anomalies = investigator.detect_anomalies(spike_trajectory)
        assert len(anomalies) >= 1, "Should detect at least one anomaly"

        # The spike at 2025-07-01 with value 8.5 should be flagged
        spike = next(
            (a for a in anomalies if a["date"] == "2025-07-01"), None
        )
        assert spike is not None, "Should flag the 2025-07-01 spike"
        assert spike["value"] == 8.5
        assert spike["direction"] == "spike"
        assert spike["severity"] in ("major", "moderate")
        assert spike["deviation"] > 0

    def test_detects_direction_reversal(self, investigator, reversal_trajectory):
        anomalies = investigator.detect_anomalies(reversal_trajectory)
        # The reversal at 2025-09-01 should be detected
        # It may be detected by residual OR reversal logic
        reversal = next(
            (a for a in anomalies if a["date"] == "2025-09-01"), None
        )
        assert reversal is not None, (
            "Should flag the direction reversal at 2025-09-01"
        )
        assert reversal["value"] == 8.8

    def test_no_anomalies_on_clean_trajectory(self, investigator, clean_trajectory):
        anomalies = investigator.detect_anomalies(clean_trajectory)
        assert len(anomalies) == 0, (
            "Clean linear trajectory should produce no anomalies"
        )

    def test_returns_expected_fields(self, investigator, spike_trajectory):
        anomalies = investigator.detect_anomalies(spike_trajectory)
        assert len(anomalies) >= 1
        a = anomalies[0]
        assert "date" in a
        assert "value" in a
        assert "expected" in a
        assert "deviation" in a
        assert "deviation_pct" in a
        assert "direction" in a
        assert "severity" in a

    def test_too_few_points_returns_empty(self, investigator):
        traj = _make_trajectory([
            {"date": "2025-01-01", "value": 5.0, "days_from_first": 0},
            {"date": "2025-03-01", "value": 5.2, "days_from_first": 59},
        ])
        anomalies = investigator.detect_anomalies(traj)
        assert anomalies == []


# ── Test: Investigation Window Calculation ────────────────────

class TestInvestigationWindows:

    def test_hba1c_window_is_90(self, investigator):
        assert investigator._get_window_days("HbA1c") == 90

    def test_glucose_window_is_7(self, investigator):
        assert investigator._get_window_days("Glucose") == 7
        assert investigator._get_window_days("Fasting Glucose") == 7

    def test_crp_window_is_14(self, investigator):
        assert investigator._get_window_days("CRP") == 14

    def test_tsh_window_is_60(self, investigator):
        assert investigator._get_window_days("TSH") == 60

    def test_liver_enzymes_window_is_30(self, investigator):
        assert investigator._get_window_days("ALT") == 30
        assert investigator._get_window_days("AST") == 30

    def test_lipid_window_is_60(self, investigator):
        assert investigator._get_window_days("LDL") == 60
        assert investigator._get_window_days("HDL") == 60
        assert investigator._get_window_days("Triglycerides") == 60

    def test_unknown_test_gets_default(self, investigator):
        assert investigator._get_window_days("SomeObscureLab") == 60

    def test_partial_match(self, investigator):
        # "hemoglobin a1c" should match even with different casing
        assert investigator._get_window_days("Hemoglobin A1c") == 90

    def test_kidney_window(self, investigator):
        assert investigator._get_window_days("eGFR") == 60
        assert investigator._get_window_days("Creatinine") == 60


# ── Test: Event Aggregation from Multiple Sources ─────────────

class TestEventAggregation:

    def test_gathers_events_within_window(self, investigator, rich_profile):
        result = investigator.investigate(
            anomaly_date="2025-07-01",
            test_name="HbA1c",
            profile_data=rich_profile,
        )

        assert result["window"]["days"] == 90
        assert result["event_count"] > 0

        events = result["events_by_source"]

        # Should find the diagnosis from 2025-06-15
        dx_dates = [r["date"] for r in events["medical_records"]]
        assert "2025-06-15" in dx_dates

        # Should find the procedure from 2025-06-20
        proc_dates = [r["date"] for r in events["medical_records"]]
        assert "2025-06-20" in proc_dates

        # Should find medication changes
        med_dates = [m["date"] for m in events["medication_changes"]]
        assert "2025-06-15" in med_dates  # Metformin started
        assert "2025-06-10" in med_dates  # Glipizide stopped

        # Should find symptom reports
        sym_dates = [s["date"] for s in events["symptom_reports"]]
        assert "2025-06-18" in sym_dates
        assert "2025-06-25" in sym_dates

    def test_event_provenance(self, investigator, rich_profile):
        result = investigator.investigate(
            anomaly_date="2025-07-01",
            test_name="HbA1c",
            profile_data=rich_profile,
        )
        events = result["events_by_source"]

        # Diagnosis should have provenance
        dx = next(
            (r for r in events["medical_records"] if r["event_type"] == "diagnosis"),
            None
        )
        assert dx is not None
        assert "provenance" in dx
        assert dx["provenance"].get("source_file") == "discharge_summary.pdf"
        assert dx["provenance"].get("source_page") == 3

    def test_excludes_events_outside_window(self, investigator, rich_profile):
        result = investigator.investigate(
            anomaly_date="2025-07-01",
            test_name="HbA1c",
            profile_data=rich_profile,
        )
        events = result["events_by_source"]

        # The hypertension diagnosis from 2024-01-10 should NOT be included
        # (outside 90-day window from 2025-07-01)
        dx_dates = [r["date"] for r in events["medical_records"]]
        assert "2024-01-10" not in dx_dates


# ── Test: Empty Investigation ─────────────────────────────────

class TestEmptyInvestigation:

    def test_no_events_in_window(self, investigator):
        """Profile with events but none in the investigation window."""
        profile = {
            "clinical_timeline": {
                "diagnoses": [
                    {"name": "Old diagnosis", "date_diagnosed": "2020-01-01"},
                ],
                "procedures": [],
                "medications": [],
                "symptoms": [],
                "labs": [
                    {"test_name": "HbA1c", "value": "7.0", "date": "2025-07-01"},
                ],
            },
        }
        result = investigator.investigate(
            anomaly_date="2025-07-01",
            test_name="HbA1c",
            profile_data=profile,
        )
        assert result["event_count"] == 0
        assert len(result["events_by_source"]["medical_records"]) == 0
        assert len(result["events_by_source"]["medication_changes"]) == 0
        assert len(result["events_by_source"]["symptom_reports"]) == 0

    def test_empty_profile(self, investigator):
        result = investigator.investigate(
            anomaly_date="2025-07-01",
            test_name="HbA1c",
            profile_data={},
        )
        assert result["event_count"] == 0

    def test_invalid_date(self, investigator):
        result = investigator.investigate(
            anomaly_date="not-a-date",
            test_name="HbA1c",
            profile_data={},
        )
        assert result["window"]["days"] == 0


# ── Test: Correlation Summary ─────────────────────────────────

class TestCorrelationSummary:

    def test_summary_with_events(self, investigator, rich_profile):
        result = investigator.investigate(
            anomaly_date="2025-07-01",
            test_name="HbA1c",
            profile_data=rich_profile,
        )
        summary = result["correlation_summary"]
        assert "discuss_because" in summary
        assert "how_to_bring_up" in summary
        assert "HbA1c" in summary["discuss_because"]
        assert "doctor" in summary["discuss_because"].lower()
        assert len(summary["discuss_because"]) > 20

    def test_summary_without_events(self, investigator):
        result = investigator.investigate(
            anomaly_date="2025-07-01",
            test_name="HbA1c",
            profile_data={"clinical_timeline": {"diagnoses": [], "procedures": [], "medications": [], "symptoms": [], "labs": []}},
        )
        summary = result["correlation_summary"]
        assert "discuss_because" in summary
        assert "how_to_bring_up" in summary
        # Should mention no events found
        assert "No recorded events" in summary["discuss_because"] or "no" in summary["discuss_because"].lower()

    def test_summary_mentions_test_name(self, investigator, rich_profile):
        result = investigator.investigate(
            anomaly_date="2025-07-01",
            test_name="HbA1c",
            profile_data=rich_profile,
        )
        summary = result["correlation_summary"]
        assert "HbA1c" in summary["discuss_because"]
        assert "HbA1c" in summary["how_to_bring_up"]

    def test_conversation_starter_is_first_person(self, investigator, rich_profile):
        result = investigator.investigate(
            anomaly_date="2025-07-01",
            test_name="HbA1c",
            profile_data=rich_profile,
        )
        starter = result["correlation_summary"]["how_to_bring_up"]
        assert starter.startswith("I "), (
            "Conversation starter should be first-person: " + starter
        )
