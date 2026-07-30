"""Static regression guards for P5 evidence and jargon surfaces."""

from pathlib import Path


ROOT = Path(__file__).parent.parent


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_flag_and_community_cards_render_evidence_metadata():
    app_js = _read("src/ui/static/app.js")

    assert "function findingMetadataHtml(item)" in app_js
    assert "+ findingMetadataHtml(f)" in app_js
    assert "+ findingMetadataHtml(ci)" in app_js
    assert "Unverified community signal" in _read("src/ui/app.py")


def test_cross_disciplinary_detail_renders_confidence_source_and_plain_language():
    graph_js = _read("src/ui/static/js/crossdisc_graph.js")

    assert "formatConfidence(connection.confidence)" in graph_js
    assert "provenanceText(connection.provenance)" in graph_js
    assert "getClinicalGlossaryEntry" in graph_js


def test_treatment_cards_render_medication_and_lab_evidence_metadata():
    trajectories_js = _read("src/ui/static/js/trajectories.js")

    assert "formatConfidence(resp.confidence)" in trajectories_js
    assert "provenanceText(resp.provenance)" in trajectories_js
    assert "lab.regression.confidence" in trajectories_js
    assert "lab.current.source_file" in trajectories_js


def test_body_map_translation_includes_all_requested_finding_types():
    bodymap_js = _read("src/ui/static/js/bodymap3d.js")

    assert 'fetch("/api/cross-disciplinary?stored=1")' in bodymap_js
    assert 'type: "cross-disciplinary"' in bodymap_js
    assert "fl[c].description" in bodymap_js
    assert "translation_text" in bodymap_js
    assert "finding.translation_text || finding.text" in bodymap_js


def test_general_clinical_glossary_extends_lab_plain_language_pattern():
    app_js = _read("src/ui/static/app.js")

    assert "const LAB_GLOSSARY" in app_js
    assert "const CLINICAL_GLOSSARY" in app_js
    assert "function getClinicalGlossaryEntry(text)" in app_js
    assert "function plainLanguageHtml(text)" in app_js
