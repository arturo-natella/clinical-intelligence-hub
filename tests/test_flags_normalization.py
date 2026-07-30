"""
Regression guards for /api/flags rendering contract.

The frontend (loadFlags) and the ClinicalFlag model both expect each flag to
carry its explanation under `description` (a string) and `evidence` as a list
of strings. Legacy/demo producers used `detail` and emitted evidence as
{source, date, value} objects, which the renderer string-coerced into the
literal "[object Object]" and left the description blank. These tests pin the
API to the model contract so that class of bug cannot reach the UI again.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def _flags_for(monkeypatch, profile):
    import src.ui.app as app_module

    monkeypatch.setattr(app_module, "_profile_data", profile)
    with app_module.app.test_client() as client:
        resp = client.get("/api/flags")
    assert resp.status_code == 200
    return json.loads(resp.data)


def test_flags_api_fills_description_from_legacy_detail(monkeypatch):
    """A flag using the legacy `detail` key still yields a non-empty description."""
    profile = {
        "analysis": {
            "flags": [
                {
                    "title": "Declining kidney function",
                    "severity": "high",
                    "category": "Trend Analysis",
                    "detail": "eGFR dropped from 92 to 78 mL/min over 18 months.",
                }
            ]
        }
    }
    flags = _flags_for(monkeypatch, profile)
    match = next(f for f in flags if f["title"] == "Declining kidney function")
    assert match.get("description"), "description must be populated from `detail`"
    assert "eGFR" in match["description"]


def test_flags_api_coerces_object_evidence_to_strings(monkeypatch):
    """Object-shaped evidence must become readable strings, never [object Object]."""
    profile = {
        "analysis": {
            "flags": [
                {
                    "title": "HbA1c above target",
                    "severity": "critical",
                    "category": "Lab Finding",
                    "detail": "HbA1c 8.2% exceeds the 7.0% target.",
                    "evidence": [
                        {"source": "Lab result", "date": "2025-12-01", "value": "HbA1c 8.2%"}
                    ],
                }
            ]
        }
    }
    flags = _flags_for(monkeypatch, profile)
    match = next(f for f in flags if f["title"] == "HbA1c above target")
    assert all(isinstance(item, str) for item in match.get("evidence", [])), (
        "every evidence item must be a string"
    )
    joined = " ".join(match.get("evidence", []))
    assert "[object Object]" not in joined
    assert "HbA1c 8.2%" in joined, "the evidence value must survive coercion"


def test_flags_api_demo_profile_is_render_safe(monkeypatch):
    """The shipping demo profile must expose only render-safe flags."""
    import src.ui.app as app_module

    profile = app_module._build_demo_profile()
    flags = _flags_for(monkeypatch, profile)
    assert flags, "demo profile should produce flags"
    for f in flags:
        assert isinstance(f.get("description", ""), str) and f.get("description"), (
            f"flag {f.get('title')!r} has an empty/non-string description"
        )
        for item in f.get("evidence", []):
            assert isinstance(item, str), (
                f"flag {f.get('title')!r} has non-string evidence: {item!r}"
            )


def test_flags_api_surfaces_matching_record_provenance_and_confidence(monkeypatch):
    profile = {
        "clinical_timeline": {
            "labs": [{
                "name": "HbA1c",
                "value": 8.2,
                "provenance": {
                    "source_file": "quest_labs.pdf",
                    "source_page": 3,
                    "extraction_model": "medgemma-27b",
                    "confidence": 0.93,
                    "raw_text": "must not be copied to derived metadata",
                },
            }],
        },
        "analysis": {
            "flags": [{
                "title": "HbA1c above target",
                "severity": "high",
                "category": "Lab Finding",
                "description": "HbA1c remains elevated.",
            }],
        },
    }

    flags = _flags_for(monkeypatch, profile)
    match = next(flag for flag in flags if flag["title"] == "HbA1c above target")

    assert match["confidence"] == 0.93
    assert match["provenance"][0]["source_file"] == "quest_labs.pdf"
    assert match["provenance"][0]["source_page"] == 3
    assert "raw_text" not in match["provenance"][0]
