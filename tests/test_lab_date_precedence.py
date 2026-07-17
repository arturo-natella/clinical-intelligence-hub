"""Regression tests: lab date field precedence.

The canonical Pydantic model (src/models.py LabResult) stores dates in
`test_date`. Dashboard helpers must read `test_date` first, falling back to
legacy `date` / `collected_date` keys. Reading only the legacy keys makes
every real extracted lab sort on "" — "latest" becomes arbitrary and trend
charts collapse (bug observed 2026-04-15, regressed since).
"""

from src.ui.app import _get_latest_labs, _get_lab_trends


def _lab(name, value, **date_fields):
    return {"name": name, "value": value, "unit": "mg/dL", **date_fields}


def test_latest_labs_uses_test_date():
    labs = [
        _lab("HbA1c", 5.4, test_date="2020-01-15"),   # older listed first
        _lab("HbA1c", 6.2, test_date="2024-03-01"),
    ]
    latest = {l["name"]: l for l in _get_latest_labs(labs)}
    assert latest["HbA1c"]["value"] == 6.2


def test_latest_labs_prefers_test_date_over_legacy_keys():
    labs = [
        _lab("LDL", 90, date="2024-06-01"),                        # legacy key only
        _lab("LDL", 120, test_date="2023-01-01", date="2019-01-01"),  # canonical wins over stale legacy
    ]
    latest = {l["name"]: l for l in _get_latest_labs(labs)}
    # 2024-06-01 (legacy) is the most recent effective date
    assert latest["LDL"]["value"] == 90


def test_lab_trends_carries_test_date_through():
    labs = [
        _lab("Glucose", 100, test_date="2022-01-01"),
        _lab("Glucose", 110, test_date="2023-01-01"),
        _lab("Glucose", 105, test_date="2024-01-01"),
    ]
    trends = _get_lab_trends(labs)
    assert "Glucose" in trends
    dates = [p["date"] for p in trends["Glucose"]]
    assert dates == ["2022-01-01", "2023-01-01", "2024-01-01"]


def test_lab_trends_skips_undated_points():
    labs = [
        _lab("Ferritin", 50, test_date="2022-01-01"),
        _lab("Ferritin", 60, test_date="2023-01-01"),
        _lab("Ferritin", 70, test_date="2024-01-01"),
        _lab("Ferritin", 999),  # no date at all — must not pollute the trend
    ]
    trends = _get_lab_trends(labs)
    assert len(trends["Ferritin"]) == 3
    assert all(p["date"] for p in trends["Ferritin"])
