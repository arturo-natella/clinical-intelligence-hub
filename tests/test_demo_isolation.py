"""Regression coverage for temporary, non-persistent sample-patient mode."""

from copy import deepcopy


def _configure_real_profile(monkeypatch, tmp_path):
    import src.ui.app as app_module
    from src.encryption import EncryptedVault

    passphrase = "demo-isolation-test"
    real_profile = {
        "demographics": {"location": "Test County, TS"},
        "clinical_timeline": {
            "medications": [{"name": "Test Medication", "status": "active"}],
            "genetics": [],
        },
        "analysis": {},
    }

    vault = EncryptedVault(tmp_path, passphrase)
    profile_id = vault.create_profile("Real profile")
    vault.save_profile(real_profile, profile_id)

    monkeypatch.setattr(app_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(app_module, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(app_module, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(app_module, "_passphrase", passphrase)
    monkeypatch.setattr(app_module, "_active_profile_id", profile_id)
    monkeypatch.setattr(app_module, "_profile_data", deepcopy(real_profile))
    monkeypatch.setattr(app_module, "_demo_mode", False)
    monkeypatch.setattr(app_module, "_profile_data_before_demo", None)
    monkeypatch.setattr(app_module, "_demo_was_persisted", False)
    monkeypatch.setattr(app_module, "_pipeline_thread", None)

    return app_module, vault, profile_id, real_profile


def test_sample_patient_is_temporary_and_restores_real_profile(monkeypatch, tmp_path):
    app_module, vault, profile_id, real_profile = _configure_real_profile(
        monkeypatch, tmp_path
    )

    with app_module.app.test_client() as client:
        opened = client.post("/api/demo-data")
        assert opened.status_code == 200
        assert opened.get_json()["demo_mode"] is True
        assert opened.get_json()["temporary"] is True
        assert app_module._demo_mode is True
        assert app_module._profile_data != real_profile

        # Computing a deep insight mutates the temporary sample in memory, but
        # must never write it into the active encrypted patient profile.
        pgx = client.post("/api/pgx-collisions")
        assert pgx.status_code == 200
        assert pgx.get_json()["summary"]["total_collisions"] >= 1

        vault.active_profile_id = profile_id
        assert vault.load_profile(profile_id) == real_profile

        status = client.get("/api/session/status")
        assert status.get_json()["demo_mode"] is True

        closed = client.post("/api/demo-data/exit")
        assert closed.status_code == 200
        assert closed.get_json()["status"] == "restored"
        assert closed.get_json()["demo_mode"] is False

    assert app_module._demo_mode is False
    assert app_module._profile_data == real_profile
    assert app_module._profile_data_before_demo is None


def test_sample_patient_blocks_analysis_and_external_sync(monkeypatch, tmp_path):
    app_module, _, _, _ = _configure_real_profile(monkeypatch, tmp_path)

    with app_module.app.test_client() as client:
        assert client.post("/api/demo-data").status_code == 200
        analysis = client.post("/api/analyze")
        environmental = client.post("/api/environmental/sync")
        literature = client.post("/api/sweep-now")

    assert analysis.status_code == 409
    assert analysis.get_json() == {
        "error": "Exit the sample patient before analyzing records"
    }
    assert environmental.status_code == 409
    assert environmental.get_json() == {
        "error": "External data sync is disabled for the sample patient"
    }
    assert literature.status_code == 409
    assert literature.get_json() == {
        "error": "External literature search is disabled for the sample patient"
    }
    assert app_module._environmental_sync_ready() is False


def test_sample_patient_cannot_open_during_analysis(monkeypatch, tmp_path):
    app_module, _, _, real_profile = _configure_real_profile(monkeypatch, tmp_path)

    class RunningThread:
        @staticmethod
        def is_alive():
            return True

    monkeypatch.setattr(app_module, "_pipeline_thread", RunningThread())

    with app_module.app.test_client() as client:
        response = client.post("/api/demo-data")

    assert response.status_code == 409
    assert response.get_json() == {
        "error": "Cannot open sample data while analysis is running"
    }
    assert app_module._demo_mode is False
    assert app_module._profile_data == real_profile


def test_exact_legacy_sample_can_be_identified_and_removed(monkeypatch, tmp_path):
    app_module, vault, profile_id, real_profile = _configure_real_profile(
        monkeypatch, tmp_path
    )
    sample = app_module._build_demo_profile()
    sample["analysis"]["pgx_collision_map"] = {"legacy": "saved snapshot"}
    sample["updated_at"] = "2026-08-17T00:00:00Z"

    assert app_module._matches_builtin_demo_profile(sample) is True
    assert app_module._matches_builtin_demo_profile(real_profile) is False

    vault.save_profile(sample, profile_id)
    monkeypatch.setattr(app_module, "_profile_data", sample)
    monkeypatch.setattr(app_module, "_demo_mode", True)
    monkeypatch.setattr(app_module, "_demo_was_persisted", True)

    with app_module.app.test_client() as client:
        repeated_open = client.post("/api/demo-data")
        assert repeated_open.status_code == 200
        assert repeated_open.get_json() == {
            "status": "already_active",
            "has_data": True,
            "demo_mode": True,
            "temporary": False,
            "demo_was_persisted": True,
        }
        response = client.post("/api/demo-data/exit")

    assert response.status_code == 200
    assert response.get_json()["status"] == "sample_removed"
    assert app_module._profile_data == {}
    assert app_module._demo_mode is False

    vault.active_profile_id = profile_id
    assert vault.load_profile(profile_id) == {}


def test_sample_patient_ui_is_explicit_and_pgx_defaults_to_collision():
    from pathlib import Path

    static_dir = Path(__file__).parents[1] / "src" / "ui" / "static"
    html = (static_dir / "index.html").read_text(encoding="utf-8")
    app_js = (static_dir / "app.js").read_text(encoding="utf-8")
    pgx_js = (static_dir / "js" / "pgx_map.js").read_text(encoding="utf-8")

    assert "SAMPLE PATIENT — NOT YOUR MEDICAL RECORD" in html
    assert "Preview Sample Patient" in html
    assert "Exit Sample and Restore My Profile" in html
    assert 'api("/api/demo-data/exit"' in app_js
    assert "fictional demonstration data" in app_js
    assert "SAMPLE DATA DETECTED — NOT YOUR MEDICAL RECORD" in app_js
    assert "Remove Saved Sample Data" in app_js
    assert 'aria-label="Patient profiles"' in html
    assert 'id="profile-action-display"' in html
    assert 'nameEl.textContent = "Patient Profiles"' in app_js
    assert "App._profiles.length === 0 && !App._demoMode" in app_js
    assert 'geneCount === 1 ? "" : "s"' in pgx_js
    assert "self._showEdgeDetail(edges[0], nodeLookup);" in pgx_js
