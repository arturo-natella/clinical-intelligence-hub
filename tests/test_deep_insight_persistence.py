"""Persistence, retrieval, and report coverage for local deep insights."""

from pathlib import Path

import pytest

from src.analysis import deep_insights
from src.models import (
    AnalysisResults,
    DeepInsightSnapshot,
    PatientProfile,
    Provenance,
)


def _profile_dict() -> dict:
    return {
        "demographics": {"biological_sex": "Female", "birth_year": 1960},
        "clinical_timeline": {
            "labs": [{
                "name": "Glucose",
                "value": 130,
                "flag": "High",
                "provenance": {
                    "source_file": "test_records.pdf",
                    "source_page": 4,
                    "extraction_model": "medgemma-27b",
                    "raw_text": "Patient-identifying source text",
                },
            }],
            "diagnoses": [{
                "name": "Type 2 Diabetes",
                "provenance": {
                    "source_file": "test_records.pdf",
                    "source_page": 5,
                },
            }],
            "medications": [],
            "symptoms": [],
            "imaging": [],
            "genetics": [],
        },
        "analysis": {
            "flags": [{
                "title": "Glucose above range",
                "description": "Repeated elevation",
            }],
        },
    }


def test_insight_snapshot_is_cached_and_invalidated(monkeypatch):
    calls = []

    def fake_engine(profile_data):
        calls.append(profile_data["clinical_timeline"]["labs"][0]["value"])
        return {"active_cascades": [{"name": "Glucose Cascade"}]}

    monkeypatch.setitem(
        deep_insights._COMPUTERS,
        "biomarker_cascades",
        fake_engine,
    )
    profile = _profile_dict()

    first, changed = deep_insights.compute_deep_insight(
        profile, "biomarker_cascades"
    )
    second, changed_again = deep_insights.compute_deep_insight(
        profile, "biomarker_cascades"
    )

    assert changed is True
    assert changed_again is False
    assert second == first
    assert calls == [130]

    stored = DeepInsightSnapshot.model_validate(
        profile["analysis"]["biomarker_cascades"]
    )
    assert stored.provenance[0].source_file == "test_records.pdf"
    assert stored.provenance[0].source_page == 4
    assert stored.provenance[0].raw_text is None

    profile["clinical_timeline"]["labs"][0]["value"] = 145
    _, changed_after_input_update = deep_insights.compute_deep_insight(
        profile, "biomarker_cascades"
    )
    assert changed_after_input_update is True
    assert calls == [130, 145]


def test_snowball_receives_canonical_nested_profile_data():
    normalized, demographics = deep_insights._snowball_input(_profile_dict())

    assert normalized["diagnoses"][0]["name"] == "Type 2 Diabetes"
    assert normalized["labs"][0]["text"] == "Glucose elevated"
    assert "Glucose above range" in normalized["flags"][0]["text"]
    assert demographics["sex"] == "Female"
    assert demographics["age"] >= 65


def test_compute_all_degrades_per_engine(monkeypatch):
    profile = _profile_dict()

    for insight_type in deep_insights.INSIGHT_FIELDS:
        monkeypatch.setitem(
            deep_insights._COMPUTERS,
            insight_type,
            lambda profile_data, name=insight_type: {"engine": name},
        )

    def unavailable(profile_data):
        raise RuntimeError("unavailable")

    monkeypatch.setitem(deep_insights._COMPUTERS, "pgx_collisions", unavailable)

    changed, errors = deep_insights.compute_all_deep_insights(profile)

    assert changed is True
    assert errors == {"pgx_collisions": "RuntimeError"}
    assert "snowball_differential" in profile["analysis"]
    assert "biomarker_cascades" in profile["analysis"]
    assert "lab_trajectories" in profile["analysis"]
    assert "pgx_collision_map" not in profile["analysis"]


def test_endpoint_persists_then_retrieves_cached_insight(monkeypatch):
    import src.ui.app as app_module

    calls = []

    def fake_engine(profile_data):
        calls.append(1)
        return {"active_cascades": [{"name": "Glucose Cascade"}]}

    monkeypatch.setitem(
        deep_insights._COMPUTERS,
        "biomarker_cascades",
        fake_engine,
    )
    monkeypatch.setattr(app_module, "_profile_data", _profile_dict())
    monkeypatch.setattr(app_module, "_passphrase", "test-passphrase")
    saved = []
    monkeypatch.setattr(
        app_module,
        "_save_profile_to_vault",
        lambda: saved.append(1) or True,
    )

    client = app_module.app.test_client()
    first = client.post("/api/biomarker-cascades")
    second = client.post("/api/biomarker-cascades")
    retrieved = client.get("/api/deep-insights")

    assert first.status_code == 200
    assert second.status_code == 200
    assert calls == [1]
    assert saved == [1]
    assert retrieved.status_code == 200
    snapshot = retrieved.get_json()["biomarker_cascades"]
    assert snapshot["data"]["active_cascades"][0]["name"] == "Glucose Cascade"
    assert snapshot["provenance"][0]["source_file"] == "test_records.pdf"


def test_endpoint_does_not_claim_or_cache_failed_persistence(monkeypatch):
    import src.ui.app as app_module

    monkeypatch.setitem(
        deep_insights._COMPUTERS,
        "biomarker_cascades",
        lambda profile_data: {"active_cascades": [{"name": "Glucose Cascade"}]},
    )
    profile = _profile_dict()
    monkeypatch.setattr(app_module, "_profile_data", profile)
    monkeypatch.setattr(app_module, "_passphrase", "test-passphrase")
    monkeypatch.setattr(app_module, "_save_profile_to_vault", lambda: False)

    response = app_module.app.test_client().post("/api/biomarker-cascades")

    assert response.status_code == 500
    assert response.get_json()["error"] == "Biomarker cascade analysis unavailable"
    assert "biomarker_cascades" not in profile["analysis"]


def test_report_renders_all_deep_insights_with_provenance(tmp_path):
    pytest.importorskip("docx")
    from docx import Document

    from src.report.builder import ReportBuilder

    provenance = Provenance(
        source_file="test_records.pdf",
        source_page=9,
        extraction_model="medgemma-27b",
    )

    def snapshot(insight_type: str, data: dict) -> DeepInsightSnapshot:
        return DeepInsightSnapshot(
            insight_type=insight_type,
            input_fingerprint="a" * 64,
            provenance=[provenance],
            data=data,
        )

    profile = PatientProfile(
        analysis=AnalysisResults(
            snowball_differential=snapshot("snowball", {
                "ranked_conditions": [{
                    "label": "Systemic Vasculitis",
                    "confidence": 0.75,
                    "matched": ["rash", "hematuria"],
                    "missing": ["ANCA test"],
                    "ruled_out": [],
                }],
            }),
            biomarker_cascades=snapshot("biomarker_cascades", {
                "active_cascades": [{
                    "name": "Chronic Inflammation Cascade",
                    "active_nodes": 2,
                    "total_nodes": 6,
                }],
                "nodes": [{
                    "cascade": "Chronic Inflammation Cascade",
                    "label": "Elevated CRP",
                    "patient_has": True,
                    "patient_value": "12 mg/L",
                }],
            }),
            pgx_collision_map=snapshot("pgx_collisions", {
                "collisions": [{
                    "gene": "CYP2D6",
                    "phenotype": "Poor Metabolizer",
                    "drug": "Codeine",
                    "severity": "critical",
                    "risk": "Reduced activation",
                    "impact": "Pain relief may be inadequate",
                    "action": "Discuss an alternative with the prescriber",
                }],
            }),
            lab_trajectories=snapshot("trajectories", {
                "trajectories": [{
                    "test_name": "HbA1c",
                    "unit": "%",
                    "trend": {"direction": "rising", "confidence": "high"},
                    "projection_6mo": {"value": 6.1},
                    "projection_12mo": {"value": 6.5},
                    "warnings": [{"message": "Projected threshold crossing"}],
                }],
            }),
        )
    )

    output = Path(tmp_path) / "deep_insights.docx"
    ReportBuilder().generate(profile, output)
    doc = Document(str(output))
    full_text = "\n".join(paragraph.text for paragraph in doc.paragraphs)

    assert "8b. Deep Clinical Insight Maps" in full_text
    assert "Systemic Vasculitis" in full_text
    assert "Chronic Inflammation Cascade" in full_text
    assert "CYP2D6 + Codeine" in full_text
    assert "HbA1c — rising trend" in full_text
    assert "test_records.pdf, p.9, medgemma-27b" in full_text
