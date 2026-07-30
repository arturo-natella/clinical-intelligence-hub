"""Local-first regression guards for SNOMED terminology validation."""

from pathlib import Path


def test_common_snomed_terms_resolve_without_network(monkeypatch):
    from src.validation.snomed import SNOMEDClient

    client = SNOMEDClient()
    monkeypatch.setattr(
        client,
        "_search_snowstorm",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("network should not be used for a curated term")
        ),
    )

    result = client.validate_disease("HTN")

    assert result["concept_id"] == "38341003"
    assert result["preferred_term"] == "Essential hypertension"
    assert result["icd10"] == "I10"
    assert result["source"] == "SNOMED CT (local curated database)"


def test_unknown_snomed_term_can_use_optional_snowstorm_enrichment(monkeypatch):
    from src.validation.snomed import SNOMEDClient

    client = SNOMEDClient()
    calls = []

    def fake_snowstorm(term, semantic_tag=None):
        calls.append((term, semantic_tag))
        return {
            "concept_id": "123",
            "preferred_term": "Rare example disorder",
            "source": "SNOMED CT (Snowstorm)",
        }

    monkeypatch.setattr(client, "_search_snowstorm", fake_snowstorm)

    result = client.validate_disease("Rare example disorder")

    assert result["concept_id"] == "123"
    assert calls == [("Rare example disorder", "disorder")]


def test_snomed_validation_has_no_obsolete_nlm_expansion_dependency():
    source = (
        Path(__file__).parent.parent / "src/validation/snomed.py"
    ).read_text(encoding="utf-8")

    assert "cts.nlm.nih.gov" not in source
    assert "_search_nlm_fhir" not in source
    assert "NLM_FHIR_BASE" not in source
