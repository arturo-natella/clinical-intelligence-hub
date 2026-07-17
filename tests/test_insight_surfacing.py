"""
Guards for the insight-conveyance surfaces: the dashboard narrative,
doctor-question auto-feed, and the community render contract.

These pin three behaviors:
1. /api/dashboard returns a plain-language `narrative` once a profile exists
   (preferring a pipeline-generated executive summary when present).
2. /api/questions GET returns a normalized, merged view: every entry is an
   object with a string `question`, and per-flag `question_for_doctor` values
   are auto-fed in (deduplicated against the stored list). The Visit Prep
   generator prefers the tailored per-flag question over its generic template.
3. /api/community normalizes all three historical payload shapes to the
   render contract (title, description, upvotes, disclaimer).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def _get(monkeypatch, profile, path):
    import src.ui.app as app_module

    monkeypatch.setattr(app_module, "_profile_data", profile)
    with app_module.app.test_client() as client:
        resp = client.get(path)
    assert resp.status_code == 200
    return json.loads(resp.data)


def _demo_profile():
    import src.ui.app as app_module

    return app_module._build_demo_profile()


# ── Dashboard narrative ─────────────────────────────────────

def test_dashboard_narrative_populates_for_demo_profile(monkeypatch):
    data = _get(monkeypatch, _demo_profile(), "/api/dashboard")
    narrative = data.get("narrative", "")
    assert isinstance(narrative, str) and len(narrative) > 40, (
        "dashboard must include a plain-language narrative once a profile exists"
    )
    assert str(data["flags_count"]) in narrative, (
        "narrative should reference the number of findings"
    )


def test_dashboard_narrative_prefers_pipeline_summary(monkeypatch):
    profile = _demo_profile()
    profile["analysis"]["executive_summary"] = "Pipeline-written overview sentence."
    data = _get(monkeypatch, profile, "/api/dashboard")
    assert data["narrative"] == "Pipeline-written overview sentence."


# ── Doctor-question auto-feed ───────────────────────────────

def test_questions_get_normalizes_every_entry_to_object(monkeypatch):
    profile = {
        "analysis": {
            "questions_for_doctor": [
                "Plain string question?",
                {"question": "Object question?", "priority": "high"},
            ]
        }
    }
    items = _get(monkeypatch, profile, "/api/questions")
    assert len(items) == 2
    for item in items:
        assert isinstance(item, dict) and isinstance(item.get("question"), str)
        assert item["question"], "no entry may normalize to an empty question"


def test_questions_get_autofeeds_flag_questions_with_dedup(monkeypatch):
    profile = {
        "analysis": {
            "questions_for_doctor": [
                {"question": "Already stored question?"},
            ],
            "flags": [
                {"title": "Finding A", "severity": "high",
                 "question_for_doctor": "Tailored question from flag A?"},
                {"title": "Finding B", "severity": "moderate",
                 "question_for_doctor": "Already stored question?"},  # duplicate text
                {"title": "Finding C", "severity": "low"},  # no question — ignored
            ],
        }
    }
    items = _get(monkeypatch, profile, "/api/questions")
    texts = [item["question"] for item in items]
    assert "Tailored question from flag A?" in texts
    assert texts.count("Already stored question?") == 1, "flag duplicates must dedup"
    flag_item = next(i for i in items if i["question"] == "Tailored question from flag A?")
    assert flag_item.get("source") == "flag"
    assert flag_item.get("context") == "Finding A"


def test_visit_prep_prefers_tailored_flag_question():
    from src.analysis.visit_prep import VisitPrepGenerator

    generator = VisitPrepGenerator()
    analysis = {
        "flags": [
            {"title": "Finding A", "severity": "high",
             "question_for_doctor": "Tailored question from flag A?"},
            {"title": "Finding B", "severity": "critical"},  # no tailored question
        ]
    }
    questions = generator._questions_to_ask(analysis, {}, {})
    texts = [q["question"] for q in questions]
    assert "Tailored question from flag A?" in texts, (
        "tailored per-flag question must be used when present"
    )
    assert not any("Finding A" in t and "what should I know" in t for t in texts), (
        "generic template must not duplicate a flag that has a tailored question"
    )
    assert any("Finding B" in t for t in texts), (
        "generic template still covers high/critical flags without a tailored question"
    )


def test_demo_flags_carry_doctor_questions(monkeypatch):
    flags = _get(monkeypatch, _demo_profile(), "/api/flags")
    with_questions = [f for f in flags if (f.get("question_for_doctor") or "").strip()]
    assert with_questions, "demo profile should exercise the per-flag doctor question"


# ── Community render contract ───────────────────────────────

def test_community_normalizes_model_shape(monkeypatch):
    profile = {
        "analysis": {
            "community_insights": [
                {"subreddit": "ChronicIllness",
                 "description": "Several members report a pattern worth asking about.",
                 "upvote_count": 240,
                 "post_url": "https://reddit.com/r/ChronicIllness/abc",
                 "cross_disciplinary_context": "A plausible mechanism explanation."},
            ]
        }
    }
    items = _get(monkeypatch, profile, "/api/community")
    item = items[0]
    assert item["upvotes"] == 240, "upvotes must mirror upvote_count"
    assert item["title"], "a title must be derived when the payload has none"
    assert item["description"].startswith("Several members")
    assert "NOT clinical data" in item.get("disclaimer", ""), (
        "the full disclaimer string must reach the UI"
    )
    assert item["cross_disciplinary_context"] == "A plausible mechanism explanation."


def test_community_normalizes_demo_shape(monkeypatch):
    items = _get(monkeypatch, _demo_profile(), "/api/community")
    assert items, "demo profile should include community insights"
    for item in items:
        assert item.get("title"), "every community card needs a title"
        assert item.get("description"), (
            "demo entries store their text under `detail` — it must surface as description"
        )
        assert isinstance(item.get("upvotes", 0), int)
        assert "NOT clinical data" in item.get("disclaimer", "")
