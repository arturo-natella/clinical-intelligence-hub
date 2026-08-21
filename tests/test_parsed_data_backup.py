"""Encrypted parsed-data durability and backup regression tests."""

import json


def _configure_saved_profile(monkeypatch, tmp_path):
    import src.ui.app as app_module
    from src.encryption import EncryptedVault

    passphrase = "parsed-backup-test"
    profile = {
        "updated_at": "2026-08-17T18:30:00-04:00",
        "clinical_timeline": {
            "medications": [{"name": "Synthetic Medication", "status": "active"}],
            "labs": [{"test_name": "Synthetic Lab", "value": "1"}],
            "diagnoses": [],
        },
        "analysis": {},
    }
    vault = EncryptedVault(tmp_path, passphrase)
    profile_id = vault.create_profile("Backup test profile")
    vault.save_profile(profile, profile_id)

    monkeypatch.setattr(app_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(app_module, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(app_module, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(app_module, "_passphrase", passphrase)
    monkeypatch.setattr(app_module, "_active_profile_id", profile_id)
    monkeypatch.setattr(app_module, "_profile_data", profile)
    monkeypatch.setattr(app_module, "_demo_mode", False)
    monkeypatch.setattr(app_module, "_demo_was_persisted", False)
    monkeypatch.setattr(app_module, "_pipeline_thread", None)
    return app_module, passphrase, profile


def test_persistence_status_reports_encrypted_checkpoint_without_phi(monkeypatch, tmp_path):
    app_module, _, _ = _configure_saved_profile(monkeypatch, tmp_path)

    with app_module.app.test_client() as client:
        response = client.get("/api/profile/persistence")

    assert response.status_code == 200
    assert response.get_json() == {
        "automatic": True,
        "backup_available": True,
        "demo_mode": False,
        "encrypted": True,
        "last_saved": "2026-08-17T18:30:00-04:00",
        "parsed_items": 2,
        "pipeline_running": False,
        "saved": True,
    }
    assert "Synthetic Medication" not in response.get_data(as_text=True)
    assert "Synthetic Lab" not in response.get_data(as_text=True)


def test_downloaded_parsed_data_backup_is_encrypted_json(monkeypatch, tmp_path):
    app_module, passphrase, profile = _configure_saved_profile(monkeypatch, tmp_path)
    from src.encryption import decrypt_data

    with app_module.app.test_client() as client:
        response = client.get("/api/profile/backup")

    assert response.status_code == 200
    assert response.mimetype == "application/octet-stream"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Content-Disposition"].endswith('.json.enc"')
    assert b"Synthetic Medication" not in response.data

    payload = json.loads(decrypt_data(response.data, passphrase))
    assert payload["format"] == "medprep-encrypted-parsed-data"
    assert payload["version"] == 1
    assert payload["profile"] == profile


def test_sample_patient_cannot_be_backed_up(monkeypatch, tmp_path):
    app_module, _, _ = _configure_saved_profile(monkeypatch, tmp_path)
    monkeypatch.setattr(app_module, "_demo_mode", True)

    with app_module.app.test_client() as client:
        status = client.get("/api/profile/persistence")
        backup = client.get("/api/profile/backup")

    assert status.status_code == 200
    assert status.get_json()["backup_available"] is False
    assert backup.status_code == 409
    assert backup.get_json() == {"error": "Sample patient data cannot be exported"}


def test_pipeline_checkpoints_use_the_active_named_profile(tmp_path):
    from src.encryption import EncryptedVault
    from src.models import PatientProfile
    from src.ui.pipeline import Pipeline

    passphrase = "named-profile-checkpoint"
    vault = EncryptedVault(tmp_path, passphrase)
    profile_id = vault.create_profile("Named profile")
    original = {"clinical_timeline": {"medications": [], "labs": []}}
    vault.save_profile(original, profile_id)

    pipeline = Pipeline(tmp_path, passphrase, profile_id=profile_id)
    pipeline._init_components()

    assert pipeline._vault.active_profile_id == profile_id
    assert pipeline._vault.load_profile() == original

    pipeline._profile = PatientProfile()
    pipeline._save_profile_checkpoint()

    assert (tmp_path / "profiles" / f"{profile_id}.enc").exists()
    assert not (tmp_path / "patient_profile.enc").exists()
    reloaded = vault.load_profile(profile_id)
    assert reloaded["updated_at"] is not None
    pipeline._db.close()


def test_local_save_ui_explains_autosave_and_encrypted_backup():
    from pathlib import Path

    static_dir = Path(__file__).parents[1] / "src" / "ui" / "static"
    html = (static_dir / "index.html").read_text(encoding="utf-8")
    app_js = (static_dir / "app.js").read_text(encoding="utf-8")

    assert "Your Progress Is Saved Locally" in html
    assert "saved after every completed processing chunk" in html
    assert "Download Encrypted Parsed-Data Backup" in html
    assert "no plaintext medical JSON is written to disk" in html
    assert 'api("/api/profile/persistence")' in app_js
    assert 'window.location.href = "/api/profile/backup"' in app_js
