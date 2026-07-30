"""Imaging `findings` shape contract across engines, demo data, and endpoints.

The canonical model is ``ImagingStudy.findings: list[ImagingFinding]`` — a list
of objects. Historically the demo profile emitted a single free-text *string*
per study, and iterating a string yields characters. That shape crashed the
Snowball corpus builder (``'str' object has no attribute 'get'``) and silently
shredded the cross-specialty corpus into single letters.

These tests pin both halves of the fix:
  * the demo profile emits the canonical list-of-objects shape, and
  * every corpus builder tolerates legacy string shapes without crashing,
    because vault profiles written before the fix still carry them.
"""

from src.analysis.diagnostic_engine.cross_specialty import CrossSpecialtyEngine
from src.analysis.snowball_engine import SnowballEngine
from src.ui import app as app_module


def _snowball_corpus(imaging: list) -> list:
    """Build a Snowball corpus from imaging studies alone."""
    engine = SnowballEngine.__new__(SnowballEngine)  # bypass matcher init
    return engine._build_corpus({"clinical_timeline": {"imaging": imaging}})


def _cross_specialty_corpus(imaging: list) -> list:
    engine = CrossSpecialtyEngine.__new__(CrossSpecialtyEngine)
    return engine._build_corpus({"clinical_timeline": {"imaging": imaging}})


def _imaging_texts(corpus: list) -> list:
    return [item["text"] for item in corpus if item.get("type") == "imaging"]


# ── Snowball corpus: every findings shape ─────────────────────────


def test_snowball_corpus_accepts_object_findings():
    """Canonical shape: list of ImagingFinding-shaped dicts."""
    corpus = _snowball_corpus([{
        "modality": "Abdominal Ultrasound",
        "findings": [
            {"description": "Mild hepatic steatosis (fatty liver)"},
            {"description": "No gallstones"},
        ],
    }])

    assert _imaging_texts(corpus) == [
        "mild hepatic steatosis (fatty liver)",
        "no gallstones",
    ]


def test_snowball_corpus_accepts_bare_string_findings():
    """Legacy shape: `findings` is a single free-text string, not a list.

    Must yield one whole-text entry — never one entry per character.
    """
    text = "No acute cardiopulmonary disease. Heart size normal."
    corpus = _snowball_corpus([{"modality": "Chest X-Ray", "findings": text}])

    assert _imaging_texts(corpus) == [text.lower()]


def test_snowball_corpus_accepts_list_of_string_findings():
    """Mixed shape: a list holding plain strings alongside dicts."""
    corpus = _snowball_corpus([{
        "modality": "MRI",
        "findings": ["Mild disc bulge", {"description": "Nerve impingement"}],
    }])

    assert _imaging_texts(corpus) == ["mild disc bulge", "nerve impingement"]


def test_snowball_corpus_skips_empty_and_malformed_findings():
    """Blank descriptions and non-text junk contribute nothing."""
    corpus = _snowball_corpus([{
        "modality": "CT",
        "findings": ["", {"description": ""}, {}, None, 42, "   "],
    }])

    assert _imaging_texts(corpus) == []


def test_snowball_corpus_still_reads_radiomic_flags():
    """Object findings keep contributing radiomic threshold flags."""
    corpus = _snowball_corpus([{
        "modality": "CT",
        "findings": [{
            "description": "Hepatic lesion",
            "radiomic_features": {
                "threshold_flags": [
                    {"message": "Texture heterogeneity above threshold",
                     "level": "high"},
                ],
            },
        }],
    }])

    flags = [item for item in corpus if item["type"] == "radiomic_flag"]
    assert len(flags) == 1
    assert flags[0]["text"] == "texture heterogeneity above threshold"
    assert flags[0]["severity"] == "high"


def test_snowball_corpus_handles_missing_and_non_list_imaging():
    """Absent or malformed imaging collections degrade quietly."""
    assert _snowball_corpus([]) == []
    assert _snowball_corpus([{"modality": "CT"}]) == []
    assert _snowball_corpus([{"modality": "CT", "findings": None}]) == []


# ── Cross-specialty corpus: same contract ─────────────────────────


def test_cross_specialty_corpus_does_not_shred_string_findings():
    """A bare string must not become one corpus entry per character."""
    corpus = _cross_specialty_corpus([{
        "modality": "Chest X-Ray",
        "description": "PA and lateral chest radiograph",
        "findings": "No acute cardiopulmonary disease.",
    }])

    assert "no acute cardiopulmonary disease." in corpus
    # Pre-fix this produced 30+ single-character entries.
    assert not [entry for entry in corpus if len(entry) == 1]


def test_cross_specialty_corpus_accepts_object_findings():
    corpus = _cross_specialty_corpus([{
        "modality": "MRI",
        "findings": [{"description": "Nerve impingement"}, "Disc bulge"],
    }])

    assert "nerve impingement" in corpus
    assert "disc bulge" in corpus


# ── Demo profile emits the canonical shape ────────────────────────


def test_demo_profile_imaging_findings_are_lists_of_objects():
    """Demo data must match ImagingStudy.findings: list[ImagingFinding]."""
    studies = app_module._build_demo_profile()["clinical_timeline"]["imaging"]
    assert studies, "demo profile should ship imaging studies"

    for study in studies:
        findings = study["findings"]
        assert isinstance(findings, list), (
            f"{study['modality']} findings must be a list, got {type(findings).__name__}"
        )
        assert findings, f"{study['modality']} should have at least one finding"
        for finding in findings:
            assert isinstance(finding, dict), (
                f"{study['modality']} finding must be a dict, got {type(finding).__name__}"
            )
            assert finding["description"].strip(), "finding needs a description"


def test_demo_profile_imaging_validates_against_the_canonical_model():
    """The demo shape round-trips through Pydantic without coercion."""
    from src.models import ImagingStudy, Provenance

    provenance = Provenance(source_file="demo_patient.json", extraction_model="demo")
    for study in app_module._build_demo_profile()["clinical_timeline"]["imaging"]:
        validated = ImagingStudy.model_validate({**study, "provenance": provenance})
        assert len(validated.findings) == len(study["findings"])


# ── End-to-end: the reported 500 ──────────────────────────────────


def test_snowball_endpoint_succeeds_with_demo_profile(monkeypatch):
    """POST /api/snowball-diagnoses returned 500 (AttributeError) on demo data."""
    monkeypatch.setattr(
        app_module, "_profile_data", app_module._build_demo_profile()
    )
    # Keep the test hermetic: no local-LLM discovery pass, no vault write.
    # Snapshot persistence has its own coverage in test_deep_insight_persistence.
    monkeypatch.setattr(
        SnowballEngine, "_discover_conditions", lambda self, corpus, scored: {}
    )
    monkeypatch.setattr(app_module, "_save_profile_to_vault", lambda: True)

    client = app_module.app.test_client()
    response = client.post("/api/snowball-diagnoses")

    assert response.status_code == 200
    payload = response.get_json()
    assert "error" not in payload
    assert payload["ranked_conditions"], "demo data should rank candidate conditions"


def test_flags_endpoint_keeps_radiomic_flags_despite_legacy_string_study(monkeypatch):
    """One legacy string study must not wipe radiomic flags from the whole profile.

    The radiomic loop in get_flags() is wrapped in try/except, so a string study
    never surfaced as an error — it aborted the loop and silently dropped every
    radiomic flag, including those on well-formed studies later in the list.
    """
    monkeypatch.setattr(app_module, "_profile_data", {
        "clinical_timeline": {
            "imaging": [
                # Legacy shape first, so it aborts the loop before the next study.
                {"modality": "Chest X-Ray", "findings": "No acute disease."},
                {"modality": "CT", "findings": [{
                    "description": "Hepatic lesion",
                    "radiomic_features": {"threshold_flags": [{
                        "level": "high",
                        "message": "Texture heterogeneity above threshold",
                        "feature": "glcm_entropy",
                        "value": 4.2,
                        "threshold": 3.5,
                    }]},
                }]},
            ],
        },
        "analysis": {"flags": []},
    })

    response = app_module.app.test_client().get("/api/flags")

    assert response.status_code == 200
    radiomic = [
        flag for flag in response.get_json()
        if flag.get("category") == "Radiomic Finding"
    ]
    assert len(radiomic) == 1, "radiomic flag was dropped by the legacy string study"
    assert radiomic[0]["description"] == "Texture heterogeneity above threshold"
