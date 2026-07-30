"""Static UI contract guards.

Preserved from the former test_phase11.py when the 3D body map was removed
(2026-07-30). These two checks were never body-map specific — they guard the
JS-serving route and the Amaru design tokens that the whole frontend depends on.
"""

from pathlib import Path

STATIC_DIR = Path(__file__).parent.parent / "src" / "ui" / "static"


def test_js_route_exists():
    """JavaScript file serving route exists."""
    from src.ui.app import app

    rules = [rule.rule for rule in app.url_map.iter_rules()]
    assert "/js/<path:filename>" in rules


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

    assert "#0a0a0a" in css, "Missing Amaru bg base"
    assert "#dc2626" in css or "#f05545" in css, "Missing Amaru heat/accent red"


def test_body_map_is_fully_removed():
    """Regression sentinel: no body map references survive anywhere in the UI.

    The 3D body map was removed because a generic cadaver atlas cannot
    represent a specific patient, and its deformation engine fabricated
    organ appearance with no provenance. This guards against reintroduction
    by copy-paste.
    """
    html = (STATIC_DIR / "index.html").read_text()
    js = (STATIC_DIR / "app.js").read_text()
    css = (STATIC_DIR / "styles.css").read_text()

    assert not (STATIC_DIR / "js" / "bodymap3d.js").exists()
    for name, content in (("index.html", html), ("app.js", js), ("styles.css", css)):
        assert "bodymap" not in content.lower(), f"body map reference survives in {name}"

    # Three.js was loaded solely for the body map — the UI must stay free of it
    assert "three.module.js" not in html, "Three.js CDN import survives in index.html"


def test_differential_dx_entry_point_survives():
    """The Differential Dx button lived in the body map toolbar — it must still be reachable."""
    html = (STATIC_DIR / "index.html").read_text()

    assert "SnowballDx.toggle()" in html, "Differential Dx entry point lost"
    assert "/js/snowball.js" in html, "snowball.js no longer loaded"
