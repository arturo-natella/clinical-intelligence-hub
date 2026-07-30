"""Contract for the per-symptom analytics drill-down.

``GET /api/symptom-analytics/<symptom_id>`` returns detail the aggregate
endpoint cannot: ``episode_timeline`` is computed only by
``analyze_single``. The endpoint shipped without a caller, so that
per-symptom history was unreachable from the UI.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "src" / "ui" / "static"


def _read(name):
    return (STATIC / name).read_text(encoding="utf-8")


def test_episode_timeline_is_unique_to_the_single_symptom_endpoint():
    """The premise for keeping this endpoint — verify it still holds."""
    from src.analysis.symptom_analytics import SymptomAnalytics

    symptom = {
        "symptom_id": "s1",
        "symptom_name": "Headache",
        "episodes": [
            {"episode_date": "2026-01-05", "intensity": "high", "time_of_day": "morning"},
            {"episode_date": "2026-01-02", "intensity": "low", "time_of_day": "evening"},
        ],
    }
    engine = SymptomAnalytics()
    single = engine.analyze_single(symptom)
    aggregate = engine.analyze([symptom], [])

    assert "episode_timeline" in single
    assert "episode_timeline" not in aggregate
    # Sorted chronologically for the detail view.
    assert [e["date"] for e in single["episode_timeline"]] == ["2026-01-02", "2026-01-05"]


def test_symptom_card_opens_the_drilldown():
    js = _read("js/symptoms.js")
    assert "/api/symptom-analytics/" in js, "nothing calls the per-symptom endpoint"
    assert "openPatterns" in js
    assert "symptom.symptom_id" in js


def test_drilldown_renders_the_episode_timeline():
    js = _read("js/symptoms.js")
    render = js.split("_renderPatternDetail: function")[1].split("\n    },")[0]
    assert "episode_timeline" in render, "detail view must show the per-symptom timeline"
    assert "innerHTML" not in render, "project rule: no innerHTML"
    assert "textContent" in render


def test_drilldown_handles_a_symptom_with_no_episodes():
    """A brand-new symptom has no history; the panel must not look broken."""
    from src.analysis.symptom_analytics import SymptomAnalytics

    result = SymptomAnalytics().analyze_single(
        {"symptom_id": "s2", "symptom_name": "Nausea", "episodes": []}
    )
    assert result["episode_timeline"] == []

    js = _read("js/symptoms.js")
    render = js.split("_renderPatternDetail: function")[1].split("\n    },")[0]
    assert "No episodes" in render or "no episodes" in render, (
        "empty-history case needs a friendly message"
    )
