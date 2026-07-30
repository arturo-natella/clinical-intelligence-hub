"""Contract for serving the patient-specific 3D mesh to the Body Map.

Pass 1c persists a VolumetricTwin manifest on the profile. The Body Map
needs a way to ask "is there a mesh built from this patient's own scan?"
without the frontend reaching into the whole profile.
"""

from pathlib import Path

import pytest

from src.ui import app as app_module

STATIC = Path(__file__).resolve().parent.parent / "src" / "ui" / "static"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(app_module, "_passphrase", "test-pass")
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


def test_reports_unavailable_without_a_twin(client, monkeypatch):
    monkeypatch.setattr(app_module, "_profile_data", {"analysis": {}})
    body = client.get("/api/patient-mesh").get_json()
    assert body["available"] is False
    assert not body.get("url")


def test_serves_the_twin_url_when_present(client, monkeypatch):
    monkeypatch.setattr(app_module, "_profile_data", {
        "analysis": {
            "volumetric_twin": {
                "url": "/models/patient/patient_twin.glb",
                "generated_at": "2026-07-30T10:00:00",
            }
        }
    })
    body = client.get("/api/patient-mesh").get_json()
    assert body["available"] is True
    assert body["url"] == "/models/patient/patient_twin.glb"
    assert body["generated_at"].startswith("2026-07-30")


def test_never_leaks_local_filesystem_paths(client, monkeypatch):
    """DICOM directory names can carry the patient's name — never serve them."""
    monkeypatch.setattr(app_module, "_profile_data", {
        "analysis": {
            "volumetric_twin": {
                "url": "/models/patient/patient_twin.glb",
                "source_dicom_dir": "/Users/someone/records/Jane Doe CT",
                "path": "/Users/someone/MedPrep/src/ui/static/models/patient/x.glb",
            }
        }
    })
    body = client.get("/api/patient-mesh").get_json()
    assert set(body) <= {"available", "url", "generated_at"}
    assert "Jane" not in str(body)


def test_no_profile_is_not_an_error(client, monkeypatch):
    """Body Map loads before any records exist; this must not 500."""
    monkeypatch.setattr(app_module, "_profile_data", None)
    res = client.get("/api/patient-mesh")
    assert res.status_code == 200
    assert res.get_json()["available"] is False


def test_bodymap_asks_for_the_patient_mesh():
    js = (STATIC / "js" / "bodymap3d.js").read_text(encoding="utf-8")
    assert "/api/patient-mesh" in js, "Body Map never checks for a patient mesh"
    assert "loadPatientMesh" in js


def test_patient_mesh_is_labeled_as_the_patients_own_scan():
    """The user must be able to tell their anatomy from the generic atlas."""
    js = (STATIC / "js" / "bodymap3d.js").read_text(encoding="utf-8")
    loader = js.split("loadPatientMesh:")[1][:3000]
    assert "your scan" in loader.lower() or "your own scan" in loader.lower()
