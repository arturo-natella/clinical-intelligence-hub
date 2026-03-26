"""
Tests for incremental, resumable profile persistence.

Validates:
1. Upload creates a profile record immediately.
2. Profiles in processing/partial states appear in the UI (list_profiles).
3. A lightweight snapshot is written before full parsing completes.
4. Restart/retry resumes from the first incomplete checkpoint.
5. Completed stages are skipped for unchanged files.
"""

import json
import tempfile
import uuid
from pathlib import Path


# ── 1. Upload creates profile immediately ─────────────────────

def test_upload_creates_profile_immediately():
    """create_profile should make the profile visible before any parsing."""
    from src.database import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        db = Database(Path(tmpdir) / "test.db")

        profile_id = str(uuid.uuid4())
        job_id = str(uuid.uuid4())

        # Simulate what upload_files() does
        db.create_profile(profile_id=profile_id, status="processing",
                          display_name="Test Upload 2026-01-01")
        db.create_source_file(
            file_id="file-001",
            profile_id=profile_id,
            filename="labs.pdf",
            sha256_hash="abc123",
            file_size_bytes=50_000,
        )
        db.create_processing_job(job_id=job_id, profile_id=profile_id)

        # Profile must exist immediately
        record = db.get_profile_record(profile_id)
        assert record is not None, "Profile record must exist right after upload"
        assert record["status"] == "processing"
        assert record["display_name"] == "Test Upload 2026-01-01"

        # Job must exist and be queued
        job = db.get_job(job_id)
        assert job is not None
        assert job["status"] == "queued"

        # Source file must be linked
        files = db.get_source_files(profile_id)
        assert len(files) == 1
        assert files[0]["filename"] == "labs.pdf"

        db.close()
    print("✓ Upload creates profile immediately")


# ── 2. Processing/partial profiles appear in list ─────────────

def test_processing_profiles_appear_in_list():
    """list_profiles must return processing, partial_ready, and ready profiles."""
    from src.database import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        db = Database(Path(tmpdir) / "test.db")

        statuses = ["processing", "partial_ready", "ready", "failed_partial", "failed"]
        ids = []
        for status in statuses:
            pid = str(uuid.uuid4())
            ids.append(pid)
            db.create_profile(profile_id=pid, status=status)

        profiles = db.list_profiles()
        returned_statuses = {p["status"] for p in profiles}

        for status in statuses:
            assert status in returned_statuses, (
                f"Profile with status '{status}' must appear in list_profiles()"
            )

        assert len(profiles) == len(statuses)

        db.close()
    print("✓ Processing/partial profiles appear in profile list")


# ── 3. Snapshot written before full parse completes ────────────

def test_snapshot_written_before_full_parse():
    """A profile snapshot must be persisted before the pipeline finishes.

    We simulate the incremental snapshot behaviour that the Pipeline class
    exercises after Pass 0 and Pass 1a.
    """
    from src.database import Database
    from src.models import PatientProfile, ProfileStatus

    with tempfile.TemporaryDirectory() as tmpdir:
        db = Database(Path(tmpdir) / "test.db")

        profile_id = str(uuid.uuid4())
        db.create_profile(profile_id=profile_id, status="processing")

        # No snapshot yet
        assert db.get_latest_snapshot(profile_id) is None

        # Simulate what _save_incremental_snapshot() does after Pass 0
        snapshot_pass0 = {
            "profile_id": profile_id,
            "status": ProfileStatus.PROCESSING.value,
            "current_stage": "ocr_complete",
            "progress_percent": 12,
            "file_count": 2,
            "medication_count": 0,
            "lab_count": 0,
            "sections": {"labs": "pending", "medications": "pending"},
            "profile_data": PatientProfile(
                profile_id=profile_id
            ).model_dump(mode="json"),
        }
        db.save_profile_snapshot(profile_id, json.dumps(snapshot_pass0))

        snap = db.get_latest_snapshot(profile_id)
        assert snap is not None, "Snapshot must exist after Pass 0"
        assert snap["status"] == "processing"
        assert snap["current_stage"] == "ocr_complete"

        # Simulate what happens after Pass 1a (labs extracted)
        from src.models import LabResult, Provenance
        profile = PatientProfile(profile_id=profile_id)
        profile.clinical_timeline.labs.append(
            LabResult(
                name="Hemoglobin A1c",
                value=7.2,
                unit="%",
                provenance=Provenance(source_file="labs.pdf"),
            )
        )
        snapshot_pass1a = {
            "profile_id": profile_id,
            "status": ProfileStatus.PARTIAL_READY.value,
            "current_stage": "entities_extracted",
            "progress_percent": 25,
            "file_count": 2,
            "medication_count": 0,
            "lab_count": 1,
            "sections": {"labs": "available", "medications": "pending"},
            "profile_data": profile.model_dump(mode="json"),
        }
        db.save_profile_snapshot(profile_id, json.dumps(snapshot_pass1a))

        # Latest snapshot must reflect Pass 1a results
        snap2 = db.get_latest_snapshot(profile_id)
        assert snap2 is not None, "Second snapshot must exist"
        assert snap2["status"] == "partial_ready", (
            f"Expected 'partial_ready', got '{snap2.get('status')}'"
        )
        assert snap2["lab_count"] == 1, (
            f"Expected 1 lab, got {snap2.get('lab_count')}"
        )
        assert snap2["current_stage"] == "entities_extracted"
        profile_data = snap2.get("profile_data", {})
        labs = profile_data.get("clinical_timeline", {}).get("labs", [])
        assert len(labs) == 1 and labs[0]["name"] == "Hemoglobin A1c", (
            f"Expected 1 lab named 'Hemoglobin A1c', got: {labs}"
        )

        db.close()
    print("✓ Snapshot written before full parse completes")


# ── 4. Resume from first incomplete checkpoint ─────────────────

def test_resume_from_first_incomplete_checkpoint():
    """Pipeline should resume from the first uncompleted stage.

    Scenario: Pass 0 (ocr_complete) completed, Pass 1a (entities_extracted)
    was NOT completed (e.g., process crashed). On retry the pipeline should
    detect that ocr_complete is done and skip it, but re-run entities_extracted.
    """
    from src.database import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        db = Database(Path(tmpdir) / "test.db")

        job_id = str(uuid.uuid4())
        file_id = "file-abc"
        parser_version = "1.0.0"

        # Simulate first run: ocr_complete finished, entities_extracted crashed
        db.save_checkpoint(
            job_id=job_id,
            file_id=file_id,
            stage="ocr_complete",
            status="completed",
            parser_version=parser_version,
        )
        # entities_extracted was NOT saved (crash before completion)

        completed = db.get_completed_stages(file_id, parser_version)
        assert "ocr_complete" in completed
        assert "entities_extracted" not in completed

        # Pipeline uses is_stage_completed() to decide whether to skip
        assert db.is_stage_completed(file_id, "ocr_complete", parser_version) is True
        assert db.is_stage_completed(file_id, "entities_extracted", parser_version) is False

        # After retry, entities_extracted completes
        db.save_checkpoint(
            job_id=job_id,
            file_id=file_id,
            stage="entities_extracted",
            status="completed",
            parser_version=parser_version,
        )
        assert db.is_stage_completed(file_id, "entities_extracted", parser_version) is True

        db.close()
    print("✓ Resume from first incomplete checkpoint")


# ── 5. Completed stages skipped for unchanged files ────────────

def test_completed_stages_skipped_for_unchanged_files():
    """When a file's hash and parser version are unchanged, completed stages
    should be detected and skippable without re-running extraction.
    """
    from src.database import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        db = Database(Path(tmpdir) / "test.db")

        job_id_run1 = str(uuid.uuid4())
        job_id_run2 = str(uuid.uuid4())
        file_id = "stable-file-xyz"
        parser_v1 = "1.0.0"
        parser_v2 = "2.0.0"

        # First run: all stages complete
        for stage in ["ocr_complete", "classified", "entities_extracted", "normalized"]:
            db.save_checkpoint(
                job_id=job_id_run1,
                file_id=file_id,
                stage=stage,
                status="completed",
                parser_version=parser_v1,
            )

        # Second run, same parser version → all stages should be seen as done
        completed_v1 = db.get_completed_stages(file_id, parser_v1)
        assert len(completed_v1) == 4, "All 4 stages must be seen as completed"

        for stage in ["ocr_complete", "classified", "entities_extracted", "normalized"]:
            assert db.is_stage_completed(file_id, stage, parser_v1) is True

        # Parser version upgrade → stages NOT seen as done (must re-extract)
        completed_v2 = db.get_completed_stages(file_id, parser_v2)
        assert len(completed_v2) == 0, (
            "Version bump must invalidate completed stages"
        )
        assert db.is_stage_completed(file_id, "entities_extracted", parser_v2) is False

        db.close()
    print("✓ Completed stages skipped for unchanged files; version bump forces re-extraction")


# ── Additional: profile status transitions ────────────────────

def test_profile_status_transitions():
    """Profile status must update correctly through the pipeline lifecycle."""
    from src.database import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        db = Database(Path(tmpdir) / "test.db")

        pid = str(uuid.uuid4())
        db.create_profile(pid, status="processing")

        assert db.get_profile_record(pid)["status"] == "processing"

        db.update_profile_status(pid, "partial_ready")
        assert db.get_profile_record(pid)["status"] == "partial_ready"

        db.update_profile_status(pid, "ready")
        assert db.get_profile_record(pid)["status"] == "ready"

        db.close()
    print("✓ Profile status transitions work correctly")


def test_job_status_and_progress():
    """Job status and progress_pct must update correctly."""
    from src.database import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        db = Database(Path(tmpdir) / "test.db")

        pid = str(uuid.uuid4())
        jid = str(uuid.uuid4())
        db.create_profile(pid)
        db.create_processing_job(jid, pid)

        job = db.get_job(jid)
        assert job["status"] == "queued"
        assert job["progress_pct"] == 0

        db.update_job_status(jid, "running", 25)
        job = db.get_job(jid)
        assert job["status"] == "running"
        assert job["progress_pct"] == 25

        db.complete_job(jid, "completed")
        job = db.get_job(jid)
        assert job["status"] == "completed"
        assert job["progress_pct"] == 100

        db.close()
    print("✓ Job status and progress tracking work correctly")


def test_clear_patient_data_removes_all_new_tables():
    """clear_patient_data must also remove profiles, snapshots, checkpoints."""
    from src.database import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        db = Database(Path(tmpdir) / "test.db")

        pid = str(uuid.uuid4())
        jid = str(uuid.uuid4())
        db.create_profile(pid, status="processing")
        db.create_source_file("f1", pid, "labs.pdf")
        db.create_processing_job(jid, pid)
        db.save_checkpoint(jid, "f1", "ocr_complete", "completed", "1.0.0")
        db.save_profile_snapshot(pid, json.dumps({"profile_id": pid}))

        # Verify data exists
        assert db.get_profile_record(pid) is not None
        assert db.get_latest_snapshot(pid) is not None

        # Clear
        db.clear_patient_data()

        # All should be gone
        assert db.get_profile_record(pid) is None
        assert db.get_latest_snapshot(pid) is None
        assert db.get_source_files(pid) == []
        assert db.get_job(jid) is None
        assert db.get_completed_stages("f1", "1.0.0") == []

        db.close()
    print("✓ clear_patient_data removes all incremental persistence tables")


if __name__ == "__main__":
    test_upload_creates_profile_immediately()
    test_processing_profiles_appear_in_list()
    test_snapshot_written_before_full_parse()
    test_resume_from_first_incomplete_checkpoint()
    test_completed_stages_skipped_for_unchanged_files()
    test_profile_status_transitions()
    test_job_status_and_progress()
    test_clear_patient_data_removes_all_new_tables()
    print("\n══════════════════════════════════════════════════════")
    print("  Incremental Profile Persistence: ALL PASSED")
    print("══════════════════════════════════════════════════════")
