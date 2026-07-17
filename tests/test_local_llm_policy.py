"""
Policy tests for local-only patient-record reasoning.

These checks pin the rule that non-research assistant paths should use
the local Ollama-backed model rather than Gemini.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_visit_prep_uses_local_narrative_without_api_key(monkeypatch):
    """Visit prep should generate its narrative from the local model."""
    import src.analysis.visit_prep as visit_prep_module

    monkeypatch.setattr(
        visit_prep_module,
        "call_local_text_model",
        lambda *args, **kwargs: "Local visit prep narrative",
    )

    generator = visit_prep_module.VisitPrepGenerator()
    result = generator.generate(
        {
            "clinical_timeline": {
                "diagnoses": [{"name": "Hypertension", "status": "active"}],
                "symptoms": [],
                "labs": [],
                "medications": [],
            },
            "analysis": {},
            "demographics": {},
        }
    )

    assert result["narrative"] == "Local visit prep narrative"


def test_symptom_analytics_uses_local_llm_without_api_key(monkeypatch):
    """Symptom AI insights should use the local model even without a Gemini key."""
    import src.analysis.symptom_analytics as symptom_module

    monkeypatch.setattr(
        symptom_module,
        "call_local_text_model",
        lambda *args, **kwargs: (
            '{"patterns":[{"message":"Fatigue clusters after lunch"}],'
            '"connections":[{"message":"Fatigue and thirst co-occur"}],'
            '"counter_narratives":[{"message":"Symptoms still break through treatment"}],'
            '"suggestions":[{"message":"Bring the episode timing to your clinician"}]}'
        ),
    )

    engine = symptom_module.SymptomAnalytics()
    result = engine.generate_ai_insights(
        [
            {
                "symptom_name": "Fatigue",
                "episodes": [
                    {
                        "description": "Crash after lunch",
                        "triggers": "high-carb meal",
                        "intensity": "high",
                    }
                ],
                "counter_definitions": [],
            }
        ],
        profile_data={},
    )

    assert result["source"] == "local_llm"
    assert result["patterns"][0]["message"] == "Fatigue clusters after lunch"


def test_ai_matcher_uses_local_model_for_unmapped_terms(monkeypatch):
    """AIMatcher should use the local model for synonym expansion."""
    import src.analysis.ai_matcher as matcher_module

    monkeypatch.setattr(
        matcher_module,
        "call_local_text_model",
        lambda *args, **kwargs: '["orthostasis", "postural dizziness"]',
    )

    matcher = matcher_module.AIMatcher()
    result = matcher.resolve_synonyms("orthostatic intolerance syndrome")

    assert "orthostasis" in result
    assert "postural dizziness" in result


def test_cross_specialty_uses_local_pattern_discovery(monkeypatch):
    """Cross-specialty discovery should not require Gemini."""
    import src.analysis.diagnostic_engine.cross_specialty as cross_module

    monkeypatch.setattr(
        cross_module,
        "call_local_text_model",
        lambda *args, **kwargs: (
            '[{"disease":"Vasculitis","specialties":["Rheumatology","Nephrology"],'
            '"evidence":["hematuria","rash"],'
            '"description":"Here is something we found. These findings may point to inflammation across multiple systems.",'
            '"sources":["KDIGO guideline"],"evidence_strength":"moderate"}]'
        ),
    )

    engine = cross_module.CrossSpecialtyEngine()
    monkeypatch.setattr(engine, "_get_pubmed_client", lambda: None)

    alerts = engine._local_pattern_discovery(
        ["hematuria", "rash", "fatigue", "joint pain", "proteinuria"],
        [],
    )

    assert len(alerts) == 1
    assert alerts[0]["disease"] == "Vasculitis"
    assert alerts[0]["evidence_source"] == "KDIGO guideline"


def test_snowball_discovery_uses_local_model(monkeypatch):
    """Snowball discovery should parse local-model differential suggestions."""
    import src.analysis.snowball_engine as snowball_module

    monkeypatch.setattr(
        snowball_module,
        "call_local_text_model",
        lambda *args, **kwargs: (
            '[{"id":"systemic_vasculitis","label":"Systemic Vasculitis",'
            '"category":"autoimmune","expected":["hematuria","rash","joint pain"],'
            '"rules_out":["normal inflammatory markers"],'
            '"matched":["hematuria","rash"]}]'
        ),
    )

    engine = snowball_module.SnowballEngine()
    discovered = engine._discover_via_ollama(
        [
            {
                "type": "finding",
                "text": "hematuria",
                "original": "hematuria",
                "severity": "high",
            },
            {
                "type": "finding",
                "text": "rash",
                "original": "rash",
                "severity": "moderate",
            },
        ],
        {"kidney_stone": {"label": "Kidney Stone"}},
    )

    assert "systemic_vasculitis" in discovered
    assert discovered["systemic_vasculitis"]["label"] == "Systemic Vasculitis"
