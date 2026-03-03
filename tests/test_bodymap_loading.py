"""Test that body map endpoints work without profile data."""
import pytest
from src.ui.app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_demographics_returns_defaults_without_profile(client):
    """Demographics endpoint should return defaults, not error."""
    resp = client.get("/api/demographics")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "biological_sex" in data
