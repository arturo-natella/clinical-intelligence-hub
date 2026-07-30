"""Contract for the vitals tracker reading its types from the backend.

``VITALS_TYPES`` in app.py is the validation authority: /api/tracker/log
rejects unknown types and out-of-range values against it. The tracker
form used to hardcode a parallel copy of that list, so a type added
backend-side never appeared in the UI, and range rejections only
surfaced after a failed round-trip.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "src" / "ui" / "static"


def _read(name):
    return (STATIC / name).read_text(encoding="utf-8")


def test_frontend_fetches_vitals_types():
    js = _read("app.js")
    assert "/api/tracker/vitals-types" in js, "nothing calls the vitals-types endpoint"
    assert "loadVitalsTypes" in js


def test_types_load_with_the_tracker_view():
    js = _read("app.js")
    body = js.split("loadTracker: async function()")[1].split("\n    },")[0]
    assert "loadVitalsTypes" in body, "tracker view must populate its type list"


def test_select_options_are_rebuilt_from_backend_metadata():
    js = _read("app.js")
    render = js.split("renderVitalsTypes: function")[1].split("\n    },")[0]
    assert "tracker-type" in render
    assert "createElement" in render and "innerHTML" not in render
    # Label + unit come from the backend payload, not a second hardcoded list.
    assert "label" in render and "unit" in render


def test_value_input_gets_range_bounds():
    """Backend rejects out-of-range values; the form should say so first."""
    js = _read("app.js")
    assert "tracker-value" in js
    assert "range" in js.split("renderVitalsTypes: function")[1].split("\n    },")[0] \
        or "applyVitalRange" in js, "range metadata must reach the value input"


def test_hardcoded_options_remain_as_fallback():
    """A failed fetch must leave a usable form, not an empty dropdown."""
    html = _read("index.html")
    select = html.split('id="tracker-type"')[1].split("</select>")[0]
    assert "blood_pressure_sys" in select, "static fallback options were removed"


def test_endpoint_preserves_clinical_ordering():
    """jsonify sorts dict keys, which would lead the form with 'HbA1c' and
    put Diastolic before Systolic. The order in VITALS_TYPES is deliberate —
    most-logged vitals first — so the payload must be an ordered sequence."""
    from src.ui import app as app_module

    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as client:
        payload = client.get("/api/tracker/vitals-types").get_json()

    assert isinstance(payload, list), "a JSON object would be re-sorted by key"
    keys = [entry["key"] for entry in payload]
    assert keys == list(app_module.VITALS_TYPES), "backend ordering was not preserved"
    assert keys[0] == "blood_pressure_sys"
    assert keys.index("blood_pressure_sys") < keys.index("blood_pressure_dia")

    first = payload[0]
    assert first["label"] == "BP Systolic"
    assert first["unit"] == "mmHg"
    assert first["range"] == [70, 200]


def test_every_backend_vital_type_is_reachable():
    """Guard the drift this wiring closes: no UI-only allowlist may shrink it."""
    import re

    app_py = (ROOT / "src" / "ui" / "app.py").read_text(encoding="utf-8")
    block = app_py.split("VITALS_TYPES = {")[1].split("\n}")[0]
    backend_types = set(re.findall(r'"([a-z0-9_]+)":\s*\{"label"', block))
    assert len(backend_types) >= 8

    html = _read("index.html")
    select = html.split('id="tracker-type"')[1].split("</select>")[0]
    fallback_types = set(re.findall(r'value="([a-z0-9_]+)"', select))
    assert backend_types == fallback_types, (
        "fallback options drifted from VITALS_TYPES: "
        f"{backend_types ^ fallback_types}"
    )
