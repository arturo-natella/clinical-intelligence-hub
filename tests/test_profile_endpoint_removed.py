"""``GET /api/profile`` returned the entire decrypted profile in one response.

Nothing consumed it — the UI reads the narrow per-section endpoints
(/api/medications, /api/labs, /api/diagnoses, …), each of which returns
only its own slice. An unused endpoint that dumps every identifier,
note, and result the vault holds is attack surface with no benefit, so
it was removed rather than left dangling.

If a future feature genuinely needs the whole profile, add a scoped
endpoint for that need instead of restoring the blanket dump.
"""


def _routes():
    from src.ui.app import app

    return {rule.rule for rule in app.url_map.iter_rules()}


def test_bulk_profile_dump_endpoint_is_gone():
    assert "/api/profile" not in _routes()


def test_profiles_management_endpoints_are_untouched():
    """/api/profiles (plural) is a different, live feature — don't break it."""
    routes = _routes()
    assert "/api/profiles" in routes
    assert "/api/profiles/<profile_id>" in routes


def test_scoped_section_endpoints_still_serve_the_ui():
    routes = _routes()
    for route in (
        "/api/medications",
        "/api/labs",
        "/api/diagnoses",
        "/api/imaging",
        "/api/genetics",
        "/api/demographics",
    ):
        assert route in routes, f"{route} is what the UI uses instead"
