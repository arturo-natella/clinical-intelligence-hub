"""
Phase 8 Tests — Clinical Intelligence Hub UI

Tests Flask server routes, pipeline orchestrator structure,
and static file serving. Does not test actual browser rendering
(that requires manual verification).
"""

import io
import json
import sqlite3
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Pipeline Tests ──────────────────────────────────────────

def test_pipeline_import():
    """Pipeline module imports without errors."""
    from src.ui.pipeline import Pipeline
    assert Pipeline is not None
    print("✓ Pipeline imports successfully")


def test_pipeline_init():
    """Pipeline initializes with required args."""
    from src.ui.pipeline import Pipeline

    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        pipeline = Pipeline(data_dir, "test-passphrase")
        assert pipeline.data_dir == data_dir
    print("✓ Pipeline initializes correctly")


def test_pipeline_clear_session():
    """Pipeline clear_session doesn't crash on empty state."""
    from src.ui.pipeline import Pipeline

    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        pipeline = Pipeline(data_dir, "test-passphrase")
        # Should not raise on empty state
        pipeline.clear_session()
    print("✓ Pipeline clear_session works on empty state")


def test_pipeline_has_all_passes():
    """Pipeline has methods for all 6 passes."""
    from src.ui.pipeline import Pipeline

    with tempfile.TemporaryDirectory() as tmpdir:
        pipeline = Pipeline(Path(tmpdir), "test")

        # Check all pass methods exist
        assert hasattr(pipeline, "_pass_0_preprocess")
        assert hasattr(pipeline, "_pass_1a_text_extraction")
        assert hasattr(pipeline, "_pass_image_analysis")
        assert hasattr(pipeline, "_pass_1_5_redaction")
        assert hasattr(pipeline, "_pass_2_4_cloud_analysis")
        assert hasattr(pipeline, "_pass_5_validation")
        assert hasattr(pipeline, "_pass_6_report")
        assert hasattr(pipeline, "run")
        assert hasattr(pipeline, "clear_session")
    print("✓ Pipeline has all pass methods")


def test_pipeline_merge_extraction_results_keeps_all_categories():
    """Pipeline merge helper should not silently drop non-core extraction types."""
    from src.models import PatientProfile
    from src.ui.pipeline import Pipeline

    with tempfile.TemporaryDirectory() as tmpdir:
        pipeline = Pipeline(Path(tmpdir), "test-passphrase")
        pipeline._profile = PatientProfile()

        pipeline._merge_extraction_results(
            {
                "medications": [
                    {
                        "name": "Lisinopril",
                        "status": "active",
                        "provenance": {"source_file": "test.pdf", "source_page": 1},
                    }
                ],
                "procedures": [
                    {
                        "name": "Colonoscopy",
                        "procedure_date": "2024-01-02",
                        "provenance": {"source_file": "test.pdf", "source_page": 2},
                    }
                ],
                "allergies": [
                    {
                        "allergen": "Penicillin",
                        "reaction": "Rash",
                        "provenance": {"source_file": "test.pdf", "source_page": 3},
                    }
                ],
                "genetics": [
                    {
                        "gene": "CYP2C19",
                        "phenotype": "Poor Metabolizer",
                        "provenance": {"source_file": "test.pdf", "source_page": 4},
                    }
                ],
                "notes": [
                    {
                        "summary": "Follow-up visit discussed fatigue.",
                        "note_date": "2024-02-03",
                        "provenance": {"source_file": "test.pdf", "source_page": 5},
                    }
                ],
            },
            {},
        )

        tl = pipeline._profile.clinical_timeline
        assert len(tl.medications) == 1
        assert len(tl.procedures) == 1
        assert tl.procedures[0].procedure_date == date(2024, 1, 2)
        assert len(tl.allergies) == 1
        assert len(tl.genetics) == 1
        assert len(tl.notes) == 1

    print("✓ Pipeline merge helper keeps all extraction categories")


def test_pipeline_lab_dedup_uses_loinc_identity_across_name_variants():
    """The same coded measurement from two providers must not form duplicate rows."""
    from src.models import PatientProfile
    from src.ui.pipeline import Pipeline

    with tempfile.TemporaryDirectory() as tmpdir:
        pipeline = Pipeline(Path(tmpdir), "test-passphrase")
        pipeline._profile = PatientProfile()

        pipeline._append_extraction_results({
            "labs": [
                {
                    "name": "Hemoglobin A1c",
                    "value": 7.2,
                    "unit": "%",
                    "test_date": "2025-01-10",
                    "provenance": {"source_file": "provider_a.pdf"},
                },
                {
                    "name": "HbA1c",
                    "value": 7.2,
                    "unit": "%",
                    "test_date": "2025-01-10",
                    "provenance": {"source_file": "provider_b.pdf"},
                },
            ],
        })

        labs = pipeline._profile.clinical_timeline.labs
        assert len(labs) == 1
        assert labs[0].loinc_code == "4548-4"
        assert labs[0].reference_low == 4.0
        assert labs[0].reference_high == 5.6


def test_pipeline_lab_dedup_preserves_distinct_dated_measurements():
    """LOINC normalization must still preserve a patient's longitudinal history."""
    from src.models import PatientProfile
    from src.ui.pipeline import Pipeline

    with tempfile.TemporaryDirectory() as tmpdir:
        pipeline = Pipeline(Path(tmpdir), "test-passphrase")
        pipeline._profile = PatientProfile()

        pipeline._append_extraction_results({
            "labs": [
                {
                    "name": "A1c",
                    "value": 7.2,
                    "unit": "%",
                    "test_date": "2025-01-10",
                    "provenance": {"source_file": "january.pdf"},
                },
                {
                    "name": "Hemoglobin A1c",
                    "value": 6.8,
                    "unit": "%",
                    "test_date": "2025-04-10",
                    "provenance": {"source_file": "april.pdf"},
                },
            ],
        })

        labs = pipeline._profile.clinical_timeline.labs
        assert len(labs) == 2
        assert {lab.loinc_code for lab in labs} == {"4548-4"}


def test_pipeline_publish_profile_snapshot_checkpoints_and_counts_all_items():
    """Publishing a snapshot should save the profile and count all timeline items."""
    from src.models import (
        Allergy,
        ClinicalNote,
        Diagnosis,
        GeneticVariant,
        LabResult,
        Medication,
        PatientProfile,
        Procedure,
        Provenance,
    )
    from src.ui.pipeline import Pipeline

    saved = []
    progress_events = []

    class StubVault:
        def save_profile(self, profile_data):
            saved.append(profile_data)

    with tempfile.TemporaryDirectory() as tmpdir:
        pipeline = Pipeline(
            Path(tmpdir),
            "test-passphrase",
            progress_callback=lambda pass_name, message, percent: progress_events.append(
                (pass_name, message, percent)
            ),
            profile_update_callback=lambda snapshot: saved.append({"snapshot": snapshot}),
        )
        pipeline._vault = StubVault()
        pipeline._profile = PatientProfile()

        prov = Provenance(source_file="test.pdf", source_page=1)
        tl = pipeline._profile.clinical_timeline
        tl.medications.append(
            Medication(name="Lisinopril", provenance=prov)
        )
        tl.labs.append(
            LabResult(name="A1c", value=7.2, provenance=prov)
        )
        tl.diagnoses.append(
            Diagnosis(name="Diabetes", provenance=prov)
        )
        tl.procedures.append(
            Procedure(name="Colonoscopy", provenance=prov)
        )
        tl.allergies.append(
            Allergy(allergen="Penicillin", provenance=prov)
        )
        tl.genetics.append(
            GeneticVariant(gene="CYP2C19", provenance=prov)
        )
        tl.notes.append(
            ClinicalNote(summary="Follow-up note", provenance=prov)
        )

        pipeline._publish_profile_snapshot()

        assert any("snapshot" in entry for entry in saved)
        assert any("clinical_timeline" in entry for entry in saved if isinstance(entry, dict) and "snapshot" not in entry)
        assert progress_events[-1][0] == "profile_updated"
        assert "7 clinical items" in progress_events[-1][1]

    print("✓ Pipeline snapshot publishes, checkpoints, and counts all items")


def test_pipeline_text_extraction_resumes_from_sqlite_chunk_checkpoint(
    monkeypatch,
):
    """A restarted pipeline skips chunks already saved to the encrypted profile."""
    from types import SimpleNamespace

    from src.database import Database
    from src.extraction.text_extractor import MODEL_NAME
    from src.models import ClinicalNote, PatientProfile, Provenance
    from src.ui.pipeline import Pipeline

    class FakeOllama:
        def __init__(self):
            self.chat_calls = []

        def list(self):
            return SimpleNamespace(
                models=[SimpleNamespace(model=MODEL_NAME)],
            )

        def chat(self, **kwargs):
            self.chat_calls.append(kwargs)
            return {
                "message": {
                    "content": json.dumps({
                        "notes": [{"summary": "second chunk result"}],
                    }),
                },
            }

        def generate(self, **kwargs):
            return {}

    class StubVault:
        def __init__(self):
            self.saved = []

        def save_profile(self, profile_data):
            self.saved.append(profile_data)

    fake_ollama = FakeOllama()
    monkeypatch.setitem(sys.modules, "ollama", fake_ollama)

    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        db = Database(data_dir / "cih.db")
        db.upsert_file_state(
            file_id="resume-file",
            filename="record.pdf",
            file_type="pdf_text",
            sha256_hash="resume-hash",
            file_size_bytes=100,
            status="extracting",
            page_count=3,
        )
        db.update_text_checkpoint(
            "resume-file",
            chunks_completed=1,
            chunks_total=2,
        )

        pipeline = Pipeline(data_dir, "test-passphrase")
        pipeline._db = db
        pipeline._vault = StubVault()
        pipeline._profile = PatientProfile()
        pipeline._profile.clinical_timeline.notes.append(
            ClinicalNote(
                summary="first chunk result",
                provenance=Provenance(
                    source_file="record.pdf",
                    source_page=1,
                ),
            )
        )
        pages = [
            {"page": page, "text": f"Page {page} " + ("x" * 5000)}
            for page in range(1, 4)
        ]
        pipeline._pass_1a_text_extraction([{
            "file_id": "resume-file",
            "filename": "record.pdf",
            "file_type": "pdf_text",
            "text": "\n".join(page["text"] for page in pages),
            "pages": pages,
            "text_chunks_completed": 1,
            "text_chunks_total": 2,
        }])

        checkpoint = db.get_file_state_by_hash("resume-hash")
        summaries = {
            note.summary
            for note in pipeline._profile.clinical_timeline.notes
        }

        assert len(fake_ollama.chat_calls) == 1
        assert checkpoint["text_chunks_completed"] == 2
        assert checkpoint["text_chunks_total"] == 2
        assert summaries == {"first chunk result", "second chunk result"}
        assert pipeline._vault.saved
        db.close()


def test_partial_checkpoint_cannot_pass_local_gate_when_model_is_unavailable(
    monkeypatch,
):
    """Prior results do not excuse unfinished chunks on a resumed run."""
    from types import SimpleNamespace

    from src.database import Database
    from src.models import ClinicalNote, PatientProfile, Provenance
    from src.ui.pipeline import Pipeline

    monkeypatch.setitem(
        sys.modules,
        "ollama",
        SimpleNamespace(
            list=lambda: SimpleNamespace(
                models=[SimpleNamespace(model="some-other-model")],
            ),
        ),
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        db = Database(data_dir / "cih.db")
        db.upsert_file_state(
            file_id="partial-file",
            filename="record.pdf",
            file_type="pdf_text",
            sha256_hash="partial-hash",
            file_size_bytes=100,
            status="extracting",
            page_count=3,
        )
        db.update_text_checkpoint(
            "partial-file",
            chunks_completed=1,
            chunks_total=2,
        )

        pipeline = Pipeline(data_dir, "test-passphrase")
        pipeline._db = db
        pipeline._profile = PatientProfile()
        pipeline._profile.clinical_timeline.notes.append(
            ClinicalNote(
                summary="first chunk result",
                provenance=Provenance(source_file="record.pdf"),
            )
        )
        pages = [
            {"page": page, "text": f"Page {page} " + ("x" * 5000)}
            for page in range(1, 4)
        ]

        pipeline._pass_1a_text_extraction([{
            "file_id": "partial-file",
            "filename": "record.pdf",
            "file_type": "pdf_text",
            "text": "\n".join(page["text"] for page in pages),
            "pages": pages,
            "text_chunks_completed": 1,
            "text_chunks_total": 2,
        }])

        checkpoint = db.get_file_state("partial-file")
        assert checkpoint["text_chunks_completed"] == 1
        assert "Local text extraction did not finish all chunks" in (
            pipeline._local_processing_errors
        )
        db.close()


def test_pipeline_runs_external_stages_only_after_local_processing():
    """Cloud and validation stages must start after every local stage finishes."""
    import threading

    from src.ui.pipeline import Pipeline

    events = []

    class StubDB:
        def start_pipeline_run(self, run_id):
            events.append("run_started")

        def complete_pipeline_run(self, run_id, files_processed, files_failed):
            events.append("run_completed")

        def update_file_status(self, *args, **kwargs):
            pass

    class StubVault:
        def load_profile(self):
            return None

        def save_profile(self, profile):
            pass

    with tempfile.TemporaryDirectory() as tmpdir:
        api_calls = threading.Event()
        api_calls.set()
        pipeline = Pipeline(
            Path(tmpdir),
            "test-passphrase",
            api_calls_event=api_calls,
        )
        pipeline._start_caffeinate = lambda: None
        pipeline._stop_caffeinate = lambda: None

        def init_components():
            pipeline._db = StubDB()
            pipeline._vault = StubVault()

        pipeline._init_components = init_components
        pipeline._pass_0_preprocess = lambda files: [
            {"file_id": "file-1", "filename": "record.pdf"}
        ]
        pipeline._pass_1a_text_extraction = lambda items: events.append("local_text")
        pipeline._pass_image_analysis = lambda items: events.append("local_imaging")
        pipeline._pass_1_5_redaction = lambda: events.append("redaction") or True
        pipeline._pass_2_4_cloud_analysis = lambda: events.append("cloud")
        pipeline._pass_5_validation = lambda: events.append("validation")
        pipeline._pass_6_report = lambda: events.append("report")

        pipeline.run([Path(tmpdir) / "record.pdf"])

    assert events.index("redaction") < events.index("cloud")
    assert events.index("cloud") < events.index("validation")
    assert events.index("local_text") < events.index("cloud")
    assert events.index("local_imaging") < events.index("cloud")

    print("✓ External stages run only after local processing")


def test_pipeline_skips_external_stages_when_local_processing_is_incomplete():
    """A local preprocessing failure must prevent every external API stage."""
    from src.ui.pipeline import Pipeline

    events = []

    class StubDB:
        def start_pipeline_run(self, run_id):
            pass

        def complete_pipeline_run(self, run_id, files_processed, files_failed):
            pass

    class StubVault:
        def load_profile(self):
            return None

        def save_profile(self, profile):
            pass

    with tempfile.TemporaryDirectory() as tmpdir:
        pipeline = Pipeline(Path(tmpdir), "test-passphrase")
        pipeline._start_caffeinate = lambda: None
        pipeline._stop_caffeinate = lambda: None

        def init_components():
            pipeline._db = StubDB()
            pipeline._vault = StubVault()

        pipeline._init_components = init_components
        pipeline._pass_0_preprocess = lambda files: []
        pipeline._pass_1a_text_extraction = lambda items: None
        pipeline._pass_image_analysis = lambda items: None
        pipeline._pass_1_5_redaction = lambda: True
        pipeline._pass_2_4_cloud_analysis = lambda: events.append("cloud")
        pipeline._pass_5_validation = lambda: events.append("validation")
        pipeline._pass_6_report = lambda: events.append("report")

        pipeline.run([Path(tmpdir) / "bad-record.pdf"])

    assert "cloud" not in events
    assert "validation" not in events
    assert events == ["report"]

    print("✓ Incomplete local processing blocks external stages")


def test_pipeline_pdf_image_failure_blocks_paid_api_gate(monkeypatch):
    """An embedded-image failure in a PDF must fail the local safety gate."""
    from types import SimpleNamespace

    from src.models import PatientProfile
    from src.ui.pipeline import Pipeline

    class FailingImagePipeline:
        def __init__(self, *args, **kwargs):
            pass

        def process(self, preprocessed, profile):
            return SimpleNamespace(
                images_found=1,
                vision_succeeded=0,
                vision_failed=1,
                errors=["MedGemma vision inference failed"],
            )

    monkeypatch.setitem(
        sys.modules,
        "src.imaging.image_pipeline",
        SimpleNamespace(ImagePipeline=FailingImagePipeline),
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        pipeline = Pipeline(Path(tmpdir), "test-passphrase")
        pipeline._profile = PatientProfile()
        pipeline._publish_profile_snapshot = lambda: None

        pipeline._pass_image_analysis([
            {
                "filename": "record.pdf",
                "file_type": "pdf_text",
            }
        ])

        assert pipeline._local_processing_errors == [
            "Local image processing: MedGemma vision inference failed"
        ]
        assert not pipeline._local_processing_ready(
            [{"filename": "record.pdf"}],
            expected_file_count=1,
            redaction_ok=True,
        )


def test_pipeline_waits_at_api_boundary_while_api_calls_are_paused():
    """The API event must block external work without blocking local passes."""
    import threading

    from src.ui.pipeline import Pipeline

    api_calls = threading.Event()
    started = threading.Event()
    finished = threading.Event()
    progress = []
    pipeline = Pipeline(
        Path(tempfile.gettempdir()),
        "test-passphrase",
        progress_callback=lambda *event: progress.append(event),
        api_calls_event=api_calls,
    )

    def wait_at_boundary():
        started.set()
        pipeline._wait_for_api_calls("test cloud stage", 75)
        finished.set()

    worker = threading.Thread(target=wait_at_boundary)
    worker.start()
    assert started.wait(timeout=1)
    assert not finished.wait(timeout=0.05)
    assert progress[-1][0] == "api_waiting"

    api_calls.set()
    assert finished.wait(timeout=1)
    worker.join(timeout=1)

    print("✓ Paused API event blocks at the external-call boundary")


# ── Flask App Tests ─────────────────────────────────────────

def test_flask_app_import():
    """Flask app imports without errors."""
    from src.ui.app import app
    assert app is not None
    print("✓ Flask app imports successfully")


def test_flask_app_adds_repo_root_to_sys_path():
    """App entrypoint makes the repo root importable for script launches."""
    import src.ui.app as app_module

    assert str(app_module.BASE_DIR) in sys.path
    print("✓ Flask app adds repo root to sys.path")


def test_flask_app_requires_explicit_passphrase_bypass(monkeypatch):
    """An absent bypass setting must leave the vault locked."""
    import src.ui.app as app_module

    monkeypatch.delenv("MEDPREP_SKIP_PASSPHRASE", raising=False)
    monkeypatch.setattr(app_module, "_passphrase", None)

    assert app_module._passphrase_bypass_enabled() is False
    assert app_module._activate_dev_passphrase_bypass() is False
    assert app_module._passphrase is None

    print("✓ Flask app keeps the passphrase gate enabled by default")


def test_flask_app_can_bypass_passphrase_for_local_dev(monkeypatch):
    """Local dev bypass can mark the session unlocked without a vault passphrase."""
    import src.ui.app as app_module

    original_passphrase = app_module._passphrase
    monkeypatch.setenv("MEDPREP_SKIP_PASSPHRASE", "1")

    try:
        app_module._passphrase = None
        assert app_module._activate_dev_passphrase_bypass() is True
        assert app_module._passphrase == app_module._DEV_BYPASS_SENTINEL
    finally:
        app_module._passphrase = original_passphrase

    print("✓ Flask app supports temporary local passphrase bypass")


def test_api_unlock_rejects_blank_passphrase_by_default(monkeypatch):
    """A blank unlock request cannot activate the development sentinel by default."""
    import src.ui.app as app_module

    monkeypatch.delenv("MEDPREP_SKIP_PASSPHRASE", raising=False)
    monkeypatch.setattr(app_module, "_passphrase", None)
    monkeypatch.setattr(app_module, "_profile_data", None)

    with app_module.app.test_client() as client:
        response = client.post("/api/unlock", json={"passphrase": ""})

    assert response.status_code == 400
    assert response.get_json() == {"error": "Passphrase is required"}
    assert app_module._passphrase is None

    print("✓ Blank unlock requests leave the vault locked by default")


def test_api_profile_creation_requires_real_passphrase_by_default(monkeypatch, tmp_path):
    """The safe default cannot create a profile encrypted with the dev sentinel."""
    import src.ui.app as app_module

    monkeypatch.delenv("MEDPREP_SKIP_PASSPHRASE", raising=False)
    monkeypatch.setattr(app_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(app_module, "_passphrase", None)
    monkeypatch.setattr(app_module, "_profile_data", None)

    with app_module.app.test_client() as client:
        response = client.post("/api/profiles", json={"name": "Test profile"})

    assert response.status_code == 401
    assert response.get_json() == {"error": "Vault not unlocked"}
    assert not (tmp_path / "profiles").exists()

    print("✓ Profile creation requires a real passphrase by default")


def test_api_session_clear_deletes_local_patient_data(monkeypatch):
    """Session clear removes local patient data artifacts but keeps the API vault."""
    import src.ui.app as app_module
    from src.database import Database
    from src.encryption import EncryptedVault

    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        upload_dir = data_dir / "uploads"
        reports_dir = data_dir / "reports"
        upload_dir.mkdir(parents=True)
        reports_dir.mkdir(parents=True)

        (upload_dir / "record.pdf").write_text("local copy of uploaded record")
        (reports_dir / "visit_prep.docx").write_text("generated report")

        db = Database(data_dir / "cih.db")
        db.upsert_file_state(
            file_id="file-1",
            filename="record.pdf",
            file_type="pdf",
            sha256_hash="abc123",
            file_size_bytes=42,
        )
        db.close()

        vault = EncryptedVault(data_dir, "test-passphrase")
        vault.save_profile({"demographics": {"name": "Test Patient"}})
        vault.set_api_key("gemini", "test-key")

        monkeypatch.setattr(app_module, "DATA_DIR", data_dir)
        monkeypatch.setattr(app_module, "UPLOAD_DIR", upload_dir)
        monkeypatch.setattr(app_module, "REPORTS_DIR", reports_dir)
        monkeypatch.setattr(app_module, "_passphrase", "test-passphrase")
        monkeypatch.setattr(app_module, "_profile_data", {"demographics": {"name": "Test Patient"}})
        monkeypatch.setattr(app_module, "_pipeline_thread", None)

        with app_module.app.test_client() as client:
            resp = client.post("/api/session/clear")

        assert resp.status_code == 200
        payload = json.loads(resp.data)
        assert payload["status"] == "cleared"
        assert "uploads" in payload["removed"]
        assert "reports" in payload["removed"]
        assert "cih.db" in payload["removed"]
        assert "patient_profile.enc" in payload["removed"]

        assert not (data_dir / "patient_profile.enc").exists()
        assert (data_dir / "api_vault.enc").exists()
        assert (data_dir / "cih.db").exists()
        assert list(upload_dir.iterdir()) == []
        assert list(reports_dir.iterdir()) == []
        assert app_module._profile_data is None

        conn = sqlite3.connect(str(data_dir / "cih.db"))
        try:
            remaining = conn.execute("SELECT COUNT(*) FROM processing_state").fetchone()[0]
        finally:
            conn.close()
        assert remaining == 0

    print("✓ Session clear deletes local patient data and recreates an empty database")


def test_flask_app_routes_exist():
    """Flask app has all expected routes."""
    from src.ui.app import app

    rules = [rule.rule for rule in app.url_map.iter_rules()]

    expected_routes = [
        "/",
        "/api/unlock",
        "/api/session/clear",
        "/api/session/status",
        "/api/upload",
        "/api/analyze",
        "/api/progress",
        "/api/demographics",
        "/api/medications",
        "/api/labs",
        "/api/diagnoses",
        "/api/imaging",
        "/api/genetics",
        "/api/flags",
        "/api/interactions",
        "/api/cross-disciplinary",
        "/api/community",
        "/api/literature",
        "/api/questions",
        "/api/alerts",
        "/api/timeline",
        "/api/report/download",
        "/api/report/generate",
        "/api/chat",
        "/api/keys",
        "/api/keys/status",
        "/api/pipeline/api-calls",
        "/api/profiles",
        "/api/profiles/<profile_id>/activate",
        "/api/profiles/<profile_id>",
    ]

    for route in expected_routes:
        assert route in rules, f"Missing route: {route}"

    print(f"✓ All {len(expected_routes)} expected routes present")


def test_flask_test_client():
    """Flask test client can make basic requests."""
    from src.ui.app import app

    with app.test_client() as client:
        # Session status should work without auth
        resp = client.get("/api/session/status")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "unlocked" in data
        assert "has_profile" in data
        assert "pipeline_running" in data

    print("✓ Flask test client works, session status returns correct fields")


def test_api_call_pause_control_waits_for_local_safety_boundary(monkeypatch):
    """External APIs cannot resume before local processing and redaction finish."""
    import src.ui.app as app_module

    original_api_state = app_module._api_calls_allowed.is_set()
    original_pipeline_state = app_module._pipeline_paused.is_set()
    original_progress_pass = app_module._pipeline_progress["pass"]

    class RunningThread:
        @staticmethod
        def is_alive():
            return True

    monkeypatch.setattr(app_module, "_pipeline_thread", RunningThread())

    try:
        app_module._api_calls_allowed.set()
        app_module._pipeline_paused.set()

        with app_module.app.test_client() as client:
            pause_resp = client.post(
                "/api/pipeline/api-calls",
                data=json.dumps({"paused": True}),
                content_type="application/json",
            )
            status_resp = client.get("/api/pipeline/status")

            assert pause_resp.status_code == 200
            assert json.loads(pause_resp.data)["api_calls_paused"] is True
            assert json.loads(status_resp.data)["api_calls_paused"] is True
            assert app_module._pipeline_paused.is_set() is True

            app_module._pipeline_progress["pass"] = "pass_1a"
            early_resume_resp = client.post(
                "/api/pipeline/api-calls",
                data=json.dumps({"paused": False}),
                content_type="application/json",
            )
            assert early_resume_resp.status_code == 409
            assert app_module._api_calls_allowed.is_set() is False

            app_module._pipeline_progress["pass"] = "api_waiting"
            resume_resp = client.post(
                "/api/pipeline/api-calls",
                data=json.dumps({"paused": False}),
                content_type="application/json",
            )
            assert resume_resp.status_code == 200
            assert json.loads(resume_resp.data)["api_calls_paused"] is False
    finally:
        if original_api_state:
            app_module._api_calls_allowed.set()
        else:
            app_module._api_calls_allowed.clear()
        if original_pipeline_state:
            app_module._pipeline_paused.set()
        else:
            app_module._pipeline_paused.clear()
        app_module._pipeline_progress["pass"] = original_progress_pass

    print("✓ API calls remain locked until the local safety boundary")


def test_upload_batches_accumulate_in_profile_stage(monkeypatch, tmp_path):
    """Multiple picker batches remain staged together until analysis starts."""
    import src.ui.app as app_module

    monkeypatch.setattr(app_module, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(app_module, "_passphrase", "test-passphrase")
    monkeypatch.setattr(app_module, "_active_profile_id", "profile-1")
    monkeypatch.setattr(app_module, "_pipeline_thread", None)

    with app_module.app.test_client() as client:
        first = client.post(
            "/api/upload",
            data={
                "start_new_stage": "1",
                "files": (io.BytesIO(b"first"), "first.pdf"),
            },
            content_type="multipart/form-data",
        )
        second = client.post(
            "/api/upload",
            data={
                "start_new_stage": "0",
                "files": (io.BytesIO(b"second"), "second.pdf"),
            },
            content_type="multipart/form-data",
        )
        staged = client.get("/api/upload")

    assert first.status_code == 200
    assert first.get_json()["staged_total"] == 1
    assert second.status_code == 200
    assert second.get_json()["staged_total"] == 2
    assert staged.status_code == 200
    assert [item["name"] for item in staged.get_json()["files"]] == [
        "first.pdf", "second.pdf",
    ]

    print("✓ Upload batches accumulate in one profile-scoped local stage")


def test_done_uploading_closes_stage_and_locks_external_apis(monkeypatch, tmp_path):
    """Starting a run moves the full stage and resets the external API gate."""
    import src.ui.app as app_module

    original_api_state = app_module._api_calls_allowed.is_set()
    captured = {}

    class DeferredThread:
        def __init__(self, target, args, daemon):
            captured["target"] = target
            captured["args"] = args
            captured["daemon"] = daemon
            captured["started"] = False

        def start(self):
            captured["started"] = True

        @staticmethod
        def is_alive():
            return False

    monkeypatch.setattr(app_module, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(app_module, "_passphrase", "test-passphrase")
    monkeypatch.setattr(app_module, "_active_profile_id", "profile-1")
    monkeypatch.setattr(app_module, "_pipeline_thread", None)
    monkeypatch.setattr(app_module.threading, "Thread", DeferredThread)

    try:
        app_module._api_calls_allowed.set()
        staging_dir = app_module._staging_upload_dir()
        staging_dir.mkdir(parents=True)
        (staging_dir / "12345678_first.pdf").write_bytes(b"first")
        (staging_dir / "87654321_second.pdf").write_bytes(b"second")

        with app_module.app.test_client() as client:
            response = client.post("/api/analyze")

        assert response.status_code == 200
        assert response.get_json()["file_count"] == 2
        assert captured["started"] is True
        assert captured["daemon"] is True
        assert len(captured["args"][0]) == 2
        assert all(path.parent.parent.name == "runs" for path in captured["args"][0])
        assert not staging_dir.exists()
        assert app_module._api_calls_allowed.is_set() is False
    finally:
        if original_api_state:
            app_module._api_calls_allowed.set()
        else:
            app_module._api_calls_allowed.clear()

    print("✓ Done uploading atomically closes the stage and locks external APIs")


def test_api_calls_are_paused_by_default_at_app_startup():
    """Paid external stages require an explicit resume after each app launch."""
    import subprocess

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from src.ui.app import _api_calls_allowed; "
            "raise SystemExit(0 if not _api_calls_allowed.is_set() else 1)",
        ],
        cwd=str(Path(__file__).parent.parent),
        check=False,
    )

    assert result.returncode == 0


def test_app_startup_recovers_orphaned_pipeline_runs(monkeypatch):
    """Startup recovery closes stale run metadata without removing checkpoints."""
    import src.ui.app as app_module
    from src.database import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        db = Database(data_dir / "cih.db")
        db.start_pipeline_run("orphaned-run")
        db.close()

        monkeypatch.setattr(app_module, "DATA_DIR", data_dir)
        assert app_module._recover_orphaned_pipeline_runs() == 1

        db = Database(data_dir / "cih.db")
        run = db._get_conn().execute(
            "SELECT status, completed_at FROM pipeline_runs WHERE run_id = 'orphaned-run'"
        ).fetchone()
        db.close()

        assert run["status"] == "interrupted"
        assert run["completed_at"] is not None


def test_api_returns_empty_without_profile():
    """API endpoints return empty data without a loaded profile."""
    from src.ui.app import app

    endpoints = [
        "/api/medications",
        "/api/labs",
        "/api/diagnoses",
        "/api/imaging",
        "/api/genetics",
        "/api/flags",
        "/api/interactions",
        "/api/cross-disciplinary",
        "/api/community",
        "/api/literature",
        "/api/questions",
        "/api/timeline",
    ]

    with app.test_client() as client:
        for endpoint in endpoints:
            resp = client.get(endpoint)
            assert resp.status_code == 200, f"{endpoint} should return 200"
            data = json.loads(resp.data)
            assert isinstance(data, list), f"{endpoint} should return a list"
            assert len(data) == 0, f"{endpoint} should be empty without profile"

    print(f"✓ All {len(endpoints)} data endpoints return empty lists without profile")


def test_api_upload_requires_auth():
    """Upload endpoint requires vault to be unlocked."""
    from src.ui.app import app

    with app.test_client() as client:
        resp = client.post("/api/upload")
        assert resp.status_code == 401

    print("✓ Upload requires authentication")


def test_api_analyze_requires_auth():
    """Analyze endpoint requires vault to be unlocked."""
    from src.ui.app import app

    with app.test_client() as client:
        resp = client.post("/api/analyze")
        assert resp.status_code == 401

    print("✓ Analyze requires authentication")


def test_api_chat_requires_profile():
    """Chat endpoint requires a loaded profile."""
    from src.ui.app import app

    with app.test_client() as client:
        resp = client.post(
            "/api/chat",
            data=json.dumps({"message": "test"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    print("✓ Chat requires loaded profile")


def test_api_chat_uses_local_assistant_model(monkeypatch):
    """Chat should use the local assistant model when available."""
    import src.ui.app as app_module

    original = app_module._profile_data
    try:
        app_module._profile_data = app_module._build_demo_profile()
        monkeypatch.setattr(
            app_module,
            "_call_local_assistant_model",
            lambda *args, **kwargs: "Local assistant answer",
        )

        with app_module.app.test_client() as client:
            resp = client.post(
                "/api/chat",
                data=json.dumps({"message": "What stands out most in my records?"}),
                content_type="application/json",
            )

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["response"] == "Local assistant answer"
    finally:
        app_module._profile_data = original

    print("✓ Chat uses local assistant model when available")


def test_api_chat_falls_back_to_deterministic_summary(monkeypatch):
    """Chat should fall back safely when the local assistant model is unavailable."""
    import src.ui.app as app_module

    original = app_module._profile_data
    try:
        app_module._profile_data = app_module._build_demo_profile()
        monkeypatch.setattr(
            app_module,
            "_call_local_assistant_model",
            lambda *args, **kwargs: None,
        )

        with app_module.app.test_client() as client:
            resp = client.post(
                "/api/chat",
                data=json.dumps({"message": "What medications am I taking?"}),
                content_type="application/json",
            )

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "active medications are" in data["response"]
        assert "Metformin" in data["response"]
    finally:
        app_module._profile_data = original

    print("✓ Chat falls back to deterministic summary when local model is unavailable")


def test_api_report_generate_requires_profile():
    """Report generation requires a loaded profile."""
    from src.ui.app import app

    with app.test_client() as client:
        resp = client.post("/api/report/generate")
        assert resp.status_code == 400

    print("✓ Report generation requires profile")


# ── Static Files Tests ──────────────────────────────────────

def test_static_files_exist():
    """All required static files exist."""
    static_dir = Path(__file__).parent.parent / "src" / "ui" / "static"

    assert (static_dir / "index.html").exists(), "index.html missing"
    assert (static_dir / "styles.css").exists(), "styles.css missing"
    assert (static_dir / "app.js").exists(), "app.js missing"

    print("✓ All static files exist")


def test_index_html_structure():
    """index.html contains all required views."""
    static_dir = Path(__file__).parent.parent / "src" / "ui" / "static"
    html = (static_dir / "index.html").read_text()

    required_views = [
        "view-dashboard",
        "view-timeline",
        "view-medications",
        "view-labs",
        "view-imaging",
        "view-genetics",
        "view-flags",
        "view-crossdisc",
        "view-community",
        "view-alerts",
        "view-report",
    ]

    for view_id in required_views:
        assert view_id in html, f"Missing view: {view_id}"

    # Check passphrase modal
    assert "passphrase-modal" in html
    assert "passphrase-input" in html

    # Check profile selector modal
    assert "profile-modal" in html
    assert "profile-list" in html
    assert "profile-indicator" in html
    assert "data-api-pause-button" in html
    assert "APIs Locked During Local Processing" in html
    assert "Done Uploading — Start Local Processing" in html
    assert "Add Another Batch" in html
    assert "no external APIs run while staging" in html

    # Check chat entry point
    assert "dashboard-chat" in html or "view-chat" in html

    # Check drop zone
    assert "drop-zone" in html

    # Check settings
    assert "settings-overlay" in html

    # Check nav
    assert "sidebar" in html or "nav-tabs" in html

    print(f"✓ index.html has all {len(required_views)} views + modal + drop zone + settings")


def test_app_js_structure():
    """app.js contains all required controllers."""
    static_dir = Path(__file__).parent.parent / "src" / "ui" / "static"
    js = (static_dir / "app.js").read_text()

    # Main controllers
    assert "var App = {" in js or "var App =" in js, "Missing App controller"
    assert "var Timeline = {" in js or "var Timeline =" in js, "Missing Timeline controller"

    # Key functions
    assert "escapeHtml" in js, "Missing escapeHtml security function"
    assert "severityBadge" in js, "Missing severityBadge helper"
    assert "formatDate" in js, "Missing formatDate helper"
    assert "formatProvenance" in js, "Missing formatProvenance helper"

    # App methods
    assert "unlock" in js, "Missing unlock method"
    assert "navigateTo" in js, "Missing navigateTo method"
    assert "handleDrop" in js, "Missing handleDrop method"
    assert "startAnalysis" in js, "Missing startAnalysis method"
    assert "listenProgress" in js, "Missing listenProgress method"
    assert "sendChat" in js, "Missing sendChat method"
    assert "generateReport" in js, "Missing generateReport method"
    assert "clearSession" in js, "Missing clearSession method"
    assert "showProfileSelector" in js, "Missing showProfileSelector method"
    assert "createProfile" in js, "Missing createProfile method"
    assert "activateProfile" in js, "Missing activateProfile method"
    assert "deleteProfile" in js, "Missing deleteProfile method"
    assert "toggleApiCalls" in js, "Missing API call pause controller"
    assert "api_calls_paused" in js, "Missing API call pause state handling"
    assert "restoreStagedUploads" in js, "Missing staged upload restoration"
    assert "_apiCallsReady" in js, "Missing external API readiness gate"

    print("✓ app.js has all required controllers and methods")


def test_existing_profile_keeps_document_upload_accessible():
    """Returning users must retain visible, keyboard-accessible ingestion controls."""
    static_dir = Path(__file__).parent.parent / "src" / "ui" / "static"
    html = (static_dir / "index.html").read_text()
    js = (static_dir / "app.js").read_text()

    assert 'id="sidebar-upload-btn"' in html
    assert 'id="dash-upload-btn"' in html
    assert 'aria-label="Upload medical records"' in html
    assert 'role="button" tabindex="0"' in html
    assert "showUpload: function()" in js

    load_dashboard = js.split("loadDashboard: async function()", 1)[1].split(
        "loadMedications: async function()", 1
    )[0]
    assert '$("upload-card").style.display = App._pipelineRunning ? "none" : "block";' in load_dashboard

    print("✓ Existing profiles retain clear document-upload entry points")


def test_css_has_all_components():
    """styles.css defines all required component styles."""
    static_dir = Path(__file__).parent.parent / "src" / "ui" / "static"
    css = (static_dir / "styles.css").read_text()

    required = [
        "--bg-primary",
        "--heat",
        "--severity-critical",
        ".nav",
        ".card",
        ".btn",
        ".drop-zone",
        ".progress-bar",
        ".data-table",
        ".badge",
        ".chat-container",
        ".modal",
        ".community-warning",
        ".timeline-item",
        "@media",
    ]

    for item in required:
        assert item in css, f"Missing CSS: {item}"

    print(f"✓ styles.css has all {len(required)} required components")


# ── Run All Tests ────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Phase 8 Tests — Clinical Intelligence Hub UI")
    print("=" * 60)

    # Pipeline
    test_pipeline_import()
    test_pipeline_init()
    test_pipeline_clear_session()
    test_pipeline_has_all_passes()

    # Flask App
    test_flask_app_import()
    test_flask_app_routes_exist()
    test_flask_test_client()
    test_api_returns_empty_without_profile()
    test_api_upload_requires_auth()
    test_api_analyze_requires_auth()
    test_api_chat_requires_profile()
    test_api_report_generate_requires_profile()

    # Static Files
    test_static_files_exist()
    test_index_html_structure()
    test_app_js_structure()
    test_css_has_all_components()

    print()
    print("=" * 60)
    print("All Phase 8 tests passed ✓")
    print("=" * 60)
