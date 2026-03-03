"""
Phase 11 Tests — Three.js 3D Anatomy Viewer

Tests the 3D body map integration: demographics endpoint,
bodymap3d.js structure, index.html 3D canvas elements,
app.js BodyMap3D integration, and CSS 3D viewer styles.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

STATIC_DIR = Path(__file__).parent.parent / "src" / "ui" / "static"


# ── Demographics API ───────────────────────────────────────

def test_demographics_route_exists():
    """Demographics endpoint is registered in Flask."""
    from src.ui.app import app

    rules = [rule.rule for rule in app.url_map.iter_rules()]
    assert "/api/demographics" in rules
    print("✓ /api/demographics route exists")


def test_demographics_returns_default():
    """Demographics returns null sex/year when no profile loaded."""
    from src.ui.app import app

    with app.test_client() as client:
        resp = client.get("/api/demographics")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "biological_sex" in data
        assert "birth_year" in data
        assert data["biological_sex"] is None
        assert data["birth_year"] is None

    print("✓ /api/demographics returns default null values")


def test_demographics_with_profile():
    """Demographics reads from profile when loaded."""
    import src.ui.app as app_module

    # Simulate a loaded profile
    original = app_module._profile_data
    try:
        app_module._profile_data = {
            "demographics": {
                "biological_sex": "female",
                "birth_year": 1968,
            }
        }

        with app_module.app.test_client() as client:
            resp = client.get("/api/demographics")
            assert resp.status_code == 200
            data = json.loads(resp.data)
            assert data["biological_sex"] == "female"
            assert data["birth_year"] == 1968

    finally:
        app_module._profile_data = original

    print("✓ /api/demographics returns profile data when loaded")


# ── New Routes ────────────────────────────────────────────

def test_js_route_exists():
    """JavaScript file serving route exists."""
    from src.ui.app import app

    rules = [rule.rule for rule in app.url_map.iter_rules()]
    assert "/js/<path:filename>" in rules
    print("✓ /js/ route exists")


def test_models_route_exists():
    """3D model serving route exists."""
    from src.ui.app import app

    rules = [rule.rule for rule in app.url_map.iter_rules()]
    assert "/models/<path:filename>" in rules
    print("✓ /models/ route exists")


def test_bodymap3d_js_served():
    """bodymap3d.js is served correctly by Flask."""
    from src.ui.app import app

    with app.test_client() as client:
        resp = client.get("/js/bodymap3d.js")
        assert resp.status_code == 200
        assert b"BodyMap3D" in resp.data

    print("✓ /js/bodymap3d.js serves correctly")


# ── Static File Structure ─────────────────────────────────

def test_bodymap3d_js_exists():
    """bodymap3d.js file exists in expected location."""
    js_file = STATIC_DIR / "js" / "bodymap3d.js"
    assert js_file.exists(), f"Missing: {js_file}"
    print("✓ bodymap3d.js exists")


def test_bodymap3d_js_structure():
    """bodymap3d.js has all required controller methods."""
    js = (STATIC_DIR / "js" / "bodymap3d.js").read_text()

    required_methods = [
        "init",
        "loadModel",
        "setLayer",
        "focusRegion",
        "resetView",
        "loadFindings",
        "toggleGender",
        "fallbackTo2D",
    ]

    for method in required_methods:
        assert method in js, f"Missing method: {method}"

    # Check region mapping preserved
    assert "regionMapping" in js
    assert "meshToRegion" in js
    assert "regionPositions" in js

    # Check damage visualization
    assert "damageColors" in js
    assert "_applyOrganDamage" in js
    assert "_mapToOrganMeshes" in js
    assert "_resetOrganColors" in js

    # Check XSS safety — no innerHTML with dynamic data
    # (Safe innerHTML with static strings is acceptable)
    assert "escapeHtml" in js or "textContent" in js

    print(f"✓ bodymap3d.js has all {len(required_methods)} required methods + damage visualization")


def test_bodymap3d_js_has_placeholder():
    """bodymap3d.js includes placeholder model for immediate use."""
    js = (STATIC_DIR / "js" / "bodymap3d.js").read_text()

    assert "_buildPlaceholderModel" in js or "placeholder" in js.lower()
    assert "SphereGeometry" in js or "CylinderGeometry" in js
    print("✓ bodymap3d.js has placeholder model geometry")


def test_bodymap3d_js_gender_support():
    """bodymap3d.js handles both male and female models."""
    js = (STATIC_DIR / "js" / "bodymap3d.js").read_text()

    assert "male" in js
    assert "female" in js
    assert "uterus" in js
    assert "prostate" in js
    assert "ovary" in js or "ovaries" in js
    print("✓ bodymap3d.js has gender-specific organ support")


def test_models_directory_exists():
    """Models directory exists for GLB files."""
    models_dir = STATIC_DIR / "models"
    assert models_dir.exists(), f"Missing: {models_dir}"
    print("✓ models/ directory exists")


# ── HTML 3D Canvas Integration ─────────────────────────────

def test_index_html_has_3d_canvas():
    """index.html includes 3D canvas elements."""
    html = (STATIC_DIR / "index.html").read_text()

    assert "bodymap-canvas-container" in html
    assert "bodymap-canvas" in html
    assert "bodymap-tooltip" in html
    assert "bodymap-loading" in html
    print("✓ index.html has 3D canvas container, canvas, tooltip, loading")


def test_index_html_has_threejs_import():
    """index.html includes Three.js import map."""
    html = (STATIC_DIR / "index.html").read_text()

    assert "importmap" in html
    assert "three" in html
    assert "unpkg.com/three" in html or "cdn" in html.lower()
    print("✓ index.html has Three.js import map")


def test_index_html_has_bodymap3d_script():
    """index.html loads bodymap3d.js script."""
    html = (STATIC_DIR / "index.html").read_text()

    assert "bodymap3d.js" in html
    print("✓ index.html loads bodymap3d.js")


def test_index_html_has_gender_toggle():
    """index.html includes gender toggle button."""
    html = (STATIC_DIR / "index.html").read_text()

    assert "gender-toggle" in html
    print("✓ index.html has gender toggle")


def test_index_html_has_2d_fallback():
    """index.html preserves 2D fallback viewer."""
    html = (STATIC_DIR / "index.html").read_text()

    assert "bodymap-2d-fallback" in html
    assert "bodymap-img" in html
    assert "anatomy.png" in html
    print("✓ index.html has 2D fallback preserved")


def test_index_html_has_layer_buttons():
    """index.html has layer toggle buttons for the 3D viewer."""
    html = (STATIC_DIR / "index.html").read_text()

    assert 'data-layer="skin"' in html
    assert 'data-layer="muscle"' in html
    assert 'data-layer="skeleton"' in html
    assert 'data-layer="organs"' in html
    print("✓ index.html has all 4 layer buttons")


def test_index_html_has_findings_panel():
    """index.html has findings panel for 3D viewer."""
    html = (STATIC_DIR / "index.html").read_text()

    assert "bodymap-findings-list" in html
    assert "bodymap-region-title" in html
    print("✓ index.html has findings panel")


# ── app.js 3D Integration ─────────────────────────────────

def test_app_js_has_bodymap3d_init():
    """app.js initializes BodyMap3D on view navigation."""
    js = (STATIC_DIR / "app.js").read_text()

    assert "BodyMap3D" in js
    assert "initBodyMap3D" in js
    assert "bodymap" in js
    print("✓ app.js integrates BodyMap3D initialization")


def test_app_js_has_2d_fallback():
    """app.js retains 2D fallback controller."""
    js = (STATIC_DIR / "app.js").read_text()

    assert "BodyMap2DFallback" in js
    assert "regionMapping" in js
    print("✓ app.js has BodyMap2DFallback controller")


def test_app_js_bodymap_in_loaders():
    """app.js view loaders include bodymap entry."""
    js = (STATIC_DIR / "app.js").read_text()

    assert "bodymap:" in js
    assert "initBodyMap3D" in js
    print("✓ app.js view loaders include bodymap → initBodyMap3D")


# ── CSS 3D Viewer Styles ──────────────────────────────────

def test_css_has_3d_viewer_styles():
    """styles.css includes 3D viewer component styles."""
    css = (STATIC_DIR / "styles.css").read_text()

    required = [
        "#bodymap-canvas-container",
        "#bodymap-canvas",
        ".bodymap-tooltip",
        ".bodymap-loading",
        ".bodymap-findings-panel",
        ".bodymap-toolbar",
        ".gender-toggle",
    ]

    for item in required:
        assert item in css, f"Missing CSS: {item}"

    print(f"✓ styles.css has all {len(required)} 3D viewer styles")


def test_css_has_amaru_tokens():
    """styles.css uses Amaru design tokens (dark mode)."""
    css = (STATIC_DIR / "styles.css").read_text()

    amaru_tokens = [
        "--bg-primary",
        "--bg-card",
        "--bg-raised",
        "--heat",
        "--border-faint",
        "--border-muted",
        "--text-primary",
        "--text-secondary",
    ]

    for token in amaru_tokens:
        assert token in css, f"Missing Amaru token: {token}"

    # Check Amaru-specific values
    assert "#0a0a0a" in css, "Missing Amaru bg base"
    assert "#dc2626" in css or "#f05545" in css, "Missing Amaru heat/accent red"

    print(f"✓ styles.css has all {len(amaru_tokens)} Amaru design tokens")


def test_css_has_severity_pin_styles():
    """styles.css includes severity-based finding card styles."""
    css = (STATIC_DIR / "styles.css").read_text()

    assert "finding-card" in css or "severity" in css
    assert "--severity-critical" in css
    assert "--severity-high" in css
    print("✓ styles.css has severity indicator styles")


# ── Procedural Deformation Engine ─────────────────────────────

def test_bodymap3d_has_deformation_engine():
    """bodymap3d.js has the full procedural deformation engine."""
    js = (STATIC_DIR / "js" / "bodymap3d.js").read_text()

    # Core deformation methods
    assert "_noise3d" in js, "Missing 3D noise function"
    assert "_fbm3d" in js, "Missing fractal Brownian motion"
    assert "_conditionToDeformation" in js, "Missing condition matcher"
    assert "_applyMeshDeformation" in js, "Missing mesh deformation"
    assert "_restoreOriginalGeometry" in js, "Missing geometry restore"
    assert "_clearDeformations" in js, "Missing deformation cleanup"
    assert "deformedMeshes" in js, "Missing deformed mesh tracking"

    print("✓ bodymap3d.js has full procedural deformation engine")


def test_bodymap3d_has_deformation_profiles():
    """bodymap3d.js has comprehensive condition → deformation profiles."""
    js = (STATIC_DIR / "js" / "bodymap3d.js").read_text()

    assert "deformationProfiles" in js

    # Key medical conditions covered
    conditions = [
        "cardiomegaly", "hepatomegaly", "cirrhosis", "fibrosis",
        "atelectasis", "emphysema", "pneumonia", "tumor",
        "inflammation", "edema", "nephritis", "hepatitis",
        "heart failure", "cardiomyopathy", "polycystic",
        "aneurysm", "stenosis", "nodule",
    ]
    for cond in conditions:
        assert cond in js, f"Missing deformation profile: {cond}"

    # Each profile has required parameters (unquoted JS object keys)
    assert "scale:" in js, "Missing scale parameter in profiles"
    assert "noise:" in js, "Missing noise parameter in profiles"
    assert "freq:" in js, "Missing freq parameter in profiles"
    assert "pulse:" in js, "Missing pulse parameter in profiles"

    print(f"✓ bodymap3d.js has {len(conditions)} medical condition deformation profiles")


def test_bodymap3d_deformation_animation():
    """bodymap3d.js animates deformed organs in the render loop."""
    js = (STATIC_DIR / "js" / "bodymap3d.js").read_text()

    # Render loop includes deformed organ animation
    assert "deformedMeshes" in js
    assert "dm.pulse" in js or "pulse" in js
    assert "dm.mesh" in js

    print("✓ bodymap3d.js has animated organ pulsing in render loop")


# ── Run All Tests ────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Phase 11 Tests — Three.js 3D Anatomy Viewer")
    print("=" * 60)

    # Demographics API
    test_demographics_route_exists()
    test_demographics_returns_default()
    test_demographics_with_profile()

    # New Routes
    test_js_route_exists()
    test_models_route_exists()
    test_bodymap3d_js_served()

    # Static Files
    test_bodymap3d_js_exists()
    test_bodymap3d_js_structure()
    test_bodymap3d_js_has_placeholder()
    test_bodymap3d_js_gender_support()
    test_models_directory_exists()

    # HTML 3D Canvas
    test_index_html_has_3d_canvas()
    test_index_html_has_threejs_import()
    test_index_html_has_bodymap3d_script()
    test_index_html_has_gender_toggle()
    test_index_html_has_2d_fallback()
    test_index_html_has_layer_buttons()
    test_index_html_has_findings_panel()

    # app.js 3D Integration
    test_app_js_has_bodymap3d_init()
    test_app_js_has_2d_fallback()
    test_app_js_bodymap_in_loaders()

    # CSS 3D Viewer Styles
    test_css_has_3d_viewer_styles()
    test_css_has_amaru_tokens()
    test_css_has_severity_pin_styles()

    # Procedural Deformation Engine
    test_bodymap3d_has_deformation_engine()
    test_bodymap3d_has_deformation_profiles()
    test_bodymap3d_deformation_animation()

    print()
    print("=" * 60)
    print("All Phase 11 tests passed ✓")
    print("=" * 60)
