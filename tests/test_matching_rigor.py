"""Matching rigor for the systemic-disease rule engine (2026-07-30 spec).

Before this module existed the engine joined the whole record into one string
and stripped qualifiers, so a NORMAL ferritin satisfied "high ferritin" and
"denies chest pain" counted as chest pain. These tests pin the corrected
behavior; see docs/superpowers/specs/2026-07-30-matching-rigor-design.md.
"""

import pytest

from src.analysis.diagnostic_engine.evidence_match import (
    build_evidence,
    is_specific_symptom,
)


def _profile(labs=None, symptoms=None, diagnoses=None, imaging=None):
    return {
        "clinical_timeline": {
            "labs": labs or [],
            "symptoms": symptoms or [],
            "diagnoses": diagnoses or [],
            "imaging": imaging or [],
            "medications": [],
            "genetics": [],
        }
    }


# ── Lab direction ───────────────────────────────────────────

def test_normal_lab_does_not_satisfy_directional_marker():
    """The original defect: a normal ferritin matched 'high ferritin'."""
    ev = build_evidence(_profile(labs=[
        {"name": "Ferritin", "value": 120, "unit": "ng/mL",
         "reference_low": 30, "reference_high": 400, "flag": "Normal"},
    ]))
    assert ev.match_lab_marker("high ferritin") is False
    assert ev.match_lab_marker("ferritin") is False  # present but not abnormal


def test_high_lab_satisfies_high_marker_only():
    ev = build_evidence(_profile(labs=[
        {"name": "Ferritin", "value": 980, "reference_low": 30,
         "reference_high": 400, "flag": "High"},
    ]))
    assert ev.match_lab_marker("high ferritin") is True
    assert ev.match_lab_marker("ferritin") is True
    assert ev.match_lab_marker("low ferritin") is False


def test_direction_computed_from_reference_range_when_flag_missing():
    ev = build_evidence(_profile(labs=[
        {"name": "Vitamin B12", "value": 140, "reference_low": 200,
         "reference_high": 900},
    ]))
    assert ev.match_lab_marker("low b12") is True or ev.match_lab_marker("low vitamin b12") is True
    assert ev.match_lab_marker("high vitamin b12") is False


def test_string_values_and_short_flags_are_understood():
    """Demo/legacy rows carry test_name, string values, and H/L flags."""
    ev = build_evidence(_profile(labs=[
        {"test_name": "Fasting Glucose", "value": "156", "flag": "H",
         "reference_low": 70, "reference_high": 100},
    ]))
    assert ev.match_lab_marker("high glucose") is True
    assert ev.match_lab_marker("low glucose") is False


def test_positivity_marker_requires_positive_result():
    negative = build_evidence(_profile(labs=[
        {"name": "ANA", "value_text": "Negative", "flag": "Normal"},
    ]))
    positive = build_evidence(_profile(labs=[
        {"name": "ANA", "value_text": "Positive", "flag": "Abnormal"},
    ]))
    assert negative.match_lab_marker("ana positive") is False
    assert positive.match_lab_marker("ana positive") is True


def test_marker_absent_from_labs_falls_back_to_text_findings():
    """'hypercalcemia' recorded as a diagnosis is real evidence."""
    ev = build_evidence(_profile(diagnoses=[{"name": "Hypercalcemia"}]))
    assert ev.match_lab_marker("hypercalcemia") is True


# ── Negation and attribution ────────────────────────────────

@pytest.mark.parametrize("text", [
    "no chest pain",
    "denies chest pain",
    "negative for chest pain",
    "patient without chest pain",
    "ruled out chest pain",
    "family history of chest pain",
    "mother had chest pain",
])
def test_negated_and_attributed_mentions_do_not_count(text):
    ev = build_evidence(_profile(symptoms=[
        {"symptom_name": "note", "episodes": [{"description": text}]},
    ]))
    assert ev.match_symptom("chest pain") is False


def test_plain_mention_still_counts():
    ev = build_evidence(_profile(symptoms=[
        {"symptom_name": "note", "episodes": [{"description": "chest pain after climbing stairs"}]},
    ]))
    assert ev.match_symptom("chest pain") is True


def test_negation_does_not_leak_across_entries():
    """A negation in one record must not suppress a real finding in another."""
    ev = build_evidence(_profile(
        symptoms=[{"symptom_name": "note", "episodes": [{"description": "denies palpitations"}]}],
        diagnoses=[{"name": "Palpitations"}],
    ))
    assert ev.match_symptom("palpitations") is True


# ── Synonyms ────────────────────────────────────────────────

def test_lay_and_clinical_terms_match_each_other():
    lay = build_evidence(_profile(symptoms=[{"symptom_name": "shortness of breath"}]))
    clinical = build_evidence(_profile(diagnoses=[{"name": "Dyspnea on exertion"}]))
    assert lay.match_symptom("dyspnea") is True
    assert clinical.match_symptom("shortness of breath") is True


# ── Specificity ─────────────────────────────────────────────

def test_non_specific_symptoms_are_classified():
    assert is_specific_symptom("fatigue") is False
    assert is_specific_symptom("headache") is False
    assert is_specific_symptom("livedo reticularis") is True
    assert is_specific_symptom("recurrent miscarriage") is True


# ── End-to-end engine behavior (first tests of the triad table) ──

def _engine():
    from src.analysis.diagnostic_engine.cross_specialty import CrossSpecialtyEngine

    engine = CrossSpecialtyEngine()
    engine._local_pattern_discovery = lambda *a, **k: []  # keep it offline
    return engine


def test_vague_symptoms_alone_do_not_fire_a_triad():
    """Balanced policy: fatigue + headache + dizziness is not evidence."""
    engine = _engine()
    results = engine.analyze(_profile(symptoms=[
        {"symptom_name": "fatigue"},
        {"symptom_name": "headache"},
        {"symptom_name": "dizziness"},
    ]))
    assert results == []


def test_specific_signal_lets_a_triad_fire():
    engine = _engine()
    results = engine.analyze(_profile(
        symptoms=[
            {"symptom_name": "fatigue"},
            {"symptom_name": "joint pain"},
        ],
        labs=[
            {"name": "Ferritin", "value": 1200, "flag": "High",
             "reference_low": 30, "reference_high": 400},
            {"name": "Transferrin Saturation", "value": 68, "flag": "High",
             "reference_low": 20, "reference_high": 50},
        ],
    ))
    assert results, "an abnormal iron panel should still surface a pattern"
    assert all(r.get("connection_type") == "pattern_database" for r in results)
    fired = results[0]
    assert fired["total_hits"] >= 2
    assert fired["matched_labs"], "lab evidence must be recorded on the finding"


def test_normal_labs_do_not_manufacture_findings():
    engine = _engine()
    results = engine.analyze(_profile(labs=[
        {"name": "Ferritin", "value": 120, "flag": "Normal",
         "reference_low": 30, "reference_high": 400},
        {"name": "ANA", "value_text": "Negative", "flag": "Normal"},
        {"name": "TSH", "value": 2.1, "flag": "Normal",
         "reference_low": 0.4, "reference_high": 4.0},
    ]))
    assert results == []


# ── Persisted dismissals ────────────────────────────────────

from src.analysis.crossdisc_merge import dismissal_key, merge_connections


def test_merge_drops_dismissed_findings_from_both_layers():
    stored = [{"title": "Metabolic syndrome cluster", "specialties": ["Endocrinology"],
               "severity": "moderate", "description": "d"}]
    engine = [{"type": "systemic_correlation", "disease": "Hemochromatosis",
               "specialties": ["Hepatology"], "severity": "high", "description": "d"}]

    kept = merge_connections(stored, engine)
    assert len(kept) == 2

    filtered = merge_connections(stored, engine, dismissed_keys={
        dismissal_key("Metabolic syndrome cluster"),
        dismissal_key("Hemochromatosis"),
    })
    assert filtered == []


def test_dismissal_key_ignores_parentheticals_and_case():
    assert dismissal_key("Antiphospholipid Syndrome (APS)") == dismissal_key("antiphospholipid syndrome")


@pytest.fixture()
def dismiss_client(monkeypatch):
    from src.ui import app as app_module

    monkeypatch.setattr(app_module, "_profile_data", {"analysis": {}})
    monkeypatch.setattr(app_module, "_save_profile_to_vault", lambda: True)
    return app_module.app.test_client(), app_module


def test_dismiss_and_restore_round_trip(dismiss_client):
    client, app_module = dismiss_client

    resp = client.post("/api/findings/dismiss", json={"title": "Hemochromatosis"})
    assert resp.status_code == 200
    assert dismissal_key("Hemochromatosis") in resp.get_json()["dismissed"]

    stored = app_module._profile_data["analysis"]["dismissed_findings"]
    assert stored[0]["title"] == "Hemochromatosis"
    assert stored[0]["kind"] == "cross_disciplinary"

    # Dismissing twice must not duplicate the entry.
    client.post("/api/findings/dismiss", json={"title": "Hemochromatosis"})
    assert len(app_module._profile_data["analysis"]["dismissed_findings"]) == 1

    resp = client.post("/api/findings/restore", json={"title": "Hemochromatosis"})
    assert resp.status_code == 200
    assert resp.get_json()["dismissed"] == []


def test_restore_all_clears_every_dismissal(dismiss_client):
    client, app_module = dismiss_client
    client.post("/api/findings/dismiss", json={"title": "One"})
    client.post("/api/findings/dismiss", json={"title": "Two"})

    resp = client.post("/api/findings/restore", json={"all": True})
    assert resp.get_json()["dismissed"] == []


def test_dismiss_rejects_unknown_kind_and_empty_title(dismiss_client):
    client, _ = dismiss_client
    assert client.post("/api/findings/dismiss",
                       json={"kind": "labs", "title": "X"}).status_code == 400
    assert client.post("/api/findings/dismiss", json={"title": "  "}).status_code == 400


def test_dismissed_finding_disappears_from_the_endpoint(dismiss_client):
    client, app_module = dismiss_client
    app_module._profile_data["analysis"]["cross_disciplinary"] = [{
        "title": "Metabolic syndrome cluster",
        "specialties": ["Endocrinology"],
        "severity": "moderate",
        "description": "d",
    }]

    before = client.get("/api/cross-disciplinary?stored=1").get_json()
    assert any(c["title"] == "Metabolic syndrome cluster" for c in before)

    client.post("/api/findings/dismiss", json={"title": "Metabolic syndrome cluster"})

    after = client.get("/api/cross-disciplinary?stored=1").get_json()
    assert all(c["title"] != "Metabolic syndrome cluster" for c in after)
