"""Static contract for the text-size toggle (P8).

The toggle is pure frontend (localStorage + CSS zoom), so pytest guards the
contract the same way the PHI-logging tests guard source: by inspecting the
shipped static assets. Runtime behavior is verified in the browser.
"""

from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "src" / "ui" / "static"


def _read(name):
    return (STATIC / name).read_text(encoding="utf-8")


def test_prepaint_script_applies_stored_scale_before_render():
    html = _read("index.html")
    head = html.split("</head>")[0]
    assert "medprep_text_scale" in head, "pre-paint scale script must live in <head>"
    assert "documentElement.style.zoom" in head
    # Whitelist guard: arbitrary stored values must not reach style.zoom.
    assert "1.15" in head and "1.3" in head


def test_sidebar_has_text_size_button():
    html = _read("index.html")
    assert 'id="text-size-btn"' in html
    assert "App.cycleTextSize" in html
    assert 'id="text-size-label"' in html


def test_app_js_defines_cycle_and_persistence():
    js = _read("app.js")
    assert "TEXT_SCALE_STEPS" in js
    assert "medprep_text_scale" in js
    assert "cycleTextSize" in js
    assert "applyTextScale" in js
    for scale in ("1", "1.15", "1.3"):
        assert f'"{scale}"' in js, f"scale step {scale} missing"
