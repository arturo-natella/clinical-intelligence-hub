"""Imaging findings must be list[ImagingFinding] everywhere (2026-07-30).

`ImagingStudy.findings` is declared `list[ImagingFinding]`, but the demo
profile stored a single string per study. Consumers that iterate it then walk
the string character by character:

  * snowball_engine called ``finding.get(...)`` on a character → 500, so the
    Differential diagnosis never rendered in the Deep Analysis card;
  * the Imaging view rendered one empty box per character (507 of them).

These tests pin the canonical shape at the source and require every consumer
to tolerate legacy strings rather than crash.
"""

from src.analysis.snowball_engine import SnowballEngine


def _profile_with(findings):
    return {
        "clinical_timeline": {
            "imaging": [{
                "modality": "Fundoscopy",
                "body_region": "Eyes",
                "description": "Diabetic retinopathy screening",
                "findings": findings,
            }],
            "labs": [], "medications": [], "diagnoses": [],
            "symptoms": [], "genetics": [],
        },
        "analysis": {"flags": []},
    }


def _imaging_corpus(profile):
    engine = SnowballEngine()
    corpus = engine._build_corpus(profile)
    return [item for item in corpus if item.get("type") == "imaging"]


def test_demo_profile_emits_model_shaped_findings():
    """The demo must match ImagingStudy.findings — a list of objects."""
    from src.ui.app import _build_demo_profile

    studies = _build_demo_profile()["clinical_timeline"]["imaging"]
    assert studies, "demo should ship imaging studies"
    for study in studies:
        findings = study.get("findings")
        assert isinstance(findings, list), f"{study.get('modality')} findings must be a list"
        for finding in findings:
            assert isinstance(finding, dict), "each finding is an object"
            assert finding.get("description"), "each finding carries description text"


def test_snowball_reads_object_findings():
    corpus = _imaging_corpus(_profile_with([
        {"description": "Dot-blot hemorrhages and hard exudates in both eyes."},
    ]))
    assert any("dot-blot hemorrhages" in item["text"] for item in corpus)


def test_snowball_survives_legacy_string_findings():
    """Regression: this raised AttributeError and 500'd the endpoint."""
    corpus = _imaging_corpus(_profile_with(
        "Dot-blot hemorrhages and hard exudates in both eyes."
    ))
    assert any("dot-blot hemorrhages" in item["text"] for item in corpus)
    # And never one entry per character.
    assert len(corpus) == 1


def test_snowball_ignores_unusable_finding_shapes():
    assert _imaging_corpus(_profile_with(None)) == []
    assert _imaging_corpus(_profile_with([])) == []
    assert _imaging_corpus(_profile_with([{"description": ""}])) == []


def test_imaging_view_renders_finding_objects_not_characters():
    """The Imaging view must read descriptions, not index into a string."""
    from pathlib import Path

    js = (Path(__file__).resolve().parent.parent
          / "src/ui/static/app.js").read_text(encoding="utf-8")
    assert "_normalizeFindings" in js, (
        "imaging render must normalize findings before iterating"
    )
