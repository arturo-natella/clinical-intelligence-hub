"""
Phase 8 Tests — Clinical Intelligence Hub UI

Tests Flask server routes, pipeline orchestrator structure,
and static file serving. Does not test actual browser rendering
(that requires manual verification).
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Pipeline Tests ──────────────────────────────────────────

def test_pipeline_import():
    """Pipeline module imports without errors."""
    from src.ui.pipeline import Pipeline
    assert Pipeline is not None
    print("✓ Pipeline imports successfully")


def test_pipeline_init():
    """Pipeline initializes with required args."""
    from src.ui.pipeline import Pipeline

    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        pipeline = Pipeline(data_dir, "test-passphrase")
        assert pipeline.data_dir == data_dir
    print("✓ Pipeline initializes correctly")


def test_pipeline_clear_session():
    """Pipeline clear_session doesn't crash on empty state."""
    from src.ui.pipeline import Pipeline

    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        pipeline = Pipeline(data_dir, "test-passphrase")
        # Should not raise on empty state
        pipeline.clear_session()
    print("✓ Pipeline clear_session works on empty state")


def test_pipeline_has_all_passes():
    """Pipeline has methods for all 6 passes."""
    from src.ui.pipeline import Pipeline

    with tempfile.TemporaryDirectory() as tmpdir:
        pipeline = Pipeline(Path(tmpdir), "test")

        # Check all pass methods exist
        assert hasattr(pipeline, "_pass_0_preprocess")
        assert hasattr(pipeline, "_pass_1a_text_extraction")
        assert hasattr(pipeline, "_pass_1b_vision")
        assert hasattr(pipeline, "_pass_1c_monai")
        assert hasattr(pipeline, "_pass_1_5_redaction")
        assert hasattr(pipeline, "_pass_2_4_cloud_analysis")
        assert hasattr(pipeline, "_pass_5_validation")
        assert hasattr(pipeline, "_pass_6_report")
        assert hasattr(pipeline, "run")
        assert hasattr(pipeline, "clear_session")
    print("✓ Pipeline has all pass methods")


# ── Flask App Tests ─────────────────────────────────────────

def test_flask_app_import():
    """Flask app imports without errors."""
    from src.ui.app import app
    assert app is not None
    print("✓ Flask app imports successfully")


def test_flask_app_routes_exist():
    """Flask app has all expected routes."""
    from src.ui.app import app

    rules = [rule.rule for rule in app.url_map.iter_rules()]

    expected_routes = [
        "/",
        "/api/unlock",
        "/api/session/clear",
        "/api/session/status",
        "/api/upload",
        "/api/analyze",
        "/api/progress",
        "/api/profile",
        "/api/medications",
        "/api/labs",
        "/api/diagnoses",
        "/api/imaging",
        "/api/genetics",
        "/api/flags",
        "/api/interactions",
        "/api/cross-disciplinary",
        "/api/community",
        "/api/literature",
        "/api/questions",
        "/api/alerts",
        "/api/timeline",
        "/api/report/download",
        "/api/report/generate",
        "/api/chat",
        "/api/keys",
        "/api/keys/status",
    ]

    for route in expected_routes:
        assert route in rules, f"Missing route: {route}"

    print(f"✓ All {len(expected_routes)} expected routes present")


def test_flask_test_client():
    """Flask test client can make basic requests."""
    from src.ui.app import app

    with app.test_client() as client:
        # Session status should work without auth
        resp = client.get("/api/session/status")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "unlocked" in data
        assert "has_profile" in data
        assert "pipeline_running" in data

    print("✓ Flask test client works, session status returns correct fields")


def test_api_returns_empty_without_profile():
    """API endpoints return empty data without a loaded profile."""
    from src.ui.app import app

    endpoints = [
        "/api/medications",
        "/api/labs",
        "/api/diagnoses",
        "/api/imaging",
        "/api/genetics",
        "/api/flags",
        "/api/interactions",
        "/api/cross-disciplinary",
        "/api/community",
        "/api/literature",
        "/api/questions",
        "/api/timeline",
    ]

    with app.test_client() as client:
        for endpoint in endpoints:
            resp = client.get(endpoint)
            assert resp.status_code == 200, f"{endpoint} should return 200"
            data = json.loads(resp.data)
            assert isinstance(data, list), f"{endpoint} should return a list"
            assert len(data) == 0, f"{endpoint} should be empty without profile"

    print(f"✓ All {len(endpoints)} data endpoints return empty lists without profile")


def test_api_upload_requires_auth():
    """Upload endpoint requires vault to be unlocked."""
    from src.ui.app import app

    with app.test_client() as client:
        resp = client.post("/api/upload")
        assert resp.status_code == 401

    print("✓ Upload requires authentication")


def test_api_analyze_requires_auth():
    """Analyze endpoint requires vault to be unlocked."""
    from src.ui.app import app

    with app.test_client() as client:
        resp = client.post("/api/analyze")
        assert resp.status_code == 401

    print("✓ Analyze requires authentication")


def test_api_chat_requires_profile():
    """Chat endpoint requires a loaded profile."""
    from src.ui.app import app

    with app.test_client() as client:
        resp = client.post(
            "/api/chat",
            data=json.dumps({"message": "test"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    print("✓ Chat requires loaded profile")


def test_api_report_generate_requires_profile():
    """Report generation requires a loaded profile."""
    from src.ui.app import app

    with app.test_client() as client:
        resp = client.post("/api/report/generate")
        assert resp.status_code == 400

    print("✓ Report generation requires profile")


# ── Static Files Tests ──────────────────────────────────────

def test_static_files_exist():
    """All required static files exist."""
    static_dir = Path(__file__).parent.parent / "src" / "ui" / "static"

    assert (static_dir / "index.html").exists(), "index.html missing"
    assert (static_dir / "styles.css").exists(), "styles.css missing"
    assert (static_dir / "app.js").exists(), "app.js missing"

    # Check assets
    assets_dir = static_dir / "assets"
    assert (assets_dir / "anatomy.png").exists(), "anatomy.png missing"
    assert (assets_dir / "anatomy_back.png").exists(), "anatomy_back.png missing"
    assert (assets_dir / "anatomy_muscle.png").exists(), "anatomy_muscle.png missing"
    assert (assets_dir / "anatomy_skeleton.png").exists(), "anatomy_skeleton.png missing"
    assert (assets_dir / "anatomy_organs.png").exists(), "anatomy_organs.png missing"

    print("✓ All static files and assets exist")


def test_index_html_structure():
    """index.html contains all required views."""
    static_dir = Path(__file__).parent.parent / "src" / "ui" / "static"
    html = (static_dir / "index.html").read_text()

    required_views = [
        "view-dashboard",
        "view-bodymap",
        "view-timeline",
        "view-medications",
        "view-labs",
        "view-imaging",
        "view-genetics",
        "view-flags",
        "view-crossdisc",
        "view-community",
        "view-chat",
        "view-alerts",
        "view-report",
    ]

    for view_id in required_views:
        assert view_id in html, f"Missing view: {view_id}"

    # Check passphrase modal
    assert "passphrase-modal" in html
    assert "passphrase-input" in html

    # Check drop zone
    assert "drop-zone" in html

    # Check settings
    assert "settings-overlay" in html

    # Check nav
    assert "nav-tabs" in html

    print(f"✓ index.html has all {len(required_views)} views + modal + drop zone + settings")


def test_app_js_structure():
    """app.js contains all required controllers."""
    static_dir = Path(__file__).parent.parent / "src" / "ui" / "static"
    js = (static_dir / "app.js").read_text()

    # Main controllers
    assert "var App = {" in js or "var App =" in js, "Missing App controller"
    assert "var BodyMap = {" in js or "var BodyMap =" in js, "Missing BodyMap controller"
    assert "var Timeline = {" in js or "var Timeline =" in js, "Missing Timeline controller"

    # Key functions
    assert "escapeHtml" in js, "Missing escapeHtml security function"
    assert "severityBadge" in js, "Missing severityBadge helper"
    assert "formatDate" in js, "Missing formatDate helper"
    assert "formatProvenance" in js, "Missing formatProvenance helper"

    # App methods
    assert "unlock" in js, "Missing unlock method"
    assert "navigateTo" in js, "Missing navigateTo method"
    assert "handleDrop" in js, "Missing handleDrop method"
    assert "startAnalysis" in js, "Missing startAnalysis method"
    assert "listenProgress" in js, "Missing listenProgress method"
    assert "sendChat" in js, "Missing sendChat method"
    assert "generateReport" in js, "Missing generateReport method"
    assert "clearSession" in js, "Missing clearSession method"

    print("✓ app.js has all required controllers and methods")


def test_css_has_all_components():
    """styles.css defines all required component styles."""
    static_dir = Path(__file__).parent.parent / "src" / "ui" / "static"
    css = (static_dir / "styles.css").read_text()

    required = [
        "--bg-primary",
        "--accent-teal",
        "--severity-critical",
        ".nav",
        ".card",
        ".btn",
        ".drop-zone",
        ".progress-bar",
        ".data-table",
        ".badge",
        ".chat-container",
        ".modal",
        ".community-warning",
        ".timeline-item",
        ".bodymap-zone",
        "@media",
    ]

    for item in required:
        assert item in css, f"Missing CSS: {item}"

    print(f"✓ styles.css has all {len(required)} required components")


# ── Run All Tests ────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Phase 8 Tests — Clinical Intelligence Hub UI")
    print("=" * 60)

    # Pipeline
    test_pipeline_import()
    test_pipeline_init()
    test_pipeline_clear_session()
    test_pipeline_has_all_passes()

    # Flask App
    test_flask_app_import()
    test_flask_app_routes_exist()
    test_flask_test_client()
    test_api_returns_empty_without_profile()
    test_api_upload_requires_auth()
    test_api_analyze_requires_auth()
    test_api_chat_requires_profile()
    test_api_report_generate_requires_profile()

    # Static Files
    test_static_files_exist()
    test_index_html_structure()
    test_app_js_structure()
    test_css_has_all_components()

    print()
    print("=" * 60)
    print("All Phase 8 tests passed ✓")
    print("=" * 60)
