"""Contract for surfacing persisted deep insights in the UI.

The four deep analyses (snowball, biomarker cascades, PGx collisions,
trajectories) persist into the encrypted profile and are served by
``GET /api/deep-insights``. Before this wiring nothing in the frontend
called that endpoint, so saved results were invisible after a reload —
the user had to rediscover overlays buried in the Labs/Genetics views.

Backend behavior is covered by test_deep_insight_persistence.py; these
tests guard the frontend contract the same way test_text_scale.py does.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "src" / "ui" / "static"


def _read(name):
    return (STATIC / name).read_text(encoding="utf-8")


def test_dashboard_has_deep_insight_card():
    html = _read("index.html")
    assert 'id="dash-deep-insights"' in html, "Deep Analysis card missing from dashboard"
    assert 'id="dash-deep-insights-body"' in html


def test_app_js_fetches_deep_insights_endpoint():
    js = _read("app.js")
    assert "/api/deep-insights" in js, "nothing calls GET /api/deep-insights"
    assert "loadDeepInsights" in js


def test_deep_insights_load_with_the_dashboard():
    """The card must populate on dashboard load, not only on demand."""
    js = _read("app.js")
    body = js.split("loadDashboard: async function()")[1]
    assert "App.loadDeepInsights();" in body.split("},")[0], (
        "loadDeepInsights must be called from loadDashboard"
    )


def test_every_persisted_insight_type_can_be_reopened():
    """Each insight the backend persists maps to its existing overlay."""
    from src.analysis.deep_insights import INSIGHT_FIELDS

    js = _read("app.js")
    launchers = {
        "snowball": "SnowballDx",
        "biomarker_cascades": "BiomarkerCascades",
        "pgx_collisions": "PgxMap",
        "trajectories": "Trajectories",
        # Cross-specialty is a full view, not an overlay — reached via App.
        "cross_specialty": "App",
    }
    assert set(launchers) == set(INSIGHT_FIELDS), (
        "insight types changed — update the dashboard launcher map"
    )
    for insight_type, global_name in launchers.items():
        assert insight_type in js, f"{insight_type} not handled in app.js"
        assert global_name in js, f"{global_name} overlay never launched from app.js"


def test_render_uses_safe_dom_construction():
    """Project rule: createElement/textContent only, never innerHTML."""
    js = _read("app.js")
    render = js.split("renderDeepInsights: function")[1].split("\n    },")[0]
    assert "innerHTML" not in render, "renderDeepInsights must not use innerHTML"
    assert "textContent" in render
