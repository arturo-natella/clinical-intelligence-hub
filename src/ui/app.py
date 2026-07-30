"""
Clinical Intelligence Hub — Flask Server

Serves the Clinical Intelligence Hub SPA and provides API endpoints
for the frontend to interact with the analysis pipeline.

Features:
  - File upload via drag-and-drop
  - Server-Sent Events (SSE) for real-time progress
  - RESTful API for all Hub views
  - Session management (clear/new session)
  - Passphrase-based vault unlock
"""

import json
import logging
import os
import queue
import re
import shutil
import sys
import threading
import time
import uuid
import gc
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import Flask, jsonify, request, Response, send_from_directory

logger = logging.getLogger("CIH-App")

# ── App Configuration ─────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
REPORTS_DIR = DATA_DIR / "reports"
STATIC_DIR = Path(__file__).parent / "static"

app = Flask(__name__, static_folder=str(STATIC_DIR))
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB max upload

# Global state
_pipeline_thread: threading.Thread = None
_sse_listeners: list = []  # Per-connection queues for SSE broadcast
_sse_listeners_lock = threading.Lock()
_passphrase: str = None
_profile_data: dict = None
_active_profile_id: str = None
_environmental_sync_worker = None
_pipeline_paused: threading.Event = threading.Event()
_pipeline_paused.set()  # Not paused by default (set = running)
_api_calls_allowed: threading.Event = threading.Event()
_api_calls_allowed.set()  # Local processing always runs; external stages may be paused

# Persistent pipeline progress — survives page refresh / SSE reconnect
_pipeline_progress: dict = {
    "pass": None,
    "message": "",
    "percent": 0,
    "timestamp": 0,
    "terminal_log": [],   # Recent log lines for terminal restore
}

# ── System Health (dashboard System Status card) ──────────────
# Reads only local machine state — never patient data.

try:
    import ollama
except ImportError:  # pragma: no cover - client library absent entirely
    ollama = None

try:
    from src.extraction.text_extractor import MODEL_NAME as TEXT_MODEL_NAME
except Exception:  # pragma: no cover - keep health checks alive regardless
    TEXT_MODEL_NAME = "jwang580/medgemma_27b_q8_0"
try:
    from src.imaging.vision_analyzer import MODEL_NAME as VISION_MODEL_NAME
except Exception:  # pragma: no cover
    VISION_MODEL_NAME = os.environ.get("MEDPREP_VISION_MODEL", "medgemma:4b").strip() or "medgemma:4b"

_HEALTH_CACHE_SECONDS = 15
_DISK_WARN_GB = 50
_DISK_FAIL_GB = 10
_health_cache: dict = {"at": 0.0, "payload": None}


def _health_check(check_id, label, status, detail, hint=""):
    return {"id": check_id, "label": label, "status": status, "detail": detail, "hint": hint}


def _installed_model_names():
    """Single bounded ollama.list() call; raises when the daemon is unreachable."""
    if ollama is None:
        raise RuntimeError("ollama client library not installed")
    listing = ollama.list()
    models = getattr(listing, "models", None)
    if models is None and isinstance(listing, dict):
        models = listing.get("models")
    names = set()
    for item in models or []:
        name = getattr(item, "model", None) or getattr(item, "name", None)
        if name is None and isinstance(item, dict):
            name = item.get("model") or item.get("name")
        if name:
            names.add(str(name))
    return names


def _model_present(names, model_name):
    candidates = {model_name, f"{model_name}:latest", model_name.split(":", 1)[0]}
    return bool(names & candidates)


def _build_system_health():
    checks = []

    names = None
    try:
        names = _installed_model_names()
        checks.append(_health_check("ollama", "AI engine (Ollama)", "ok", "Running"))
    except Exception:
        hint = "Start the Ollama app, then press Refresh."
        if ollama is None:
            hint = "The Ollama software is not installed on this Mac."
        checks.append(_health_check("ollama", "AI engine (Ollama)", "fail", "Not running", hint))

    if names is None:
        unknown_hint = "Can't check until the AI engine is running."
        checks.append(_health_check(
            "medgemma_text", "Text model (MedGemma 27B)", "unknown", "Not checked", unknown_hint,
        ))
        checks.append(_health_check(
            "medgemma_vision", "Image model (MedGemma 4B)", "unknown", "Not checked", unknown_hint,
        ))
    else:
        if _model_present(names, TEXT_MODEL_NAME):
            checks.append(_health_check("medgemma_text", "Text model (MedGemma 27B)", "ok", "Installed"))
        else:
            checks.append(_health_check(
                "medgemma_text", "Text model (MedGemma 27B)", "fail", "Not installed",
                f"Records can't be analyzed without it. In Terminal run: ollama pull {TEXT_MODEL_NAME}",
            ))
        if _model_present(names, VISION_MODEL_NAME):
            checks.append(_health_check("medgemma_vision", "Image model (MedGemma 4B)", "ok", "Installed"))
        else:
            checks.append(_health_check(
                "medgemma_vision", "Image model (MedGemma 4B)", "warn", "Not installed",
                f"X-rays and scans will be skipped. In Terminal run: ollama pull {VISION_MODEL_NAME}",
            ))

    try:
        usage = shutil.disk_usage(DATA_DIR)
        free_gb = usage.free / (1024 ** 3)
        detail = f"{free_gb:,.0f} GB free"
        if free_gb < _DISK_FAIL_GB:
            checks.append(_health_check(
                "disk", "Disk space", "fail", detail,
                "Too little space to analyze safely — free up disk space first.",
            ))
        elif free_gb < _DISK_WARN_GB:
            checks.append(_health_check(
                "disk", "Disk space", "warn", detail,
                "Getting low — consider freeing space before long analyses.",
            ))
        else:
            checks.append(_health_check("disk", "Disk space", "ok", detail))
    except Exception:
        checks.append(_health_check("disk", "Disk space", "unknown", "Not checked", "Couldn't read disk space."))

    try:
        import importlib.util
        has_presidio = importlib.util.find_spec("presidio_analyzer") is not None
    except Exception:
        has_presidio = False
    if has_presidio:
        checks.append(_health_check("privacy", "Privacy shield (Presidio)", "ok", "Ready"))
    else:
        checks.append(_health_check(
            "privacy", "Privacy shield (Presidio)", "warn", "Not installed",
            "Cloud analysis stays switched off until it's installed. Local analysis still works.",
        ))

    if _passphrase:
        checks.append(_health_check("vault", "Records vault", "ok", "Unlocked"))
    else:
        checks.append(_health_check(
            "vault", "Records vault", "warn", "Locked",
            "Unlock to restore your saved profile and reports.",
        ))

    rank = {"ok": 0, "unknown": 1, "warn": 1, "fail": 2}
    overall_rank = max(rank[c["status"]] for c in checks)
    overall = {0: "ok", 1: "warn", 2: "fail"}[overall_rank]

    return {
        "checked_at": datetime.now().isoformat(),
        "overall": overall,
        "checks": checks,
    }


@app.route("/api/system-health")
def api_system_health():
    force = request.args.get("refresh") == "1"
    now = time.monotonic()
    if (
        not force
        and _health_cache["payload"] is not None
        and now - _health_cache["at"] < _HEALTH_CACHE_SECONDS
    ):
        return jsonify(_health_cache["payload"])
    payload = _build_system_health()
    _health_cache["payload"] = payload
    _health_cache["at"] = now
    return jsonify(payload)

def _broadcast_progress(event: dict):
    """Send a progress event to all active SSE listeners and update persistent state."""
    with _sse_listeners_lock:
        for listener_q in _sse_listeners:
            try:
                listener_q.put_nowait(event)
            except queue.Full:
                pass
    # Update persistent state
    _pipeline_progress["pass"] = event.get("pass")
    _pipeline_progress["message"] = event.get("message", "")
    if event.get("percent", -1) >= 0:
        _pipeline_progress["percent"] = event["percent"]
    _pipeline_progress["timestamp"] = event.get("timestamp", time.time())
    _pipeline_progress["terminal_log"].append(event)
    if len(_pipeline_progress["terminal_log"]) > 200:
        _pipeline_progress["terminal_log"] = _pipeline_progress["terminal_log"][-200:]


_DEV_BYPASS_SENTINEL = "__medprep_local_dev_bypass__"
LOCAL_ASSISTANT_MODEL = os.environ.get("MEDPREP_ASSISTANT_MODEL", "gpt-oss:20b").strip() or "gpt-oss:20b"


def _passphrase_bypass_enabled() -> bool:
    """Allow temporary local testing without the unlock modal."""
    value = os.environ.get("MEDPREP_SKIP_PASSPHRASE", "1").strip().lower()
    return value not in {"0", "false", "no"}


def _activate_dev_passphrase_bypass() -> bool:
    """Mark the session unlocked for local development runs."""
    global _passphrase

    if _passphrase is not None or not _passphrase_bypass_enabled():
        return False

    _passphrase = _DEV_BYPASS_SENTINEL
    logger.warning(
        "Passphrase gate bypassed for local development "
        "(set MEDPREP_SKIP_PASSPHRASE=0 to re-enable it)"
    )
    return True


def _pipeline_running() -> bool:
    """Return True when an analysis thread is currently active."""
    return _pipeline_thread is not None and _pipeline_thread.is_alive()


def _purge_local_patient_data() -> dict:
    """
    Remove all local patient-data artifacts while preserving reusable app config.

    Wipes:
      - uploaded source files copied into MedPrep
      - generated reports saved under data/reports
      - encrypted patient profiles (legacy + multi-profile)
      - SQLite patient-state database and WAL/SHM sidecars

    Preserves:
      - encrypted API key vault
      - downloaded model assets bundled with the app
    """
    global _profile_data, _active_profile_id

    from src.database import Database
    from src.encryption import EncryptedVault

    if _pipeline_running():
        raise RuntimeError("Analysis is still running. Wait for it to finish before deleting local data.")

    removed = []

    # Delete legacy single-file profile
    vault = EncryptedVault(DATA_DIR, _passphrase)
    if (DATA_DIR / "patient_profile.enc").exists():
        vault.clear_patient_profile()
        removed.append("patient_profile.enc")

    # Delete all multi-profile data (encrypted profiles + index)
    profiles_dir = DATA_DIR / "profiles"
    if profiles_dir.exists():
        shutil.rmtree(profiles_dir)
        removed.append("profiles")

    _active_profile_id = None

    for directory, label in (
        (UPLOAD_DIR, "uploads"),
        (REPORTS_DIR, "reports"),
    ):
        if directory.exists():
            shutil.rmtree(directory)
            removed.append(label)
        directory.mkdir(parents=True, exist_ok=True)

    db_files = [
        DATA_DIR / "cih.db",
        DATA_DIR / "cih.db-wal",
        DATA_DIR / "cih.db-shm",
    ]
    db_removed = False
    for db_path in db_files:
        if db_path.exists():
            db_path.unlink()
            db_removed = True
    if db_removed:
        removed.append("cih.db")

    environmental_dir = DATA_DIR / "environmental"
    if environmental_dir.exists():
        for subdir in ("raw", "normalized"):
            target = environmental_dir / subdir
            if target.exists():
                shutil.rmtree(target)
                removed.append(f"environmental/{subdir}")

        manifest_path = environmental_dir / "source_manifest.json"
        if manifest_path.exists():
            manifest_path.write_text(
                json.dumps({
                    "schema_version": 1,
                    "updated_at": "",
                    "sources": {},
                }, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            removed.append("environmental/source_manifest.json")

    # Recreate an empty database immediately so the app stays usable after purge.
    Database(DATA_DIR / "cih.db").close()

    _profile_data = None

    return {"status": "cleared", "removed": removed}


def _environmental_sync_ready() -> bool:
    demographics = (_profile_data or {}).get("demographics", {}) if isinstance(_profile_data, dict) else {}
    return bool(_passphrase and (demographics.get("location") or "").strip())


def _load_environmental_api_keys() -> dict:
    if not _passphrase:
        return {}

    try:
        from src.encryption import EncryptedVault

        vault = EncryptedVault(DATA_DIR, _passphrase)
        return vault.load_api_keys() or {}
    except Exception as exc:
        logger.warning(
            "Failed to load environmental API keys (error_type=%s)",
            type(exc).__name__,
        )
        return {}


def _get_environmental_profile() -> dict:
    return _profile_data or {}


def _start_environmental_sync_worker() -> None:
    global _environmental_sync_worker
    if _environmental_sync_worker is not None:
        return

    from src.analysis.environmental_sync import EnvironmentalAutoSyncWorker

    _environmental_sync_worker = EnvironmentalAutoSyncWorker(
        DATA_DIR,
        get_profile_data=_get_environmental_profile,
        get_api_keys=_load_environmental_api_keys,
        is_ready=_environmental_sync_ready,
    )
    _environmental_sync_worker.start()


# ── Static Files ──────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the main SPA."""
    return send_from_directory(str(STATIC_DIR), "index.html")


@app.route("/js/<path:filename>")
def javascript(filename):
    """Serve JavaScript files."""
    return send_from_directory(str(STATIC_DIR / "js"), filename)


@app.route("/<path:filename>")
def static_files(filename):
    """Serve any static file."""
    return send_from_directory(str(STATIC_DIR), filename)


# ── Vault / Session ───────────────────────────────────────────

@app.route("/api/unlock", methods=["POST"])
def unlock_vault():
    """Unlock the encrypted vault with a passphrase."""
    global _passphrase, _profile_data, _active_profile_id

    data = request.get_json(silent=True) or {}
    passphrase = data.get("passphrase", "")

    if _passphrase_bypass_enabled():
        _passphrase = passphrase or _DEV_BYPASS_SENTINEL
        return jsonify({
            "status": "unlocked",
            "has_profile": _profile_data is not None,
            "bypassed": True,
            "profiles": [],
        })

    if not passphrase:
        return jsonify({"error": "Passphrase is required"}), 400

    try:
        from src.encryption import EncryptedVault

        vault = EncryptedVault(DATA_DIR, passphrase)

        if not vault.verify_passphrase():
            return jsonify({"error": "Incorrect passphrase"}), 401

        _passphrase = passphrase

        # Migrate legacy single-file profile if it exists
        migrated_id = vault.migrate_legacy_profile()
        if migrated_id:
            logger.info("Migrated legacy profile to multi-profile system")

        profiles = vault.list_profiles()

        # Auto-activate if there's exactly one profile
        if len(profiles) == 1:
            _active_profile_id = profiles[0]["id"]
            vault.active_profile_id = _active_profile_id
            profile = vault.load_profile(_active_profile_id)
            if profile:
                _profile_data = profile

        return jsonify({
            "status": "unlocked",
            "has_profile": _profile_data is not None,
            "profiles": profiles,
            "active_profile_id": _active_profile_id,
        })

    except Exception as e:
        error_type = type(e).__name__
        logger.error("Vault unlock failed (error_type=%s)", error_type)
        return jsonify({"error": f"Vault unlock failed ({error_type})"}), 500


# ── Profile Management ───────────────────────────────────────

@app.route("/api/profiles")
def list_profiles():
    """List all patient profiles (metadata only, no PII)."""
    if not _passphrase:
        return jsonify({"error": "Vault not unlocked"}), 401

    from src.encryption import EncryptedVault
    vault = EncryptedVault(DATA_DIR, _passphrase)
    profiles = vault.list_profiles()
    return jsonify({
        "profiles": profiles,
        "active_profile_id": _active_profile_id,
    })


@app.route("/api/profiles", methods=["POST"])
def create_profile():
    """Create a new patient profile."""
    global _active_profile_id, _profile_data

    if not _passphrase:
        return jsonify({"error": "Vault not unlocked"}), 401

    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Profile name is required"}), 400

    from src.encryption import EncryptedVault
    vault = EncryptedVault(DATA_DIR, _passphrase)

    profile_id = vault.create_profile(name)

    # Activate the new profile
    _active_profile_id = profile_id
    vault.active_profile_id = profile_id
    _profile_data = {}

    # Save empty profile to vault
    vault.save_profile(_profile_data, profile_id)

    return jsonify({
        "status": "created",
        "profile_id": profile_id,
        "name": name,
    })


@app.route("/api/profiles/<profile_id>/activate", methods=["POST"])
def activate_profile(profile_id):
    """Switch to a different patient profile."""
    global _active_profile_id, _profile_data

    if not _passphrase:
        return jsonify({"error": "Vault not unlocked"}), 401

    if _pipeline_thread and _pipeline_thread.is_alive():
        return jsonify({"error": "Cannot switch profiles while analysis is running"}), 409

    # Save current profile before switching
    if _active_profile_id and _profile_data:
        _save_profile_to_vault()

    from src.encryption import EncryptedVault
    vault = EncryptedVault(DATA_DIR, _passphrase)

    # Verify the target profile exists
    profiles = vault.list_profiles()
    if not any(p["id"] == profile_id for p in profiles):
        return jsonify({"error": "Profile not found"}), 404

    # Load the new profile
    vault.active_profile_id = profile_id
    _active_profile_id = profile_id
    profile = vault.load_profile(profile_id)
    _profile_data = profile or {}

    return jsonify({
        "status": "activated",
        "profile_id": profile_id,
        "has_data": bool(profile),
    })


@app.route("/api/profiles/<profile_id>", methods=["DELETE"])
def delete_profile_endpoint(profile_id):
    """Delete a patient profile."""
    global _active_profile_id, _profile_data

    if not _passphrase:
        return jsonify({"error": "Vault not unlocked"}), 401

    if _pipeline_thread and _pipeline_thread.is_alive():
        return jsonify({"error": "Cannot delete profile while analysis is running"}), 409

    from src.encryption import EncryptedVault
    vault = EncryptedVault(DATA_DIR, _passphrase)
    vault.delete_profile(profile_id)

    # Clear active state if we deleted the active profile
    if _active_profile_id == profile_id:
        _active_profile_id = None
        _profile_data = None

    return jsonify({"status": "deleted"})


@app.route("/api/profiles/<profile_id>", methods=["PUT"])
def rename_profile_endpoint(profile_id):
    """Rename a patient profile."""
    if not _passphrase:
        return jsonify({"error": "Vault not unlocked"}), 401

    data = request.get_json(silent=True) or {}
    new_name = data.get("name", "").strip()
    if not new_name:
        return jsonify({"error": "Name is required"}), 400

    from src.encryption import EncryptedVault
    vault = EncryptedVault(DATA_DIR, _passphrase)
    vault.rename_profile(profile_id, new_name)

    return jsonify({"status": "renamed", "name": new_name})


@app.route("/api/vault/reset", methods=["POST"])
def reset_vault():
    """Delete encrypted vault files so the user can start fresh."""
    global _passphrase, _profile_data, _active_profile_id

    _passphrase = _DEV_BYPASS_SENTINEL if _passphrase_bypass_enabled() else None
    _profile_data = None
    _active_profile_id = None

    removed = []
    for fname in ["patient_profile.enc", "api_vault.enc"]:
        fpath = DATA_DIR / fname
        if fpath.exists():
            fpath.unlink()
            removed.append(fname)

    # Delete all multi-profile encrypted data
    profiles_dir = DATA_DIR / "profiles"
    if profiles_dir.exists():
        shutil.rmtree(profiles_dir)
        removed.append("profiles")

    logger.info("Vault reset completed (artifacts_removed=%d)", len(removed))
    return jsonify({"status": "reset", "removed": removed})


@app.route("/api/session/clear", methods=["POST"])
def clear_session():
    """Delete all local patient data copied or generated by MedPrep."""

    if not _passphrase:
        return jsonify({"error": "Vault not unlocked"}), 401

    try:
        return jsonify(_purge_local_patient_data())

    except Exception as e:
        error_type = type(e).__name__
        logger.error("Session clear failed (error_type=%s)", error_type)
        still_running = "Analysis is still running" in str(e)
        status = 409 if still_running else 500
        message = (
            "Analysis is still running"
            if still_running
            else f"Session clear failed ({error_type})"
        )
        return jsonify({"error": message}), status


@app.route("/api/session/status")
def session_status():
    """Get current session status."""
    return jsonify({
        "unlocked": _passphrase is not None,
        "has_profile": _profile_data is not None,
        "pipeline_running": _pipeline_running(),
    })


@app.route("/api/demo-data", methods=["POST"])
def load_demo_data():
    """Load comprehensive demo patient data for all tabs."""
    global _profile_data

    _profile_data = _build_demo_profile()
    return jsonify({"status": "loaded", "has_data": True})


def _build_demo_profile():
    """Build a richly detailed demo patient profile."""
    return {
        "demographics": {
            "biological_sex": "male",
            "birth_year": 1985,
            "age": 40,
            "location": "Portland, OR",
            "ethnicity": "Hispanic",
            "blood_type": "O+",
            "height_cm": 178,
            "weight_kg": 102,
            "bmi": 32.2,
        },
        "clinical_timeline": {
            "medications": [
                {"name": "Metformin", "dose": "1000mg", "route": "Oral", "frequency": "twice daily",
                 "status": "active", "start_date": "2019-04-01", "prescriber": "Dr. Elena Vasquez",
                 "reason": "Type 2 diabetes glycemic control"},
                {"name": "Lisinopril", "dose": "20mg", "route": "Oral", "frequency": "once daily",
                 "status": "active", "start_date": "2020-02-15", "prescriber": "Dr. James Chen",
                 "reason": "Hypertension and renal protection"},
                {"name": "Atorvastatin", "dose": "40mg", "route": "Oral", "frequency": "once daily at bedtime",
                 "status": "active", "start_date": "2020-02-15", "prescriber": "Dr. James Chen",
                 "reason": "Hyperlipidemia, CV risk reduction"},
                {"name": "Metoprolol Succinate", "dose": "50mg", "route": "Oral", "frequency": "once daily",
                 "status": "active", "start_date": "2021-03-20", "prescriber": "Dr. James Chen",
                 "reason": "Heart rate control, hypertension"},
                {"name": "Insulin Glargine", "dose": "24 units", "route": "Subcutaneous injection", "frequency": "once daily at bedtime",
                 "status": "active", "start_date": "2023-06-01", "prescriber": "Dr. Elena Vasquez",
                 "reason": "Basal insulin for uncontrolled T2DM"},
                {"name": "Aspirin", "dose": "81mg", "route": "Oral", "frequency": "once daily",
                 "status": "active", "start_date": "2020-02-15", "prescriber": "Dr. James Chen",
                 "reason": "Cardiovascular prophylaxis"},
                {"name": "Omeprazole", "dose": "20mg", "route": "Oral", "frequency": "once daily before breakfast",
                 "status": "active", "start_date": "2021-08-20", "prescriber": "Dr. Sarah Kim",
                 "reason": "GERD, aspirin gastroprotection"},
                {"name": "Gabapentin", "dose": "300mg", "route": "Oral", "frequency": "three times daily",
                 "status": "active", "start_date": "2024-01-15", "prescriber": "Dr. Michael Torres",
                 "reason": "Diabetic peripheral neuropathy pain"},
                {"name": "Vitamin D3", "dose": "2000 IU", "route": "Oral", "frequency": "once daily",
                 "status": "active", "start_date": "2024-03-01", "prescriber": "Dr. Elena Vasquez",
                 "reason": "Vitamin D deficiency"},
                {"name": "Glipizide", "dose": "5mg", "route": "Oral", "frequency": "once daily",
                 "status": "discontinued", "start_date": "2019-04-01", "end_date": "2023-05-15",
                 "prescriber": "Dr. Elena Vasquez", "reason": "Replaced by insulin glargine"},
            ],
            "diagnoses": [
                {"name": "Type 2 Diabetes Mellitus", "severity": "high", "date": "2019-03-15",
                 "date_diagnosed": "2019-03-15", "status": "active",
                 "icd10": "E11.65", "provider": "Dr. Elena Vasquez"},
                {"name": "Essential Hypertension", "severity": "moderate", "date": "2020-01-10",
                 "date_diagnosed": "2020-01-10", "status": "active",
                 "icd10": "I10", "provider": "Dr. James Chen"},
                {"name": "Mixed Hyperlipidemia", "severity": "moderate", "date": "2020-01-10",
                 "date_diagnosed": "2020-01-10", "status": "active",
                 "icd10": "E78.2", "provider": "Dr. James Chen"},
                {"name": "Non-proliferative Diabetic Retinopathy", "severity": "high", "date": "2024-06-20",
                 "date_diagnosed": "2024-06-20", "status": "active",
                 "icd10": "E11.319", "provider": "Dr. Lisa Park"},
                {"name": "Diabetic Peripheral Neuropathy", "severity": "moderate", "date": "2023-11-05",
                 "date_diagnosed": "2023-11-05", "status": "active",
                 "icd10": "E11.42", "provider": "Dr. Michael Torres"},
                {"name": "GERD", "severity": "low", "date": "2021-08-12",
                 "date_diagnosed": "2021-08-12", "status": "active",
                 "icd10": "K21.0", "provider": "Dr. Sarah Kim"},
                {"name": "Obesity, Class I", "severity": "moderate", "date": "2019-03-15",
                 "date_diagnosed": "2019-03-15", "status": "active",
                 "icd10": "E66.01", "provider": "Dr. Elena Vasquez"},
                {"name": "Vitamin D Deficiency", "severity": "low", "date": "2024-03-01",
                 "date_diagnosed": "2024-03-01", "status": "active",
                 "icd10": "E55.9", "provider": "Dr. Elena Vasquez"},
            ],
            "symptoms": [
                {"symptom_id": "sym-tingling-feet", "symptom_name": "Tingling in feet",
                 "date_created": "2025-08-05",
                 "episodes": [
                     {"episode_id": "ep-tf-1", "episode_date": "2025-12-01", "time_of_day": "21:30", "intensity": "high",
                      "description": "Burning tingling both feet, worse at night", "triggers": "Standing all day"},
                     {"episode_id": "ep-tf-2", "episode_date": "2025-11-15", "time_of_day": "22:00", "intensity": "high",
                      "description": "Pins and needles extending to ankles", "triggers": "Evening after walk"},
                     {"episode_id": "ep-tf-3", "episode_date": "2025-10-20", "time_of_day": "20:45", "intensity": "mid",
                      "description": "Mild tingling in toes bilaterally", "triggers": "After sitting long period"},
                     {"episode_id": "ep-tf-4", "episode_date": "2025-09-10", "time_of_day": "23:00", "intensity": "mid",
                      "description": "Numbness and tingling, had to walk it off", "triggers": "Bedtime"},
                     {"episode_id": "ep-tf-5", "episode_date": "2025-08-05", "time_of_day": "19:30", "intensity": "low",
                      "description": "First noticed occasional tingling", "triggers": "None identified"},
                 ],
                 "counter_definitions": [
                     {"counter_id": "cnt-tf-1", "doctor_claim": "Gabapentin should control neuropathy pain",
                      "measure_type": "scale", "measure_label": "Pain level (1-10)",
                      "date_added": "2024-01-15", "date_archived": None, "archived": False},
                 ]},
                {"symptom_id": "sym-fatigue", "symptom_name": "Fatigue",
                 "date_created": "2025-09-20",
                 "episodes": [
                     {"episode_id": "ep-fat-1", "episode_date": "2025-12-10", "time_of_day": "14:00", "intensity": "high",
                      "description": "Extreme fatigue, could barely function after lunch", "triggers": "High-carb meal"},
                     {"episode_id": "ep-fat-2", "episode_date": "2025-11-25", "time_of_day": "10:30", "intensity": "mid",
                      "description": "Dragging all morning, needed nap by 11am", "triggers": "Poor sleep night before"},
                     {"episode_id": "ep-fat-3", "episode_date": "2025-10-30", "time_of_day": "15:00", "intensity": "mid",
                      "description": "Afternoon crash, hard to concentrate at work", "triggers": "Skipped lunch"},
                     {"episode_id": "ep-fat-4", "episode_date": "2025-09-20", "time_of_day": "09:00", "intensity": "low",
                      "description": "Woke up tired despite 8 hours sleep", "triggers": "None identified"},
                 ],
                 "counter_definitions": [
                     {"counter_id": "cnt-fat-1", "doctor_claim": "Blood sugar control will reduce fatigue",
                      "measure_type": "scale", "measure_label": "Energy level (1-10)",
                      "date_added": "2025-10-01", "date_archived": None, "archived": False},
                 ]},
                {"symptom_id": "sym-blurred-vision", "symptom_name": "Blurred vision",
                 "date_created": "2025-10-08",
                 "episodes": [
                     {"episode_id": "ep-bv-1", "episode_date": "2025-12-05", "time_of_day": "08:00", "intensity": "high",
                      "description": "Blurry for 20 min after waking, slow to clear", "triggers": "Morning, high glucose reading"},
                     {"episode_id": "ep-bv-2", "episode_date": "2025-11-20", "time_of_day": "16:30", "intensity": "mid",
                      "description": "Intermittent blur while reading", "triggers": "Screen time"},
                     {"episode_id": "ep-bv-3", "episode_date": "2025-10-08", "time_of_day": "09:15", "intensity": "mid",
                      "description": "Difficulty focusing on distant objects", "triggers": "After insulin adjustment"},
                 ],
                 "counter_definitions": []},
                {"symptom_id": "sym-frequent-urination", "symptom_name": "Frequent urination",
                 "date_created": "2025-08-20",
                 "episodes": [
                     {"episode_id": "ep-fu-1", "episode_date": "2025-12-08", "time_of_day": "02:00", "intensity": "high",
                      "description": "Up 4 times overnight", "triggers": "High glucose day (220+)"},
                     {"episode_id": "ep-fu-2", "episode_date": "2025-11-18", "time_of_day": "03:30", "intensity": "mid",
                      "description": "Up 3 times, disrupted sleep", "triggers": "Late dinner"},
                     {"episode_id": "ep-fu-3", "episode_date": "2025-10-25", "time_of_day": "01:00", "intensity": "mid",
                      "description": "Nocturia x3", "triggers": "Elevated evening glucose"},
                     {"episode_id": "ep-fu-4", "episode_date": "2025-09-15", "time_of_day": "04:00", "intensity": "low",
                      "description": "Woke twice overnight", "triggers": "Extra water intake"},
                     {"episode_id": "ep-fu-5", "episode_date": "2025-08-20", "time_of_day": "02:30", "intensity": "mid",
                      "description": "Nocturia started becoming regular pattern", "triggers": "Glucose poorly controlled"},
                 ],
                 "counter_definitions": [
                     {"counter_id": "cnt-fu-1", "doctor_claim": "SGLT2 inhibitor may increase urination initially",
                      "measure_type": "scale", "measure_label": "Nighttime wakeups",
                      "date_added": "2025-09-01", "date_archived": "2025-11-01", "archived": True},
                 ]},
                {"symptom_id": "sym-headache", "symptom_name": "Headache",
                 "date_created": "2025-11-05",
                 "episodes": [
                     {"episode_id": "ep-ha-1", "episode_date": "2025-12-12", "time_of_day": "16:00", "intensity": "mid",
                      "description": "Dull pressure headache, frontal area", "triggers": "Blood pressure spike"},
                     {"episode_id": "ep-ha-2", "episode_date": "2025-11-05", "time_of_day": "10:00", "intensity": "low",
                      "description": "Mild tension headache", "triggers": "Stress at work"},
                 ],
                 "counter_definitions": []},
                {"symptom_id": "sym-heartburn", "symptom_name": "Heartburn",
                 "date_created": "2025-11-10",
                 "episodes": [
                     {"episode_id": "ep-hb-1", "episode_date": "2025-12-01", "time_of_day": "22:00", "intensity": "mid",
                      "description": "Burning after dinner, despite omeprazole", "triggers": "Spicy food, late meal"},
                     {"episode_id": "ep-hb-2", "episode_date": "2025-11-10", "time_of_day": "21:30", "intensity": "low",
                      "description": "Mild acid reflux", "triggers": "Large meal"},
                 ],
                 "counter_definitions": []},
                {"symptom_id": "sym-numbness-hands", "symptom_name": "Numbness in hands",
                 "date_created": "2025-11-12",
                 "episodes": [
                     {"episode_id": "ep-nh-1", "episode_date": "2025-12-03", "time_of_day": "07:00", "intensity": "mid",
                      "description": "Woke with numb fingers, took 10 min to resolve", "triggers": "Sleeping position"},
                     {"episode_id": "ep-nh-2", "episode_date": "2025-11-12", "time_of_day": "06:45", "intensity": "low",
                      "description": "Tingling in ring/pinky fingers on waking", "triggers": "Unknown"},
                 ],
                 "counter_definitions": []},
                {"symptom_id": "sym-excessive-thirst", "symptom_name": "Excessive thirst",
                 "date_created": "2025-10-18",
                 "episodes": [
                     {"episode_id": "ep-et-1", "episode_date": "2025-12-09", "time_of_day": "14:30", "intensity": "mid",
                      "description": "Drank 4L water by afternoon, still thirsty", "triggers": "High glucose day"},
                     {"episode_id": "ep-et-2", "episode_date": "2025-11-22", "time_of_day": "11:00", "intensity": "mid",
                      "description": "Constant dry mouth, excessive water intake", "triggers": "Missed metformin dose"},
                     {"episode_id": "ep-et-3", "episode_date": "2025-10-18", "time_of_day": "15:00", "intensity": "low",
                      "description": "Noticeably thirstier than normal", "triggers": "Warm day, but felt excessive"},
                 ],
                 "counter_definitions": []},
                {"symptom_id": "sym-dizziness", "symptom_name": "Dizziness on standing",
                 "date_created": "2025-12-11", "archived": True,
                 "episodes": [
                     {"episode_id": "ep-dz-1", "episode_date": "2025-12-11", "time_of_day": "08:00", "intensity": "mid",
                      "description": "Lightheaded when standing from bed, had to grab wall", "triggers": "Morning, possible orthostatic from metoprolol"},
                 ],
                 "counter_definitions": []},
                {"symptom_id": "sym-wound-healing", "symptom_name": "Slow wound healing",
                 "date_created": "2025-11-28",
                 "episodes": [
                     {"episode_id": "ep-wh-1", "episode_date": "2025-11-28", "time_of_day": "12:00", "intensity": "low",
                      "description": "Small cut on finger took 2 weeks to fully heal", "triggers": "Paper cut from Nov 14"},
                 ],
                 "counter_definitions": []},
            ],
            "labs": [
                # HbA1c — 5 data points showing improvement trend
                {"test_name": "HbA1c", "value": "8.2", "unit": "%", "date": "2025-12-01", "reference_low": 4.0, "reference_high": 5.6, "flag": "H"},
                {"test_name": "HbA1c", "value": "7.8", "unit": "%", "date": "2025-09-01", "reference_low": 4.0, "reference_high": 5.6, "flag": "H"},
                {"test_name": "HbA1c", "value": "8.5", "unit": "%", "date": "2025-06-01", "reference_low": 4.0, "reference_high": 5.6, "flag": "H"},
                {"test_name": "HbA1c", "value": "9.1", "unit": "%", "date": "2025-03-01", "reference_low": 4.0, "reference_high": 5.6, "flag": "H"},
                {"test_name": "HbA1c", "value": "9.4", "unit": "%", "date": "2024-12-01", "reference_low": 4.0, "reference_high": 5.6, "flag": "H"},
                # Fasting Glucose
                {"test_name": "Fasting Glucose", "value": "156", "unit": "mg/dL", "date": "2025-12-01", "reference_low": 70, "reference_high": 100, "flag": "H"},
                {"test_name": "Fasting Glucose", "value": "142", "unit": "mg/dL", "date": "2025-09-01", "reference_low": 70, "reference_high": 100, "flag": "H"},
                {"test_name": "Fasting Glucose", "value": "168", "unit": "mg/dL", "date": "2025-06-01", "reference_low": 70, "reference_high": 100, "flag": "H"},
                {"test_name": "Fasting Glucose", "value": "185", "unit": "mg/dL", "date": "2025-03-01", "reference_low": 70, "reference_high": 100, "flag": "H"},
                # Lipid Panel
                {"test_name": "LDL Cholesterol", "value": "118", "unit": "mg/dL", "date": "2025-12-01", "reference_low": 0, "reference_high": 100, "flag": "H"},
                {"test_name": "LDL Cholesterol", "value": "132", "unit": "mg/dL", "date": "2025-06-01", "reference_low": 0, "reference_high": 100, "flag": "H"},
                {"test_name": "LDL Cholesterol", "value": "145", "unit": "mg/dL", "date": "2025-01-01", "reference_low": 0, "reference_high": 100, "flag": "H"},
                {"test_name": "LDL Cholesterol", "value": "158", "unit": "mg/dL", "date": "2024-06-01", "reference_low": 0, "reference_high": 100, "flag": "H"},
                {"test_name": "HDL Cholesterol", "value": "42", "unit": "mg/dL", "date": "2025-12-01", "reference_low": 40, "reference_high": 60},
                {"test_name": "HDL Cholesterol", "value": "38", "unit": "mg/dL", "date": "2025-06-01", "reference_low": 40, "reference_high": 60, "flag": "L"},
                {"test_name": "HDL Cholesterol", "value": "36", "unit": "mg/dL", "date": "2025-01-01", "reference_low": 40, "reference_high": 60, "flag": "L"},
                {"test_name": "Total Cholesterol", "value": "214", "unit": "mg/dL", "date": "2025-12-01", "reference_low": 0, "reference_high": 200, "flag": "H"},
                {"test_name": "Triglycerides", "value": "195", "unit": "mg/dL", "date": "2025-12-01", "reference_low": 0, "reference_high": 150, "flag": "H"},
                {"test_name": "Triglycerides", "value": "210", "unit": "mg/dL", "date": "2025-06-01", "reference_low": 0, "reference_high": 150, "flag": "H"},
                {"test_name": "Triglycerides", "value": "228", "unit": "mg/dL", "date": "2025-01-01", "reference_low": 0, "reference_high": 150, "flag": "H"},
                # Renal
                {"test_name": "Creatinine", "value": "1.1", "unit": "mg/dL", "date": "2025-12-01", "reference_low": 0.7, "reference_high": 1.3},
                {"test_name": "Creatinine", "value": "1.0", "unit": "mg/dL", "date": "2025-06-01", "reference_low": 0.7, "reference_high": 1.3},
                {"test_name": "Creatinine", "value": "0.9", "unit": "mg/dL", "date": "2025-01-01", "reference_low": 0.7, "reference_high": 1.3},
                {"test_name": "BUN", "value": "22", "unit": "mg/dL", "date": "2025-12-01", "reference_low": 7, "reference_high": 20, "flag": "H"},
                {"test_name": "eGFR", "value": "78", "unit": "mL/min", "date": "2025-12-01", "reference_low": 90, "reference_high": 120, "flag": "L"},
                {"test_name": "eGFR", "value": "82", "unit": "mL/min", "date": "2025-06-01", "reference_low": 90, "reference_high": 120, "flag": "L"},
                {"test_name": "eGFR", "value": "88", "unit": "mL/min", "date": "2025-01-01", "reference_low": 90, "reference_high": 120, "flag": "L"},
                {"test_name": "eGFR", "value": "92", "unit": "mL/min", "date": "2024-06-01", "reference_low": 90, "reference_high": 120},
                # Thyroid
                {"test_name": "TSH", "value": "2.8", "unit": "mIU/L", "date": "2025-12-01", "reference_low": 0.4, "reference_high": 4.0},
                # Liver
                {"test_name": "ALT", "value": "32", "unit": "U/L", "date": "2025-12-01", "reference_low": 7, "reference_high": 56},
                {"test_name": "AST", "value": "28", "unit": "U/L", "date": "2025-12-01", "reference_low": 10, "reference_high": 40},
                # Vitals
                {"test_name": "Blood Pressure (Systolic)", "value": "138", "unit": "mmHg", "date": "2025-12-01", "reference_low": 90, "reference_high": 120, "flag": "H"},
                {"test_name": "Blood Pressure (Systolic)", "value": "142", "unit": "mmHg", "date": "2025-09-01", "reference_low": 90, "reference_high": 120, "flag": "H"},
                {"test_name": "Blood Pressure (Systolic)", "value": "148", "unit": "mmHg", "date": "2025-06-01", "reference_low": 90, "reference_high": 120, "flag": "H"},
                {"test_name": "Blood Pressure (Systolic)", "value": "155", "unit": "mmHg", "date": "2025-03-01", "reference_low": 90, "reference_high": 120, "flag": "H"},
                # CBC
                {"test_name": "WBC", "value": "7.2", "unit": "K/uL", "date": "2025-12-01", "reference_low": 4.0, "reference_high": 11.0},
                {"test_name": "Hemoglobin", "value": "13.8", "unit": "g/dL", "date": "2025-12-01", "reference_low": 13.5, "reference_high": 17.5},
                {"test_name": "Platelets", "value": "245", "unit": "K/uL", "date": "2025-12-01", "reference_low": 150, "reference_high": 400},
                # Other
                {"test_name": "Vitamin D", "value": "28", "unit": "ng/mL", "date": "2025-12-01", "reference_low": 30, "reference_high": 100, "flag": "L"},
                {"test_name": "Vitamin D", "value": "18", "unit": "ng/mL", "date": "2024-03-01", "reference_low": 30, "reference_high": 100, "flag": "L"},
                {"test_name": "Vitamin D", "value": "24", "unit": "ng/mL", "date": "2025-06-01", "reference_low": 30, "reference_high": 100, "flag": "L"},
                {"test_name": "CRP (hs)", "value": "3.8", "unit": "mg/L", "date": "2025-12-01", "reference_low": 0, "reference_high": 3.0, "flag": "H"},
            ],
            "imaging": [
                {"modality": "Fundoscopy", "body_region": "Eyes", "study_date": "2024-06-20",
                 "description": "Bilateral non-proliferative diabetic retinopathy with scattered microaneurysms",
                 "findings": [{"description": "Dot-blot hemorrhages and hard exudates in both eyes. No neovascularization."}],
                 "provider": "Dr. Lisa Park"},
                {"modality": "Chest X-Ray", "body_region": "Chest", "study_date": "2025-01-15",
                 "description": "PA and lateral chest radiograph",
                 "findings": [{"description": "No acute cardiopulmonary disease. Heart size normal. No pleural effusion."}],
                 "provider": "Portland Radiology Associates"},
                {"modality": "Echocardiogram", "body_region": "Heart", "study_date": "2024-09-10",
                 "description": "Transthoracic echocardiogram",
                 "findings": [{"description": "EF 55%. Mild concentric LVH. No valvular abnormalities. Grade I diastolic dysfunction."}],
                 "provider": "Dr. James Chen"},
                {"modality": "Nerve Conduction Study", "body_region": "Lower Extremities", "study_date": "2023-11-05",
                 "description": "Bilateral lower extremity nerve conduction study and EMG",
                 "findings": [{"description": "Reduced sensory nerve conduction velocities bilaterally consistent with distal symmetric polyneuropathy."}],
                 "provider": "Dr. Michael Torres"},
                {"modality": "Carotid Ultrasound", "body_region": "Neck", "study_date": "2025-03-20",
                 "description": "Bilateral carotid duplex ultrasound",
                 "findings": [{"description": "Mild bilateral intimal thickening. No hemodynamically significant stenosis. IMT 0.9mm."}],
                 "provider": "Portland Vascular Lab"},
                {"modality": "Abdominal Ultrasound", "body_region": "Abdomen", "study_date": "2025-06-15",
                 "description": "Right upper quadrant ultrasound",
                 "findings": [{"description": "Mild hepatic steatosis (fatty liver). No gallstones. Kidneys normal size bilateral."}],
                 "provider": "Portland Radiology Associates"},
            ],
            "genetics": [
                {"gene": "SLC22A1", "variant": "rs622342 A/C", "significance": "Pharmacogenomic",
                 "detail": "Reduced organic cation transporter 1 activity. May decrease metformin hepatic uptake and efficacy.",
                 "category": "Drug metabolism"},
                {"gene": "SLCO1B1", "variant": "rs4149056 T/C", "significance": "Pharmacogenomic",
                 "detail": "Intermediate function OATP1B1 transporter. Increased statin myopathy risk — consider lower atorvastatin dose.",
                 "category": "Drug metabolism"},
                {"gene": "TCF7L2", "variant": "rs7903146 C/T", "significance": "Disease risk",
                 "detail": "Heterozygous risk variant associated with impaired beta-cell function and 1.4x T2DM risk.",
                 "category": "Diabetes susceptibility"},
                {"gene": "APOE", "variant": "e3/e4", "significance": "Disease risk",
                 "detail": "APOE e4 carrier. Elevated cardiovascular risk and altered lipid metabolism.",
                 "category": "Cardiovascular"},
                {"gene": "ACE", "variant": "rs4646994 I/D", "significance": "Pharmacogenomic",
                 "detail": "DD genotype associated with higher ACE activity. May need higher dose of ACE inhibitor.",
                 "category": "Drug response"},
                {"gene": "MTHFR", "variant": "rs1801133 C/T", "significance": "Nutritional",
                 "detail": "Heterozygous C677T. Mildly reduced folate metabolism. Consider methylfolate supplementation.",
                 "category": "Nutrient metabolism"},
            ],
            "procedures": [
                {"name": "Annual Physical Examination", "procedure_date": "2025-12-01",
                 "provider": "Dr. Elena Vasquez", "notes": "Comprehensive metabolic review"},
                {"name": "Dilated Eye Exam", "procedure_date": "2024-06-20",
                 "provider": "Dr. Lisa Park", "notes": "NPDR identified bilaterally"},
                {"name": "Nerve Conduction Study", "procedure_date": "2023-11-05",
                 "provider": "Dr. Michael Torres", "notes": "Confirmed distal symmetric polyneuropathy"},
                {"name": "Cardiac Stress Test", "procedure_date": "2024-09-08",
                 "provider": "Dr. James Chen", "notes": "Exercise stress — no ischemic changes at 9.2 METs"},
            ],
        },
        "analysis": {
            "flags": [
                {"title": "HbA1c significantly above target", "severity": "critical", "category": "Lab Finding",
                 "detail": "HbA1c 8.2% is well above the 7.0% ADA target (5.6% normal). Despite trending down from 9.4%, glucose control remains inadequate. Risk: accelerated microvascular damage.",
                 "evidence": [{"source": "Lab result", "date": "2025-12-01", "value": "HbA1c 8.2%"}]},
                {"title": "Declining kidney function (eGFR trend)", "severity": "high", "category": "Trend Analysis",
                 "detail": "eGFR dropped from 92 to 78 mL/min over 18 months (15% decline). Stage 2 CKD territory. Combination of diabetes and hypertension accelerates nephron loss.",
                 "question_for_doctor": "My kidney filtration number has been declining for 18 months — should we adjust any of my medications or add kidney-protective treatment?",
                 "evidence": [{"source": "Lab trend", "date": "2025-12-01", "value": "eGFR 78 (was 92 in Jun 2024)"}]},
                {"title": "LDL above diabetic target", "severity": "high", "category": "Lab Finding",
                 "detail": "LDL 118 mg/dL exceeds the <70 mg/dL target for high-risk diabetic patients (AHA/ACC guidelines). Despite statin therapy, not at goal.",
                 "question_for_doctor": "My LDL cholesterol is still above target on my current statin — should we discuss a dose change or a different medication?",
                 "evidence": [{"source": "Lab result", "date": "2025-12-01", "value": "LDL 118 mg/dL"}]},
                {"title": "Elevated triglycerides", "severity": "moderate", "category": "Lab Finding",
                 "detail": "Triglycerides 195 mg/dL above 150 mg/dL reference range. Improving from 228 but still elevated. Part of metabolic syndrome picture.",
                 "evidence": [{"source": "Lab result", "date": "2025-12-01", "value": "TG 195 mg/dL"}]},
                {"title": "Blood pressure above diabetic target", "severity": "moderate", "category": "Vital Sign",
                 "detail": "Systolic BP 138 mmHg exceeds the 130/80 mmHg target for diabetic patients. Improving trend (was 155 in March) but not at goal.",
                 "evidence": [{"source": "Vital signs", "date": "2025-12-01", "value": "SBP 138 mmHg"}]},
                {"title": "Peripheral neuropathy progression", "severity": "moderate", "category": "Symptom Pattern",
                 "detail": "Tingling in feet occurring monthly. New numbness in hands suggests proximal spread of diabetic neuropathy.",
                 "evidence": [{"source": "Symptom log", "date": "2025-12-01", "value": "5 episodes in 4 months"}]},
                {"title": "Elevated hs-CRP — inflammatory marker", "severity": "moderate", "category": "Lab Finding",
                 "detail": "hs-CRP 3.8 mg/L (reference <3.0) indicates elevated systemic inflammation. Associated with increased cardiovascular event risk.",
                 "evidence": [{"source": "Lab result", "date": "2025-12-01", "value": "hs-CRP 3.8 mg/L"}]},
                {"title": "HDL borderline low", "severity": "low", "category": "Lab Finding",
                 "detail": "HDL 42 mg/dL, just above 40 mg/dL minimum. Target >50 for cardiovascular protection. Improving from 36.",
                 "evidence": [{"source": "Lab result", "date": "2025-12-01", "value": "HDL 42 mg/dL"}]},
                {"title": "Mild hepatic steatosis on imaging", "severity": "low", "category": "Imaging Finding",
                 "detail": "Fatty liver identified on abdominal ultrasound. Common in metabolic syndrome. Monitor ALT/AST trends.",
                 "evidence": [{"source": "Imaging", "date": "2025-06-15", "value": "Abdominal US: mild steatosis"}]},
                {"title": "Urine ACR not tested", "severity": "moderate", "category": "Monitoring Gap",
                 "missing_test": "Urine Albumin-to-Creatinine Ratio",
                 "detail": "Annual uACR recommended for all diabetic patients per ADA guidelines. Critical given declining eGFR."},
                {"title": "Annual dilated eye exam overdue", "severity": "moderate", "category": "Monitoring Gap",
                 "missing_test": "Annual Dilated Eye Exam",
                 "question_for_doctor": "I'm about 6 months overdue for my dilated eye exam — can we schedule one soon?",
                 "detail": "Last eye exam was Jun 2024 (18 months ago). With known NPDR, annual screening is critical."},
                {"title": "Comprehensive foot exam needed", "severity": "low", "category": "Monitoring Gap",
                 "missing_test": "Comprehensive Foot Exam",
                 "detail": "Annual monofilament and vibration testing recommended given peripheral neuropathy diagnosis."},
            ],
            "drug_gene_interactions": [
                {"drug": "Metformin", "gene": "SLC22A1", "impact": "moderate", "severity": "moderate",
                 "detail": "SLC22A1 rs622342 A/C variant reduces organic cation transporter 1 activity. Metformin hepatic uptake may be 20-30% lower. Consider monitoring response and dose optimization."},
                {"drug": "Atorvastatin", "gene": "SLCO1B1", "impact": "high", "severity": "high",
                 "detail": "SLCO1B1 rs4149056 T/C increases systemic statin exposure. 1.7x higher myopathy risk. CPIC recommends considering lower dose or alternative statin (e.g., rosuvastatin, pravastatin)."},
            ],
            "drug_interactions": [
                {"drug_a": "Metformin", "drug_b": "Insulin Glargine", "severity": "low",
                 "detail": "Additive hypoglycemic effect. Combined use is standard for T2DM but increases hypoglycemia risk. Ensure patient monitors blood glucose."},
                {"drug_a": "Lisinopril", "drug_b": "Aspirin", "severity": "low",
                 "detail": "NSAIDs/aspirin may reduce antihypertensive effect of ACE inhibitors. Low-dose aspirin 81mg has minimal impact."},
                {"drug_a": "Metoprolol", "drug_b": "Insulin Glargine", "severity": "moderate",
                 "detail": "Beta-blockers may mask hypoglycemia symptoms (tachycardia, tremor). Patient should rely on other cues like sweating, hunger."},
                {"drug_a": "Gabapentin", "drug_b": "Metformin", "severity": "low",
                 "detail": "Both renally cleared. With declining eGFR, monitor for gabapentin accumulation. Dose adjustment may be needed if eGFR drops below 60."},
            ],
            "cross_disciplinary": [
                {"title": "Diabetes-Cardiovascular-Renal axis", "severity": "high",
                 "connection_type": "cloud_analysis",
                 "specialties": ["Endocrinology", "Cardiology", "Nephrology"],
                 "description": "Here\u2019s something we found. The good news is we spotted it early. What\u2019s happening: your diabetes, heart, and kidneys are all connected. When blood sugar stays high, it puts extra stress on your heart and kidneys. Your heart is already working harder (that\u2019s the LVH finding), and your kidney function has been slowly dropping. These three things feed into each other \u2014 but there are medications that can help all three at once.",
                 "patient_data_points": [
                     "HbA1c 8.2% \u2014 blood sugar above target",
                     "Kidney function (eGFR) dropped from 92 to 78 over 18 months",
                     "Heart thickening (LVH) found on echocardiogram",
                     "Inflammation marker (hs-CRP) elevated at 3.8",
                     "Blood pressure needs two medications to control",
                 ],
                 "question_for_doctor": "My records show my diabetes, kidneys, and heart are all being affected together. Are there treatment approaches that could help protect all three at the same time?",
                 "evidence_source": "ADA Standards of Care 2025, ACC/AHA Heart Failure Guidelines, KDIGO CKD Guidelines",
                 "diagnostic_source": "ADA Standards of Medical Care in Diabetes (Diabetes Care 2025); ACC/AHA Guideline for Management of Heart Failure (Circulation 2022); KDIGO Clinical Practice Guideline for CKD (Kidney Int 2024)"},
                {"title": "Metabolic syndrome cluster", "severity": "moderate",
                 "connection_type": "cloud_analysis",
                 "specialties": ["Endocrinology", "Cardiology", "Hepatology"],
                 "description": "Here\u2019s something we found. Your body is showing a cluster of related issues \u2014 weight, blood sugar, blood pressure, cholesterol, and liver changes. When these happen together, doctors call it metabolic syndrome. Each one alone is manageable, but together they multiply the risk. The good news: treating the root causes (like weight and insulin resistance) can improve several of these at once.",
                 "patient_data_points": [
                     "BMI 32.2 \u2014 in the obese range",
                     "HbA1c 8.2% \u2014 blood sugar not well controlled",
                     "High blood pressure needing two medications",
                     "Triglycerides high, good cholesterol (HDL) low",
                     "Fatty liver found on imaging",
                 ],
                 "question_for_doctor": "Several of my numbers point to metabolic syndrome. Could a GLP-1 medication like semaglutide help tackle the weight, blood sugar, and heart risk together instead of adding more separate medications?",
                 "evidence_source": "NCEP ATP III Metabolic Syndrome Criteria, ADA/EASD Consensus Report, AASLD NAFLD Practice Guidelines",
                 "diagnostic_source": "NCEP ATP III Metabolic Syndrome Definition (Circulation 2005;112:2735-2752); ADA/EASD Consensus Report on T2DM Management (Diabetes Care 2022); AASLD Practice Guidance on NAFLD (Hepatology 2023)"},
                {"title": "Microvascular damage correlation", "severity": "moderate",
                 "connection_type": "cloud_analysis",
                 "specialties": ["Neurology", "Ophthalmology", "Endocrinology"],
                 "description": "Here\u2019s something we found, and it\u2019s good that we caught it. Two things showed up that are related: changes in your eyes (retinopathy) and numbness in your feet (neuropathy). Both are caused by high blood sugar damaging tiny blood vessels. When this kind of damage shows up in the eyes and nerves, it\u2019s a signal to watch the kidneys more closely too \u2014 since they have similar small blood vessels.",
                 "patient_data_points": [
                     "Early diabetic eye changes (retinopathy) found",
                     "Numbness and tingling in the feet (neuropathy)",
                     "Both point to small blood vessel damage from diabetes",
                 ],
                 "question_for_doctor": "I have both eye changes and nerve symptoms from diabetes. Since these both involve small blood vessel damage, should we be checking my kidneys more often? I want to catch any changes early.",
                 "evidence_source": "ADA Microvascular Complications Standards, AAO Diabetic Retinopathy PPP, AAN Diabetic Neuropathy Guidelines",
                 "diagnostic_source": "ADA Standards: Microvascular Complications (Diabetes Care 2025); AAO Preferred Practice Pattern: Diabetic Retinopathy (Ophthalmology 2020); AAN Practice Guideline: Diabetic Neuropathy (Neurology 2017)"},
            ],
            "community_insights": [
                {"title": "SGLT2 inhibitors show renal and cardiac benefits in T2DM",
                 "detail": "Recent RCTs show SGLT2 inhibitors reduce CKD progression by 30-40% and heart failure hospitalizations by 35% in T2DM patients with declining eGFR.",
                 "source": "CREDENCE/DAPA-CKD trials"},
                {"title": "Statin-gene interaction awareness growing",
                 "detail": "SLCO1B1 pharmacogenomic testing is increasingly recommended before high-dose statin therapy. Rosuvastatin or pravastatin have lower SLCO1B1 dependence.",
                 "source": "CPIC Guidelines 2024"},
                {"title": "Continuous glucose monitoring improves HbA1c outcomes",
                 "detail": "CGM use in insulin-treated T2DM patients shows average 0.5-1.0% HbA1c reduction. Insurance coverage expanding in 2025.",
                 "source": "ADA Standards of Care 2025"},
            ],
            "literature": [
                {"title": "Empagliflozin, Cardiovascular Outcomes, and Mortality in Type 2 Diabetes",
                 "journal": "New England Journal of Medicine",
                 "year": 2025, "relevance": "Directly relevant — SGLT2 inhibitor trial for cardiorenal protection in T2DM"},
                {"title": "CPIC Guideline for Statins and SLCO1B1, ABCG2, and CYP2C9",
                 "journal": "Clinical Pharmacology & Therapeutics",
                 "year": 2024, "relevance": "Patient carries SLCO1B1 variant affecting atorvastatin metabolism"},
                {"title": "ADA Standards of Medical Care in Diabetes — 2025",
                 "journal": "Diabetes Care",
                 "year": 2025, "relevance": "Current treatment guidelines for all aspects of this patient's diabetes management"},
                {"title": "Diabetic Peripheral Neuropathy: Pathogenesis and Treatment",
                 "journal": "The Lancet Neurology",
                 "year": 2024, "relevance": "Patient has active diabetic neuropathy with progression of symptoms"},
                {"title": "GLP-1 Receptor Agonists for Obesity and Type 2 Diabetes: A Review",
                 "journal": "JAMA",
                 "year": 2025, "relevance": "Patient has obesity + T2DM — GLP-1 RA may address both conditions"},
            ],
            "questions_for_doctor": [
                {"question": "Given my declining kidney function and cardiovascular risk, are there medication classes that could address both?",
                 "context": "eGFR dropped from 92 to 78 in 18 months. Multiple drug classes have evidence for slowing CKD progression in T2DM.",
                 "priority": "high"},
                {"question": "My SLCO1B1 genetic variant increases statin side effect risk. Should we switch from atorvastatin to a different statin?",
                 "context": "SLCO1B1 rs4149056 T/C — CPIC recommends considering rosuvastatin or pravastatin as alternatives.",
                 "priority": "high"},
                {"question": "Would a GLP-1 receptor agonist (semaglutide) be appropriate for combined weight loss and glucose control?",
                 "context": "BMI 32.2, HbA1c 8.2%. GLP-1 RA could address obesity, improve HbA1c, and reduce cardiovascular risk.",
                 "priority": "moderate"},
                {"question": "Should I be using a continuous glucose monitor (CGM) given my insulin therapy?",
                 "context": "Currently on basal insulin with suboptimal control. CGM may help optimize dosing and catch hypoglycemia.",
                 "priority": "moderate"},
                {"question": "Is it time to schedule my overdue eye exam given the retinopathy diagnosis?",
                 "context": "Last dilated eye exam was June 2024. NPDR was found. Annual follow-up is standard of care.",
                 "priority": "high"},
                {"question": "Should gabapentin dose be adjusted given my declining kidney function?",
                 "context": "Gabapentin is renally cleared. eGFR 78 is still above the 60 threshold for dose adjustment, but trending down.",
                 "priority": "low"},
            ],
        },
    }


# ── File Upload ───────────────────────────────────────────────

@app.route("/api/upload", methods=["POST"])
def upload_files():
    """Handle file upload (drag-and-drop or file picker)."""
    if not _passphrase:
        return jsonify({"error": "Vault not unlocked"}), 401

    if "files" not in request.files:
        return jsonify({"error": "No files provided"}), 400

    if _pipeline_thread and _pipeline_thread.is_alive():
        return jsonify({"error": "Cannot upload while analysis is running"}), 409

    # Clear previous uploads so only the current batch is analyzed
    if UPLOAD_DIR.exists():
        shutil.rmtree(UPLOAD_DIR)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    uploaded = []

    for file in request.files.getlist("files"):
        if file.filename:
            safe_name = f"{uuid.uuid4().hex[:8]}_{file.filename}"
            filepath = UPLOAD_DIR / safe_name
            file.save(str(filepath))
            uploaded.append({
                "name": file.filename,
                "path": str(filepath),
                "size": filepath.stat().st_size,
            })

    return jsonify({
        "uploaded": len(uploaded),
        "files": uploaded,
    })


# ── Pipeline ──────────────────────────────────────────────────

@app.route("/api/analyze", methods=["POST"])
def start_analysis():
    """Start the analysis pipeline."""
    global _pipeline_thread

    if not _passphrase:
        return jsonify({"error": "Vault not unlocked"}), 401

    if _pipeline_thread and _pipeline_thread.is_alive():
        return jsonify({"error": "Analysis already running"}), 409

    # Gather uploaded files
    if not UPLOAD_DIR.exists():
        return jsonify({"error": "No files uploaded"}), 400

    input_files = list(UPLOAD_DIR.glob("*"))
    input_files = [f for f in input_files if f.is_file() and not f.name.startswith(".")]

    if not input_files:
        return jsonify({"error": "No files to analyze"}), 400

    # Start pipeline in background thread
    _pipeline_thread = threading.Thread(
        target=_run_pipeline,
        args=(input_files,),
        daemon=True,
    )
    _pipeline_thread.start()

    return jsonify({
        "status": "started",
        "file_count": len(input_files),
    })


def _run_pipeline(input_files: list[Path]):
    """Run the pipeline in a background thread."""
    global _profile_data

    # Reset progress state for new run
    _pipeline_progress["pass"] = "starting"
    _pipeline_progress["message"] = "Preparing analysis..."
    _pipeline_progress["percent"] = 0
    _pipeline_progress["timestamp"] = time.time()
    _pipeline_progress["terminal_log"] = []

    try:
        from src.ui.pipeline import Pipeline

        def progress_callback(pass_name, message, percent):
            _broadcast_progress({
                "pass": pass_name,
                "message": message,
                "percent": percent,
                "timestamp": time.time(),
            })

        def profile_update_callback(snapshot):
            """Called after each MedGemma chunk — update dashboard data.

            Merges pipeline-owned keys (clinical_timeline, analysis,
            processed_files) into the existing _profile_data rather than
            replacing it wholesale.  This preserves user additions made
            through the UI (symptoms, vitals, demographics) during the run.

            Auto-saves to the encrypted vault after each merge so progress
            survives crashes or browser refreshes.
            """
            global _profile_data
            if _profile_data is None:
                _profile_data = snapshot
            else:
                for key in ("clinical_timeline", "analysis", "processed_files"):
                    if key in snapshot:
                        _profile_data[key] = snapshot[key]
            _save_profile_to_vault()

        pipeline = Pipeline(
            DATA_DIR,
            _passphrase,
            progress_callback,
            profile_update_callback=profile_update_callback,
            pause_event=_pipeline_paused,
            api_calls_event=_api_calls_allowed,
        )
        profile = pipeline.run(input_files)

        _profile_data = profile.model_dump(mode="json")
        _save_profile_to_vault()

    except Exception as e:
        error_type = type(e).__name__
        logger.error("Pipeline thread failed (error_type=%s)", error_type)
        _broadcast_progress({
            "pass": "error",
            "message": f"Analysis failed ({error_type})",
            "percent": -1,
            "timestamp": time.time(),
        })


@app.route("/api/progress")
def progress_stream():
    """Server-Sent Events stream for pipeline progress.

    Each connection gets its own queue so page refreshes don't lose
    events and multiple browser tabs work correctly.
    """
    listener_q = queue.Queue(maxsize=500)
    with _sse_listeners_lock:
        _sse_listeners.append(listener_q)

    def generate():
        try:
            while True:
                try:
                    event = listener_q.get(timeout=30)
                    yield f"data: {json.dumps(event)}\n\n"

                    if event.get("pass") in ("complete", "error"):
                        break

                except queue.Empty:
                    # Send keepalive
                    yield f"data: {json.dumps({'pass': 'heartbeat', 'message': 'waiting', 'percent': -1})}\n\n"
        finally:
            # Clean up when client disconnects
            with _sse_listeners_lock:
                if listener_q in _sse_listeners:
                    _sse_listeners.remove(listener_q)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/api/pipeline/status")
def pipeline_status():
    """Return persisted pipeline progress so the UI can restore on refresh."""
    running = _pipeline_running()
    paused = not _pipeline_paused.is_set()
    return jsonify({
        "running": running,
        "paused": paused,
        "api_calls_paused": not _api_calls_allowed.is_set(),
        "pass": _pipeline_progress["pass"],
        "message": _pipeline_progress["message"],
        "percent": _pipeline_progress["percent"],
        "timestamp": _pipeline_progress["timestamp"],
        "terminal_log": _pipeline_progress["terminal_log"] if running else [],
    })


@app.route("/api/pipeline/pause", methods=["POST"])
def toggle_pause():
    """Toggle pipeline pause/resume. When paused, safe to close laptop."""
    if _pipeline_paused.is_set():
        # Currently running → pause
        _pipeline_paused.clear()
        _broadcast_progress({
            "pass": "paused",
            "message": "Pipeline paused — safe to close laptop",
            "percent": -1,
            "timestamp": time.time(),
        })
        logger.info("Pipeline paused by user")
        return jsonify({"state": "paused"})
    else:
        # Currently paused → resume
        _pipeline_paused.set()
        _broadcast_progress({
            "pass": "log",
            "message": "Pipeline resumed",
            "percent": -1,
            "timestamp": time.time(),
        })
        logger.info("Pipeline resumed by user")
        return jsonify({"state": "running"})


@app.route("/api/pipeline/api-calls", methods=["POST"])
def set_api_call_state():
    """Pause or resume external API stages without stopping local processing."""
    data = request.get_json(silent=True) or {}
    requested_paused = data.get("paused")
    if not isinstance(requested_paused, bool):
        requested_paused = _api_calls_allowed.is_set()

    if requested_paused:
        _api_calls_allowed.clear()
        state = "paused"
        message = (
            "API calls paused — local record processing will continue. "
            "Any in-flight request will finish."
        )
        event_name = "api_calls_paused"
    else:
        _api_calls_allowed.set()
        state = "enabled"
        message = "API calls enabled — they will start only after local processing passes."
        event_name = "api_calls_resumed"

    if _pipeline_running():
        _broadcast_progress({
            "pass": event_name,
            "message": message,
            "percent": -1,
            "timestamp": time.time(),
        })
    logger.info(message)
    return jsonify({
        "state": state,
        "api_calls_paused": requested_paused,
        "pipeline_running": _pipeline_running(),
    })


# ── Profile Data API ──────────────────────────────────────────

@app.route("/api/demographics")
def get_demographics():
    """Return patient demographics for gender-aware 3D model loading."""
    if not _profile_data:
        return jsonify({"biological_sex": None, "birth_year": None})

    demographics = _profile_data.get("demographics", {})
    return jsonify({
        "biological_sex": demographics.get("biological_sex"),
        "birth_year": demographics.get("birth_year"),
        "location": demographics.get("location"),
    })


@app.route("/api/location", methods=["GET"])
def get_location():
    """Get patient's stored location."""
    if not _profile_data:
        return jsonify({"location": None})

    demographics = _profile_data.get("demographics", {})
    return jsonify({"location": demographics.get("location", "")})


@app.route("/api/location", methods=["POST"])
def set_location():
    """Save patient's location for environmental risk analysis."""
    global _profile_data
    if not _passphrase:
        return jsonify({"error": "Vault not unlocked"}), 401

    data = request.get_json()
    location = data.get("location", "").strip()

    if _profile_data is None:
        _profile_data = {}

    if "demographics" not in _profile_data:
        _profile_data["demographics"] = {}

    _profile_data["demographics"]["location"] = location

    # Save to vault
    try:
        from src.encryption import EncryptedVault
        from src.analysis.environmental_sources import update_environmental_sync_settings
        vault = EncryptedVault(DATA_DIR, _passphrase)
        vault.save_profile(_profile_data)
        update_environmental_sync_settings(
            DATA_DIR,
            {
                "next_run_at": "",
                "last_error": "",
            },
        )
    except Exception as e:
        logger.error("Failed to save location (error_type=%s)", type(e).__name__)
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "saved", "location": location})


@app.route("/api/environmental")
def get_environmental():
    """Analyze environmental/geographic health risks for patient's location."""
    try:
        from src.analysis.environmental import EnvironmentalRiskEngine
        from src.analysis.environmental_sources import load_environmental_sync_settings
        engine = EnvironmentalRiskEngine(DATA_DIR)
        result = engine.analyze(_profile_data or {})
        result["sync_settings"] = load_environmental_sync_settings(DATA_DIR)
        return jsonify(result)
    except Exception as e:
        logger.error("Environmental analysis failed (error_type=%s)", type(e).__name__)
        return jsonify({"error": str(e)}), 500


@app.route("/api/environmental/settings", methods=["GET"])
def get_environmental_settings():
    """Return auto-sync settings and the full environmental source inventory."""
    if not _passphrase:
        return jsonify({"error": "Vault not unlocked"}), 401

    try:
        from src.analysis.environmental_sources import (
            get_environmental_source_catalog,
            load_environmental_sync_settings,
        )
        from src.analysis.environmental_sync import EnvironmentalDataSync

        return jsonify({
            "settings": load_environmental_sync_settings(DATA_DIR),
            "source_catalog": get_environmental_source_catalog(DATA_DIR),
            "automated_source_ids": list(EnvironmentalDataSync.AUTOMATED_SOURCE_IDS),
        })
    except Exception as e:
        logger.error(
            "Failed to load environmental settings (error_type=%s)",
            type(e).__name__,
        )
        return jsonify({"error": str(e)}), 500


@app.route("/api/environmental/settings", methods=["POST"])
def save_environmental_settings():
    """Save environmental auto-sync settings."""
    if not _passphrase:
        return jsonify({"error": "Vault not unlocked"}), 401

    data = request.get_json(silent=True) or {}
    enabled = bool(data.get("enabled"))
    interval_hours = data.get("interval_hours", 24)
    source_ids = data.get("source_ids") or []

    try:
        interval_hours = max(1, int(interval_hours))
    except (TypeError, ValueError):
        return jsonify({"error": "interval_hours must be an integer"}), 400

    try:
        from src.analysis.environmental_sources import (
            get_environmental_source_catalog,
            update_environmental_sync_settings,
        )
        from src.analysis.environmental_sync import EnvironmentalDataSync

        allowed_ids = {item["id"] for item in get_environmental_source_catalog(DATA_DIR)}
        selected_ids = [
            source_id for source_id in source_ids
            if isinstance(source_id, str) and source_id in allowed_ids
        ]
        if not selected_ids:
            selected_ids = list(EnvironmentalDataSync.AUTOMATED_SOURCE_IDS)

        settings = update_environmental_sync_settings(
            DATA_DIR,
            {
                "enabled": enabled,
                "interval_hours": interval_hours,
                "source_ids": selected_ids,
                "next_run_at": "" if enabled else "",
                "last_status": "idle" if not enabled else "queued",
                "last_error": "",
            },
        )
        return jsonify({"status": "saved", "settings": settings})
    except Exception as e:
        logger.error(
            "Failed to save environmental settings (error_type=%s)",
            type(e).__name__,
        )
        return jsonify({"error": str(e)}), 500


@app.route("/api/environmental/sync", methods=["POST"])
def sync_environmental():
    """Fetch and stage environmental source snapshots for the saved location."""
    if not _passphrase:
        return jsonify({"error": "Vault not unlocked"}), 401

    data = request.get_json(silent=True) or {}
    source_ids = data.get("sources")
    force = bool(data.get("force", False))

    try:
        from src.analysis.environmental_sync import EnvironmentalDataSync
        from src.analysis.environmental_sources import (
            load_environmental_sync_settings,
            update_environmental_sync_settings,
        )
        from src.encryption import EncryptedVault

        vault = EncryptedVault(DATA_DIR, _passphrase)
        keys = vault.load_api_keys() or {}
        syncer = EnvironmentalDataSync(DATA_DIR, api_keys=keys)
        result = syncer.sync_profile(_profile_data or {}, source_ids=source_ids, force=force)
        settings = load_environmental_sync_settings(DATA_DIR)
        update_environmental_sync_settings(
            DATA_DIR,
            {
                "last_run_at": result.get("synced_at", ""),
                "next_run_at": (
                    (
                        datetime.fromisoformat(result.get("synced_at", "").replace("Z", "+00:00"))
                        + timedelta(hours=max(1, int(settings.get("interval_hours", 24) or 24)))
                    ).isoformat()
                    if result.get("synced_at")
                    else settings.get("next_run_at", "")
                ),
                "last_status": "ok" if not result.get("summary", {}).get("errors") else "error",
                "last_error": "",
                "last_summary": result.get("summary", {}),
            },
        )
        return jsonify(result)
    except Exception as e:
        logger.error("Environmental sync failed (error_type=%s)", type(e).__name__)
        try:
            from src.analysis.environmental_sources import update_environmental_sync_settings

            update_environmental_sync_settings(
                DATA_DIR,
                {
                    "last_run_at": datetime.now().astimezone().isoformat(),
                    "last_status": "error",
                    "last_error": str(e),
                },
            )
        except Exception:
            pass
        return jsonify({"error": str(e)}), 500


@app.route("/api/medications")
def get_medications():
    """Get medications list."""
    if not _profile_data:
        return jsonify([])
    timeline = _profile_data.get("clinical_timeline", {})
    return jsonify(timeline.get("medications", []))


@app.route("/api/labs")
def get_labs():
    """Get lab results."""
    if not _profile_data:
        return jsonify([])
    timeline = _profile_data.get("clinical_timeline", {})
    return jsonify(timeline.get("labs", []))


@app.route("/api/diagnoses")
def get_diagnoses():
    """Get diagnoses."""
    if not _profile_data:
        return jsonify([])
    timeline = _profile_data.get("clinical_timeline", {})
    return jsonify(timeline.get("diagnoses", []))


@app.route("/api/imaging")
def get_imaging():
    """Get imaging studies."""
    if not _profile_data:
        return jsonify([])
    timeline = _profile_data.get("clinical_timeline", {})
    return jsonify(timeline.get("imaging", []))


@app.route("/api/genetics")
def get_genetics():
    """Get genetic variants."""
    if not _profile_data:
        return jsonify([])
    timeline = _profile_data.get("clinical_timeline", {})
    return jsonify(timeline.get("genetics", []))


def _stringify_evidence(item):
    """Coerce one evidence entry to a readable string (never '[object Object]')."""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        value = str(item.get("value") or "").strip()
        source = str(item.get("source") or "").strip()
        date = str(item.get("date") or "").strip()
        attribution = ", ".join(part for part in (source, date) if part)
        if value and attribution:
            return f"{value} — {attribution}"
        if value or attribution:
            return value or attribution
        # Unknown dict shape: join its non-empty scalar values.
        return " · ".join(
            str(v).strip() for v in item.values() if v not in (None, "", [], {})
        )
    return str(item)


def _record_source_index(profile: dict) -> list[dict]:
    """Build a PHI-safe index of clinical labels and their source metadata."""
    timeline = profile.get("clinical_timeline", {})
    if not isinstance(timeline, dict):
        return []

    index = []
    for collection in (
        "medications", "labs", "imaging", "diagnoses", "procedures",
        "allergies", "genetics", "notes", "vitals",
    ):
        for item in timeline.get(collection, []):
            if not isinstance(item, dict):
                continue
            provenance = item.get("provenance")
            if not isinstance(provenance, dict) or not provenance.get("source_file"):
                continue

            labels = []
            for key in (
                "name", "test_name", "gene", "allergen", "description",
                "summary", "body_region", "modality",
            ):
                value = item.get(key)
                if isinstance(value, str) and len(value.strip()) >= 3:
                    labels.append(value.strip().lower())

            for finding in item.get("findings", []):
                if isinstance(finding, dict):
                    description = str(finding.get("description") or "").strip()
                    if len(description) >= 3:
                        labels.append(description.lower())

            if labels:
                public_provenance = {
                    key: provenance.get(key)
                    for key in (
                        "source_file", "source_page", "date_extracted",
                        "extraction_model", "confidence",
                    )
                    if provenance.get(key) is not None
                }
                index.append({"labels": labels, "provenance": public_provenance})
    return index


def _enrich_finding_metadata(item: dict, source_index: list[dict]) -> dict:
    """Attach only provenance that can be matched to this derived finding."""
    enriched = dict(item)

    def public_provenance(value):
        if not isinstance(value, dict) or not value.get("source_file"):
            return None
        return {
            key: value.get(key)
            for key in (
                "source_file", "source_page", "date_extracted",
                "extraction_model", "confidence",
            )
            if value.get(key) is not None
        }

    existing = enriched.get("provenance")
    if isinstance(existing, dict):
        candidate = public_provenance(existing)
        provenance = [candidate] if candidate else []
    elif isinstance(existing, list):
        provenance = [
            candidate for candidate in (
                public_provenance(value) for value in existing
            )
            if candidate
        ]
    else:
        provenance = []

    if not provenance and enriched.get("source_file"):
        provenance = [{
            "source_file": enriched.get("source_file"),
            "source_page": enriched.get("source_page"),
            "confidence": enriched.get("confidence"),
        }]

    if not provenance:
        evidence = enriched.get("evidence") or []
        if not isinstance(evidence, (list, tuple)):
            evidence = [evidence]
        text = " ".join([
            str(enriched.get("title") or ""),
            str(enriched.get("description") or enriched.get("pattern") or ""),
            " ".join(_stringify_evidence(value) for value in evidence),
            " ".join(str(value) for value in enriched.get("patient_data_points", [])),
            " ".join(str(value) for value in enriched.get("matched_labs", [])),
        ]).lower()

        finding_text = text.strip()
        if finding_text:
            seen = set()
            for source in source_index:
                if not any(
                    label in finding_text
                    or (len(finding_text) <= 120 and finding_text in label)
                    for label in source["labels"]
                ):
                    continue
                candidate = source["provenance"]
                key = (
                    candidate.get("source_file"),
                    candidate.get("source_page"),
                    candidate.get("extraction_model"),
                )
                if key not in seen:
                    seen.add(key)
                    provenance.append(candidate)
                if len(provenance) >= 8:
                    break

    enriched["provenance"] = provenance
    if enriched.get("confidence") is None:
        confidence_values = [
            p.get("confidence") for p in provenance
            if isinstance(p.get("confidence"), (int, float))
        ]
        if confidence_values:
            enriched["confidence"] = round(
                sum(confidence_values) / len(confidence_values), 3
            )
        elif enriched.get("total_hits") and enriched.get("total_possible"):
            enriched["confidence"] = round(
                enriched["total_hits"] / enriched["total_possible"], 3
            )
    return enriched


def _normalize_flag(flag):
    """Return a copy of `flag` conforming to the ClinicalFlag render contract.

    The frontend and the ClinicalFlag model expect `description` (str) and
    `evidence` (list[str]). Legacy/demo producers used `detail` and emitted
    evidence as {source, date, value} objects; normalizing here keeps that
    shape from reaching the UI as an empty line or "[object Object]".
    """
    normalized = dict(flag)
    normalized["description"] = (
        flag.get("description") or flag.get("detail") or flag.get("explanation") or ""
    )
    evidence = flag.get("evidence") or []
    if not isinstance(evidence, (list, tuple)):
        evidence = [evidence]
    normalized["evidence"] = [_stringify_evidence(item) for item in evidence]
    return normalized


@app.route("/api/flags")
def get_flags():
    """Get clinical flags and patterns, including missing negative gaps."""
    if not _profile_data:
        return jsonify([])

    analysis = _profile_data.get("analysis", {})
    flags = list(analysis.get("flags", []))

    # Append missing-negative monitoring gaps as moderate flags
    try:
        from src.analysis.missing_negatives import MissingNegativeDetector

        detector = MissingNegativeDetector()
        gaps = detector.analyze(_profile_data)

        for gap in gaps:
            status_label = (
                "Never tested" if gap["status"] == "never_tested"
                else f"Overdue by ~{gap.get('months_overdue', '?')} months"
            )
            flags.append({
                "severity": gap["severity"],
                "category": "Monitoring Gap",
                "title": f"{gap['missing_test']} — {gap['condition']}",
                "description": gap["recommendation"],
                "evidence": [
                    f"Status: {status_label}",
                    f"Expected: {gap['expected_frequency']}",
                ],
            })
    except Exception as e:
        logger.debug(
            "Missing-negative detection in flags failed (error_type=%s)",
            type(e).__name__,
        )

    # Append environmental/geographic risk flags
    try:
        from src.analysis.environmental import EnvironmentalRiskEngine

        engine = EnvironmentalRiskEngine()
        env_result = engine.analyze(_profile_data)

        for risk in env_result.get("risks", []):
            # Only surface personalized risks (score > 0) or high severity
            if risk["relevance_score"] > 0 or risk["severity"] == "high":
                evidence = list(risk.get("relevance_reasons", []))
                if not evidence:
                    evidence = [risk["description"]]
                flags.append({
                    "severity": risk["severity"],
                    "category": "Environmental Risk",
                    "title": risk["name"],
                    "description": risk["action"],
                    "evidence": evidence,
                })
    except Exception as e:
        logger.debug(
            "Environmental-risk detection in flags failed (error_type=%s)",
            type(e).__name__,
        )

    # Append radiomic threshold flags from imaging findings
    try:
        timeline = _profile_data.get("clinical_timeline", {})
        for study in timeline.get("imaging", []):
            for finding in study.get("findings", []):
                radiomic = finding.get("radiomic_features", {})
                for tf in radiomic.get("threshold_flags", []):
                    flags.append({
                        "severity": tf.get("level", "moderate"),
                        "category": "Radiomic Finding",
                        "title": f"Imaging: {finding.get('description', 'Finding')[:60]}",
                        "description": tf.get("message", ""),
                        "evidence": [
                            f"Feature: {tf.get('feature', '?')}",
                            f"Value: {tf.get('value', '?')}",
                            f"Threshold: {tf.get('threshold', '?')}",
                        ],
                    })
    except Exception as e:
        logger.debug(
            "Radiomic flag extraction failed (error_type=%s)",
            type(e).__name__,
        )

    source_index = _record_source_index(_profile_data)
    return jsonify([
        _enrich_finding_metadata(_normalize_flag(flag), source_index)
        for flag in flags
    ])


# ── Dashboard Helpers ─────────────────────────────────────

def _get_latest_labs(labs):
    """Return the most recent result for each unique lab test name."""
    latest = {}
    for lab in labs:
        name = lab.get("test_name") or lab.get("name") or "Unknown"
        # The canonical field is `test_date` (LabResult model). The legacy
        # `date` / `collected_date` fallbacks kept us from silently breaking
        # on older payloads, but without `test_date` here every lab looked
        # undated, so "latest" collapsed to "first seen in list order".
        date = (
            lab.get("test_date")
            or lab.get("date")
            or lab.get("collected_date")
            or ""
        )
        if name not in latest or date > latest[name].get("_sort_date", ""):
            entry = dict(lab)
            entry["_sort_date"] = date
            latest[name] = entry
    # Remove helper key and return list
    result = []
    for entry in latest.values():
        entry.pop("_sort_date", None)
        result.append(entry)
    return result


def _normalize_lab_name(raw: str) -> str:
    """Collapse whitespace, underscores, and casing so that
    'Avg HR', 'AvgHR', 'Avg_HR', 'avg hr' all map to the same key.
    Returns a human-friendly display form (title-cased, single spaces).
    """
    import re
    # Insert space before capital letters in camelCase: "AvgHR" -> "Avg HR"
    s = re.sub(r'([a-z])([A-Z])', r'\1 \2', raw)
    # Replace underscores and multiple spaces with single space
    s = re.sub(r'[_\s]+', ' ', s).strip()
    # Title-case for display
    return s.title() if s else raw


def _get_lab_trends(labs):
    """Return labs that have 3+ data points, suitable for sparkline rendering."""
    from collections import defaultdict
    by_name = defaultdict(list)
    # Map normalized keys -> display name (use first occurrence as canonical)
    display_names = {}
    for lab in labs:
        raw_name = lab.get("test_name") or lab.get("name") or "Unknown"
        norm = _normalize_lab_name(raw_name)
        if norm not in display_names:
            display_names[norm] = norm  # use the normalized title-case form
        value = lab.get("value")
        date = (
            lab.get("test_date")
            or lab.get("date")
            or lab.get("collected_date")
            or ""
        )
        # Time-scale rendering (d3.scaleTime) needs real dates; empty-string
        # dates parse to Invalid Date and collapse every point onto the same
        # x coordinate, which looks like "several Low readings on one day".
        if not date:
            continue
        if value is not None:
            try:
                numeric_val = float(str(value).replace(",", ""))
            except (ValueError, TypeError):
                continue
            by_name[norm].append({
                "date": date,
                "value": numeric_val,
                "unit": lab.get("unit", ""),
                "ref_low": lab.get("reference_low"),
                "ref_high": lab.get("reference_high"),
            })
    # Only return tests with 3+ data points, sorted by date
    trends = {}
    for norm, points in by_name.items():
        if len(points) >= 3:
            trends[display_names[norm]] = sorted(points, key=lambda p: p["date"])
    return trends


def _count_visit_prep_items():
    """Count how many items would appear in a visit prep report."""
    if not _profile_data:
        return 0
    analysis = _profile_data.get("analysis", {})
    count = 0
    count += len(analysis.get("flags", []))
    count += len(analysis.get("cross_disciplinary", []))
    count += len(analysis.get("drug_interactions", []))
    return count


_SEVERITY_ORDER = {"critical": 0, "high": 1, "moderate": 2, "low": 3, "info": 4}


def _compose_dashboard_narrative(analysis, severity_counts, flags,
                                 active_meds, diagnoses, latest_labs):
    """Plain-language dashboard summary.

    Prefers a pipeline-written executive summary when one exists; otherwise
    composes a deterministic overview from data already on the dashboard so
    the panel populates even for local-only runs with no cloud passes.
    """
    pipeline_summary = str(
        analysis.get("executive_summary") or analysis.get("summary") or ""
    ).strip()
    if pipeline_summary:
        return pipeline_summary

    if not (flags or active_meds or diagnoses or latest_labs):
        return ""

    inventory = []
    if diagnoses:
        inventory.append(f"{len(diagnoses)} tracked condition{'s' if len(diagnoses) != 1 else ''}")
    if active_meds:
        inventory.append(f"{len(active_meds)} active medication{'s' if len(active_meds) != 1 else ''}")
    if latest_labs:
        inventory.append(f"{len(latest_labs)} recent lab result{'s' if len(latest_labs) != 1 else ''}")

    if len(inventory) > 1:
        joined = ", ".join(inventory[:-1]) + " and " + inventory[-1]
    else:
        joined = inventory[0] if inventory else ""

    parts = []
    if joined:
        parts.append(f"Your records show {joined}.")

    if flags:
        needs_attention = severity_counts.get("critical", 0) + severity_counts.get("high", 0)
        sentence = f"The analysis surfaced {len(flags)} finding{'s' if len(flags) != 1 else ''} to review"
        if needs_attention:
            sentence += (
                f" — {needs_attention} may need prompt attention"
            )
        top = min(
            (f for f in flags if f.get("title")),
            key=lambda f: _SEVERITY_ORDER.get((f.get("severity") or "info").lower(), 4),
            default=None,
        )
        if top:
            sentence += f". Start with: {top['title']}"
        parts.append(sentence + ".")

        gaps = [f for f in flags if f.get("category") == "Monitoring Gap"]
        if gaps:
            verb = "checks look" if len(gaps) != 1 else "check looks"
            parts.append(f"{len(gaps)} routine {verb} overdue or missing.")

    parts.append(
        "Open the Flags tab for details, or use Visit Prep to build "
        "questions for your next appointment."
    )
    return " ".join(parts)


@app.route("/api/dashboard")
def get_dashboard():
    """Aggregate all data needed for the diagnostic dashboard."""
    if not _profile_data:
        return jsonify({"has_data": False})

    clinical = _profile_data.get("clinical_timeline", {})
    analysis = _profile_data.get("analysis", {})

    # Latest labs with flags
    labs = clinical.get("labs", [])
    latest_labs = _get_latest_labs(labs)

    # Labs with 3+ data points for sparklines
    lab_trends = _get_lab_trends(labs)

    # Active medications — list for donut breakdown
    meds = clinical.get("medications", [])
    active_meds = [m for m in meds if (m.get("status") or "").lower() != "discontinued"]

    # Normalize medication routes so "by mouth", "by_mouth", "mouth",
    # "oral", "BY MOUTH", "Oral" etc. all collapse into one category.
    _ROUTE_ALIASES = {
        "by mouth": "Oral", "by_mouth": "Oral", "mouth": "Oral",
        "oral": "Oral", "po": "Oral",
        "tablet": "Oral", "capsule": "Oral",
        "by": "Oral",  # truncated "by mouth"
        "iv": "IV", "intravenous": "IV",
        "topical": "Topical", "transdermal": "Topical",
        "subcutaneous": "Subcutaneous", "sq": "Subcutaneous", "subq": "Subcutaneous",
        "intramuscular": "Intramuscular", "im": "Intramuscular",
        "inhaled": "Inhaled", "inhalation": "Inhaled",
        "sublingual": "Sublingual",
        "rectal": "Rectal", "ophthalmic": "Ophthalmic",
        "nasal": "Nasal", "otic": "Otic",
    }

    meds_by_route = {}
    for m in active_meds:
        raw_route = (m.get("route") or m.get("category") or "").strip()
        normalized = _ROUTE_ALIASES.get(raw_route.lower(), raw_route) if raw_route else "Other"
        if not normalized:
            normalized = "Other"
        meds_by_route[normalized] = meds_by_route.get(normalized, 0) + 1
    meds_breakdown = [{"label": k, "value": v} for k, v in meds_by_route.items()]
    meds_list = [{"name": m.get("name") or "Unknown", "dose": m.get("dose", ""),
                  "route": m.get("route", "")} for m in active_meds]

    # Active diagnoses — list for bar chart
    diagnoses = clinical.get("diagnoses", [])
    diagnoses_list = []
    for dx in diagnoses:
        name = dx.get("name") or dx.get("condition") or "Unknown"
        sev = (dx.get("severity") or "info").lower()
        diagnoses_list.append({"name": name, "severity": sev})

    # Symptoms — list with episode counts for bar chart
    symptoms = clinical.get("symptoms", [])
    symptoms_list = []
    for s in symptoms:
        name = s.get("symptom_name") or s.get("name") or "Unknown"
        ep_count = len(s.get("episodes", []))
        if ep_count == 0:
            ep_count = 1  # flat entries without episodes array count as 1
        symptoms_list.append({"name": name, "episodes": ep_count})
    symptoms_list.sort(key=lambda x: x["episodes"], reverse=True)

    # Flags — with severity breakdown for stacked bar
    flags = list(analysis.get("flags", []))
    severity_counts = {"critical": 0, "high": 0, "moderate": 0, "low": 0}
    for f in flags:
        sev = (f.get("severity") or "low").lower()
        if sev in severity_counts:
            severity_counts[sev] += 1
        else:
            severity_counts["low"] += 1
    flags_list = [{"title": f.get("title") or f.get("flag") or "—",
                   "severity": (f.get("severity") or "low").lower(),
                   "detail": f.get("detail") or f.get("explanation") or ""}
                  for f in flags[:20]]

    # Missing negatives / monitoring gaps
    missing = [f for f in flags if f.get("category") == "Monitoring Gap"]

    # PGx collision count + details
    pgx_alerts = analysis.get("drug_gene_interactions", [])
    pgx_list = [{"drug": p.get("drug", ""), "gene": p.get("gene", ""),
                 "impact": p.get("impact") or p.get("severity", "")}
                for p in pgx_alerts[:10]]

    # Cross-specialty patterns
    cross_spec = analysis.get("cross_disciplinary", [])
    cross_spec_list = [{"title": c.get("title") or c.get("pattern") or "—",
                        "specialties": c.get("specialties", []),
                        "severity": (c.get("severity") or "info").lower()}
                       for c in cross_spec[:10]]

    # Risk score — computed from flag severities
    risk_score = (severity_counts["critical"] * 25 + severity_counts["high"] * 15
                  + severity_counts["moderate"] * 8 + severity_counts["low"] * 3)
    risk_score = min(risk_score, 100)

    return jsonify({
        "has_data": True,
        "latest_labs": latest_labs,
        "lab_trends": lab_trends,
        "active_medications": len(active_meds),
        "medications_list": meds_list,
        "medications_breakdown": meds_breakdown,
        "diagnoses_count": len(diagnoses),
        "diagnoses_list": diagnoses_list,
        "symptoms_count": len(symptoms),
        "symptoms_list": symptoms_list,
        "flags_count": len(flags),
        "flags_by_severity": severity_counts,
        "flags_list": flags_list,
        "missing_tests": missing,
        "pgx_collisions": len(pgx_alerts),
        "pgx_list": pgx_list,
        "cross_specialty_count": len(cross_spec),
        "cross_specialty_list": cross_spec_list,
        "visit_prep_items": _count_visit_prep_items(),
        "risk_score": risk_score,
        "narrative": _compose_dashboard_narrative(
            analysis, severity_counts, flags, active_meds, diagnoses, latest_labs
        ),
    })


@app.route("/api/interactions")
def get_interactions():
    """Get drug interactions."""
    if not _profile_data:
        return jsonify([])
    analysis = _profile_data.get("analysis", {})
    return jsonify(analysis.get("drug_interactions", []))


_DISMISSIBLE_KINDS = {"cross_disciplinary"}


def _dismissed_keys(kind: str = "cross_disciplinary") -> set:
    """Normalized keys of findings the reader marked 'not relevant'."""
    analysis = (_profile_data or {}).get("analysis", {}) or {}
    entries = analysis.get("dismissed_findings", []) or []
    return {
        str(item.get("key") or "")
        for item in entries
        if isinstance(item, dict)
        and item.get("kind", "cross_disciplinary") == kind
        and item.get("key")
    }


@app.route("/api/findings/dismissed")
def list_dismissed_findings():
    """Findings the reader set aside — the UI needs the count to offer undo."""
    kind = (request.args.get("kind") or "cross_disciplinary").strip()
    if kind not in _DISMISSIBLE_KINDS:
        return jsonify({"error": f"Unknown finding kind: {kind}"}), 400

    analysis = (_profile_data or {}).get("analysis", {}) or {}
    entries = [
        {
            "key": item.get("key", ""),
            "title": item.get("title", ""),
            "dismissed_at": item.get("dismissed_at", ""),
        }
        for item in analysis.get("dismissed_findings", []) or []
        if isinstance(item, dict) and item.get("kind", "cross_disciplinary") == kind
    ]
    return jsonify({"dismissed": entries})


@app.route("/api/findings/dismiss", methods=["POST"])
def dismiss_finding():
    """Mark a finding not relevant. Persists in the encrypted vault (PHI-derived)."""
    from src.analysis.crossdisc_merge import dismissal_key

    if not _profile_data:
        return jsonify({"error": "No profile loaded"}), 400

    data = request.get_json(silent=True) or {}
    kind = (data.get("kind") or "cross_disciplinary").strip()
    title = (data.get("title") or "").strip()
    if kind not in _DISMISSIBLE_KINDS:
        return jsonify({"error": f"Unknown finding kind: {kind}"}), 400
    if not title:
        return jsonify({"error": "Finding title is required"}), 400

    key = dismissal_key(title)
    if not key:
        return jsonify({"error": "Finding title is required"}), 400

    analysis = _profile_data.setdefault("analysis", {})
    entries = analysis.setdefault("dismissed_findings", [])
    already = any(
        isinstance(item, dict) and item.get("key") == key and item.get("kind") == kind
        for item in entries
    )
    if not already:
        entries.append({
            "key": key,
            "kind": kind,
            "title": title,
            "dismissed_at": datetime.now().isoformat(),
        })
        if not _save_profile_to_vault():
            entries[:] = [
                item for item in entries
                if not (isinstance(item, dict) and item.get("key") == key)
            ]
            return jsonify({"error": "Could not save your choice"}), 500

    return jsonify({"ok": True, "dismissed": sorted(_dismissed_keys(kind))})


@app.route("/api/findings/restore", methods=["POST"])
def restore_finding():
    """Undo a dismissal — one finding by title, or all of a kind."""
    from src.analysis.crossdisc_merge import dismissal_key

    if not _profile_data:
        return jsonify({"error": "No profile loaded"}), 400

    data = request.get_json(silent=True) or {}
    kind = (data.get("kind") or "cross_disciplinary").strip()
    if kind not in _DISMISSIBLE_KINDS:
        return jsonify({"error": f"Unknown finding kind: {kind}"}), 400

    analysis = _profile_data.setdefault("analysis", {})
    entries = analysis.setdefault("dismissed_findings", [])
    previous = list(entries)

    if data.get("all"):
        entries[:] = [
            item for item in entries
            if not (isinstance(item, dict) and item.get("kind", "cross_disciplinary") == kind)
        ]
    else:
        key = dismissal_key((data.get("title") or "").strip())
        if not key:
            return jsonify({"error": "Finding title is required"}), 400
        entries[:] = [
            item for item in entries
            if not (
                isinstance(item, dict)
                and item.get("key") == key
                and item.get("kind", "cross_disciplinary") == kind
            )
        ]

    if entries != previous and not _save_profile_to_vault():
        entries[:] = previous
        return jsonify({"error": "Could not save your choice"}), 500

    return jsonify({"ok": True, "dismissed": sorted(_dismissed_keys(kind))})


@app.route("/api/cross-disciplinary")
def get_cross_disciplinary():
    """Get cross-disciplinary connections, including cross-specialty correlations."""
    if not _profile_data:
        return jsonify([])

    analysis = _profile_data.get("analysis", {})
    connections = list(analysis.get("cross_disciplinary", []))

    # Merge in the snapshot-cached cross-specialty engine (rule triads +
    # local-AI discovery). The snapshot recomputes only when clinical inputs
    # change or ?refresh=1 — previously this ran Ollama + PubMed on every
    # request. Lightweight consumers such as the Body Map can request only
    # already-persisted items with ?stored=1.
    stored_only = request.args.get("stored", "").strip().lower() in {
        "1", "true", "yes",
    }
    dismissed = _dismissed_keys("cross_disciplinary")
    if not stored_only:
        try:
            from src.analysis.crossdisc_merge import merge_connections

            result = _compute_and_persist_deep_insight("cross_specialty")
            connections = merge_connections(
                connections, result.get("connections", []), dismissed_keys=dismissed
            )
        except Exception as e:
            logger.warning(
                "Cross-specialty correlation failed (error_type=%s)",
                type(e).__name__,
            )
    elif dismissed:
        from src.analysis.crossdisc_merge import dismissal_key

        connections = [
            c for c in connections
            if dismissal_key(c.get("title", "")) not in dismissed
        ]

    source_index = _record_source_index(_profile_data)
    return jsonify([
        _enrich_finding_metadata(connection, source_index)
        for connection in connections
    ])


_COMMUNITY_DISCLAIMER = (
    "Unverified community report — NOT clinical data. "
    "For discussion with your doctor only."
)


def _normalize_community(item):
    """Coerce a community insight to the render contract.

    Three shapes exist historically: the CommunityInsight model
    (description/upvote_count, no title), the demo profile
    (title/detail/source), and the renderer's expectation
    (title/summary/upvotes). Normalize them all here.
    """
    normalized = dict(item)
    description = str(
        item.get("description") or item.get("summary") or item.get("detail") or ""
    ).strip()
    normalized["description"] = description
    normalized["summary"] = normalized.get("summary") or description

    title = str(item.get("title") or "").strip()
    if not title and description:
        first_sentence = re.split(r"(?<=[.!?])\s", description)[0]
        title = first_sentence[:80] + ("…" if len(first_sentence) > 80 else "")
    if not title:
        subreddit = str(item.get("subreddit") or "").strip()
        title = f"r/{subreddit} community report" if subreddit else "Community report"
    normalized["title"] = title

    upvotes = item.get("upvotes", item.get("upvote_count", 0))
    try:
        normalized["upvotes"] = int(upvotes)
    except (TypeError, ValueError):
        normalized["upvotes"] = 0

    normalized.setdefault("disclaimer", _COMMUNITY_DISCLAIMER)
    normalized["confidence_label"] = "Unverified community signal"
    if normalized.get("post_url"):
        normalized["source_label"] = "Original community post"
    elif normalized.get("subreddit"):
        normalized["source_label"] = f"r/{normalized['subreddit']}"
    else:
        normalized["source_label"] = str(normalized.get("source") or "Community source")
    return normalized


@app.route("/api/community")
def get_community():
    """Get community insights."""
    if not _profile_data:
        return jsonify([])
    analysis = _profile_data.get("analysis", {})
    return jsonify([
        _normalize_community(item)
        for item in analysis.get("community_insights", [])
    ])


@app.route("/api/literature")
def get_literature():
    """Get literature citations."""
    if not _profile_data:
        return jsonify([])
    analysis = _profile_data.get("analysis", {})
    return jsonify(analysis.get("literature", []))


def _normalize_question_entry(entry):
    """Coerce a stored question (legacy string or object) to the render contract."""
    if isinstance(entry, dict):
        item = dict(entry)
        item["question"] = str(entry.get("question") or "").strip()
    else:
        item = {"question": str(entry or "").strip()}
    item.setdefault("context", "")
    item.setdefault("priority", "moderate")
    item.setdefault("source", "analysis")
    return item


@app.route("/api/questions", methods=["GET", "POST"])
def questions():
    """Get or add questions for doctor."""
    if not _profile_data:
        if request.method == "POST":
            return jsonify({"error": "No profile data loaded"}), 400
        return jsonify([])

    analysis = _profile_data.get("analysis")
    if not isinstance(analysis, dict):
        analysis = {}
        _profile_data["analysis"] = analysis
    questions_list = analysis.setdefault("questions_for_doctor", [])

    if request.method == "GET":
        # Merged view: stored questions (normalized to objects) plus each
        # flag's tailored question_for_doctor, deduplicated by text. The
        # stored list itself is never mutated here.
        merged, seen = [], set()
        for entry in questions_list:
            item = _normalize_question_entry(entry)
            key = item["question"].lower()
            if item["question"] and key not in seen:
                merged.append(item)
                seen.add(key)
        for flag in analysis.get("flags", []):
            tailored = str(flag.get("question_for_doctor") or "").strip()
            if tailored and tailored.lower() not in seen:
                merged.append({
                    "question": tailored,
                    "context": flag.get("title", ""),
                    "priority": (flag.get("severity") or "moderate").lower(),
                    "source": "flag",
                })
                seen.add(tailored.lower())
        return jsonify(merged)

    # POST — add a new question to the visit prep list
    data = request.get_json()
    question_text = (data.get("question") or "").strip()
    if not question_text:
        return jsonify({"error": "Question text is required"}), 400

    # Prevent exact duplicates (entries may be legacy plain strings)
    for q in questions_list:
        existing = _normalize_question_entry(q).get("question", "")
        if existing.strip().lower() == question_text.lower():
            return jsonify({"ok": True, "duplicate": True})

    new_q = {
        "question": question_text,
        "context": data.get("context", ""),
        "priority": data.get("priority", "moderate"),
        "source": data.get("source", "user"),
    }
    questions_list.append(new_q)

    # Persist to vault (reuses symptom saver — it saves the full profile)
    _save_symptoms_to_vault()

    return jsonify({"ok": True, "added": new_q})


@app.route("/api/alerts")
def get_alerts():
    """Get monitoring alerts."""
    if not _passphrase:
        return jsonify([])

    try:
        from src.database import Database
        db = Database(DATA_DIR / "cih.db")
        alerts = db.get_unaddressed_alerts()
        db.close()
        return jsonify(alerts)
    except Exception:
        return jsonify([])


@app.route("/api/sweep-now", methods=["POST"])
def sweep_now():
    """On-demand PubMed sweep using v2.0 expanded queries.

    Searches for recent publications relevant to the patient's
    symptoms, medications, medication combos, diagnoses, and genetic
    variants. Optionally uses Gemini for relevance scoring.
    """
    if not _passphrase:
        return jsonify({"error": "Vault not unlocked"}), 401

    profile = _profile_data or {}

    try:
        from src.monitoring.api_monitors.pubmed_monitor import PubMedMonitor

        # Load API keys for NCBI and Gemini
        gemini_key = None
        ncbi_key = None
        try:
            settings = profile.get("settings", {})
            gemini_key = settings.get("gemini_api_key")
            if not gemini_key:
                import os
                gemini_key = os.environ.get("GEMINI_API_KEY")
        except Exception:
            pass

        monitor = PubMedMonitor(
            api_key=ncbi_key,
            gemini_api_key=gemini_key,
        )

        # Build query summary for the UI (without executing)
        queries = monitor._build_queries_from_dict(profile)
        query_summary = {
            "total_queries": len(queries),
            "categories": {},
        }
        for q in queries:
            cat = q.get("category", "unknown")
            query_summary["categories"][cat] = (
                query_summary["categories"].get(cat, 0) + 1
            )

        # Execute the sweep
        alerts = monitor.check_from_dict(profile, days_back=30)

        # Convert to serializable dicts
        results = []
        for alert in alerts:
            severity_str = (
                alert.severity.value
                if hasattr(alert.severity, "value")
                else str(alert.severity)
            )
            results.append({
                "source": alert.source,
                "title": alert.title,
                "description": alert.description,
                "relevance": alert.relevance_explanation or "",
                "severity": severity_str,
                "url": alert.url,
            })

        return jsonify({
            "alerts": results,
            "query_summary": query_summary,
        })

    except Exception as e:
        logger.error("PubMed sweep failed (error_type=%s)", type(e).__name__)
        return jsonify({"error": str(e)}), 500


@app.route("/api/timeline")
def get_timeline():
    """Get all dated events for the timeline view."""
    if not _profile_data:
        return jsonify([])

    timeline = _profile_data.get("clinical_timeline", {})
    events = []
    notes = []

    def _first_value(*values):
        for value in values:
            if value is None:
                continue
            if isinstance(value, str):
                stripped = value.strip()
                if stripped:
                    return stripped
                continue
            return value
        return None

    def _date_value(value):
        if not value:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value

        text = str(value).strip()
        if not text:
            return None

        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            try:
                return datetime.fromisoformat(text).date()
            except ValueError:
                return None

    def _iso_date(value):
        parsed = _date_value(value)
        return parsed.isoformat() if parsed else None

    def _provenance_fields(item):
        provenance = item.get("provenance") or {}
        if not isinstance(provenance, dict):
            return {}
        return {
            "source_file": provenance.get("source_file"),
            "source_page": provenance.get("source_page"),
            "confidence": provenance.get("confidence"),
            "raw_text": provenance.get("raw_text"),
        }

    def _findings_text(findings):
        if not findings:
            return ""
        if isinstance(findings, str):
            return findings

        parts = []
        for finding in findings:
            if isinstance(finding, dict):
                text = _first_value(finding.get("description"), finding.get("summary"))
            else:
                text = str(finding).strip()
            if text:
                parts.append(text)
        return "; ".join(parts)

    def _event_provider(event):
        provider = _first_value(event.get("provider"), event.get("prescriber"))
        return provider.lower() if isinstance(provider, str) else ""

    def _related_notes(event_date, provider_name):
        if not event_date:
            return []

        ranked = []
        for note in notes:
            note_date = _date_value(note.get("date"))
            if not note_date:
                continue

            day_gap = abs((note_date - event_date).days)
            if day_gap > 7:
                continue

            note_provider = (note.get("provider") or "").strip().lower()
            same_provider = bool(provider_name and note_provider and provider_name == note_provider)

            score = day_gap * 10
            if day_gap == 0:
                score -= 20
            if same_provider:
                score -= 6

            ranked.append((score, note))

        ranked.sort(key=lambda pair: (pair[0], pair[1].get("date") or ""))
        return [note for _, note in ranked[:4]]

    def _related_events(current_index, allowed_types):
        current = events[current_index]
        event_date = _date_value(current.get("date"))
        if not event_date:
            return []

        provider_name = _event_provider(current)
        ranked = []

        for idx, other in enumerate(events):
            if idx == current_index or other.get("type") not in allowed_types:
                continue

            other_date = _date_value(other.get("date"))
            if not other_date:
                continue

            day_gap = abs((other_date - event_date).days)
            if day_gap > 7:
                continue

            other_provider = _event_provider(other)
            same_provider = bool(provider_name and other_provider and provider_name == other_provider)

            score = day_gap * 10
            if day_gap == 0:
                score -= 20
            if same_provider:
                score -= 6
            if other.get("type") == current.get("type"):
                score += 4

            ranked.append((score, {
                "date": other.get("date"),
                "type": other.get("type"),
                "title": other.get("title"),
                "detail": other.get("detail"),
            }))

        ranked.sort(key=lambda pair: (pair[0], pair[1].get("date") or ""))

        seen = set()
        related = []
        for _, item in ranked:
            key = (item.get("date"), item.get("type"), item.get("title"))
            if key in seen:
                continue
            seen.add(key)
            related.append(item)
            if len(related) >= 5:
                break

        return related

    for med in timeline.get("medications", []):
        med_date = _iso_date(med.get("start_date"))
        if med_date:
            dose_text = _first_value(med.get("dosage"), med.get("dose"))
            provider = _first_value(med.get("prescriber"), med.get("provider"))
            events.append({
                "date": med_date,
                "type": "medication",
                "title": f"Started {_first_value(med.get('name'), 'Medication')}",
                "detail": " ".join(part for part in [dose_text or "", med.get("frequency", "")] if part).strip(),
                "name": med.get("name"),
                "dosage": dose_text,
                "frequency": med.get("frequency"),
                "route": med.get("route"),
                "reason": med.get("reason"),
                "prescriber": provider,
                "provider": provider,
                "status": med.get("status"),
                **_provenance_fields(med),
            })

    for lab in timeline.get("labs", []):
        lab_date = _iso_date(_first_value(lab.get("test_date"), lab.get("date")))
        if lab_date:
            value_text = str(_first_value(lab.get("value"), lab.get("value_text"), "")).strip()
            unit_text = (lab.get("unit") or "").strip()
            flag_text = (lab.get("flag") or "").strip()
            provider = _first_value(lab.get("ordering_provider"), lab.get("provider"))
            events.append({
                "date": lab_date,
                "type": "lab",
                "title": _first_value(lab.get("name"), lab.get("test_name"), "Lab result"),
                "detail": " ".join(part for part in [value_text, unit_text, flag_text] if part),
                "name": _first_value(lab.get("name"), lab.get("test_name")),
                "value": lab.get("value"),
                "value_text": lab.get("value_text"),
                "unit": lab.get("unit"),
                "flag": lab.get("flag"),
                "reference_low": lab.get("reference_low"),
                "reference_high": lab.get("reference_high"),
                "provider": provider,
                "facility": _first_value(lab.get("lab_facility"), lab.get("facility")),
                **_provenance_fields(lab),
            })

    for dx in timeline.get("diagnoses", []):
        dx_date = _iso_date(_first_value(dx.get("date_diagnosed"), dx.get("date")))
        if dx_date:
            provider = _first_value(dx.get("diagnosing_provider"), dx.get("provider"))
            events.append({
                "date": dx_date,
                "type": "diagnosis",
                "title": _first_value(dx.get("name"), dx.get("condition"), "Diagnosis"),
                "detail": dx.get("status", ""),
                "name": _first_value(dx.get("name"), dx.get("condition")),
                "status": dx.get("status"),
                "provider": provider,
                "icd10": _first_value(dx.get("icd10"), dx.get("icd10_code")),
                **_provenance_fields(dx),
            })

    for proc in timeline.get("procedures", []):
        proc_date = _iso_date(proc.get("procedure_date"))
        if proc_date:
            provider = _first_value(proc.get("provider"), proc.get("ordering_provider"))
            detail_text = _first_value(proc.get("notes"), proc.get("outcome"), provider, "")
            events.append({
                "date": proc_date,
                "type": "procedure",
                "title": _first_value(proc.get("name"), "Procedure"),
                "detail": detail_text,
                "name": proc.get("name"),
                "provider": provider,
                "facility": proc.get("facility"),
                "notes": proc.get("notes"),
                "outcome": proc.get("outcome"),
                **_provenance_fields(proc),
            })

    for img in timeline.get("imaging", []):
        img_date = _iso_date(img.get("study_date"))
        if img_date:
            provider = _first_value(img.get("ordering_provider"), img.get("provider"))
            findings_text = _first_value(_findings_text(img.get("findings")), img.get("description"), "")
            events.append({
                "date": img_date,
                "type": "imaging",
                "title": f"{img.get('modality', 'Study')} — {img.get('body_region', '')}",
                "detail": findings_text,
                "modality": img.get("modality"),
                "body_region": img.get("body_region"),
                "description": img.get("description"),
                "findings": findings_text,
                "provider": provider,
                "facility": img.get("facility"),
                **_provenance_fields(img),
            })

    for symptom in timeline.get("symptoms", []):
        for ep in symptom.get("episodes", []):
            ep_date = _iso_date(ep.get("episode_date"))
            if ep_date:
                sev = (ep.get("intensity") or "mid").upper()
                tod = ep.get("time_of_day") or ""
                tod_label = f" — {tod}" if tod else ""
                detail = ep.get("description") or ""
                events.append({
                    "date": ep_date,
                    "type": "symptom",
                    "title": f"{symptom.get('symptom_name', 'Symptom')} ({sev}){tod_label}",
                    "detail": detail,
                    "symptom_name": symptom.get("symptom_name"),
                    "intensity": ep.get("intensity"),
                    "time_of_day": ep.get("time_of_day"),
                    "description": ep.get("description"),
                    "triggers": ep.get("triggers"),
                    "duration": ep.get("duration"),
                })

    for note in timeline.get("notes", []):
        note_date = _iso_date(_first_value(note.get("note_date"), note.get("date")))
        if not note_date:
            continue

        notes.append({
            "date": note_date,
            "provider": _first_value(note.get("provider")),
            "facility": _first_value(note.get("facility")),
            "note_type": _first_value(note.get("note_type"), "Clinical note"),
            "summary": _first_value(note.get("summary"), note.get("detail"), ""),
            **_provenance_fields(note),
        })

    for index, event in enumerate(events):
        event_date = _date_value(event.get("date"))
        provider_name = _event_provider(event)
        event["event_key"] = f"{event.get('type', 'event')}:{event.get('date', '')}:{index}"
        event["related_notes"] = _related_notes(event_date, provider_name)
        event["related_labs"] = _related_events(index, {"lab"})
        event["related_events"] = _related_events(
            index,
            {"medication", "diagnosis", "procedure", "imaging", "symptom"},
        )

    events.sort(key=lambda e: e.get("date") or "", reverse=True)
    return jsonify(events)


# ── Health Tracker API ─────────────────────────────────────────

VITALS_TYPES = {
    "blood_pressure_sys": {"label": "BP Systolic", "unit": "mmHg", "range": [70, 200]},
    "blood_pressure_dia": {"label": "BP Diastolic", "unit": "mmHg", "range": [40, 130]},
    "heart_rate":         {"label": "Heart Rate", "unit": "bpm", "range": [30, 200]},
    "blood_glucose":      {"label": "Blood Glucose", "unit": "mg/dL", "range": [30, 500]},
    "weight":             {"label": "Weight", "unit": "lbs", "range": [50, 600]},
    "temperature":        {"label": "Temperature", "unit": "\u00b0F", "range": [90, 110]},
    "oxygen_sat":         {"label": "O\u2082 Saturation", "unit": "%", "range": [70, 100]},
    "a1c":                {"label": "HbA1c", "unit": "%", "range": [3, 15]},
}


@app.route("/api/tracker/vitals-types")
def get_vitals_types():
    """Return vital sign types and their metadata, most-logged first.

    Sent as an ordered array because jsonify sorts object keys, which
    would alphabetize the tracker's dropdown.
    """
    return jsonify([
        {"key": key, **meta} for key, meta in VITALS_TYPES.items()
    ])


@app.route("/api/tracker/entries")
def get_tracker_entries():
    """Get all vitals log entries, optionally filtered by type."""
    if not _profile_data:
        return jsonify([])

    entries = _profile_data.get("vitals_log", [])
    vital_type = request.args.get("type")
    if vital_type:
        entries = [e for e in entries if e.get("vital_type") == vital_type]

    # Sort newest first
    entries = sorted(entries, key=lambda e: e.get("timestamp", ""), reverse=True)

    limit = request.args.get("limit", type=int)
    if limit:
        entries = entries[:limit]

    return jsonify(entries)


@app.route("/api/tracker/log", methods=["POST"])
def log_vital():
    """Log a new vital sign entry."""
    global _profile_data

    if not _profile_data:
        return jsonify({"error": "No profile loaded"}), 400

    data = request.get_json()
    vital_type = data.get("vital_type", "")
    value = data.get("value")
    timestamp = data.get("timestamp") or time.strftime("%Y-%m-%dT%H:%M:%S")
    notes = data.get("notes", "")

    if vital_type not in VITALS_TYPES:
        return jsonify({"error": f"Unknown vital type: {vital_type}"}), 400

    if value is None:
        return jsonify({"error": "Value is required"}), 400

    try:
        value = float(value)
    except (TypeError, ValueError):
        return jsonify({"error": "Value must be a number"}), 400

    vt = VITALS_TYPES[vital_type]
    if value < vt["range"][0] or value > vt["range"][1]:
        return jsonify({
            "error": f"Value {value} out of range for {vt['label']} "
                     f"({vt['range'][0]}-{vt['range'][1]} {vt['unit']})"
        }), 400

    entry = {
        "id": str(uuid.uuid4())[:8],
        "vital_type": vital_type,
        "value": value,
        "unit": vt["unit"],
        "timestamp": timestamp,
        "notes": notes,
    }

    if "vitals_log" not in _profile_data:
        _profile_data["vitals_log"] = []
    _profile_data["vitals_log"].append(entry)

    # Persist to vault
    _save_profile_to_vault()

    return jsonify({"status": "logged", "entry": entry})


@app.route("/api/tracker/delete", methods=["POST"])
def delete_vital():
    """Delete a vitals log entry by ID."""
    global _profile_data

    if not _profile_data:
        return jsonify({"error": "No profile loaded"}), 400

    data = request.get_json()
    entry_id = data.get("id")
    if not entry_id:
        return jsonify({"error": "Entry ID required"}), 400

    log = _profile_data.get("vitals_log", [])
    before = len(log)
    _profile_data["vitals_log"] = [e for e in log if e.get("id") != entry_id]
    after = len(_profile_data["vitals_log"])

    if before == after:
        return jsonify({"error": "Entry not found"}), 404

    _save_profile_to_vault()
    return jsonify({"status": "deleted"})


@app.route("/api/tracker/trends")
def get_tracker_trends():
    """Get trend data for sparklines — last N entries per vital type."""
    if not _profile_data:
        return jsonify({})

    entries = _profile_data.get("vitals_log", [])
    limit = request.args.get("limit", 30, type=int)

    trends = {}
    for vtype in VITALS_TYPES:
        typed = sorted(
            [e for e in entries if e.get("vital_type") == vtype],
            key=lambda e: e.get("timestamp", ""),
        )
        if typed:
            recent = typed[-limit:]
            values = [e.get("value") for e in recent]
            dates = [e.get("timestamp", "")[:10] for e in recent]
            latest = values[-1] if values else None
            avg = sum(values) / len(values) if values else None
            trends[vtype] = {
                "values": values,
                "dates": dates,
                "latest": latest,
                "average": round(avg, 1) if avg is not None else None,
                "count": len(typed),
                "label": VITALS_TYPES[vtype]["label"],
                "unit": VITALS_TYPES[vtype]["unit"],
            }

    return jsonify(trends)


@app.route("/api/tracker/risk-breakdown")
def get_risk_breakdown():
    """Get detailed risk score breakdown by category."""
    if not _profile_data:
        return jsonify({"score": 0, "factors": []})

    analysis = _profile_data.get("analysis", {})
    flags = analysis.get("flags", [])

    factors = []
    total = 0

    # Medication complexity
    meds = _profile_data.get("clinical_timeline", {}).get("medications", [])
    active_meds = [m for m in meds if m.get("status") in ("active", "prn", "unknown")]
    med_count = len(active_meds)
    if med_count >= 5:
        pts = min(20, (med_count - 4) * 4)
        total += pts
        factors.append({
            "category": "Polypharmacy",
            "points": pts,
            "detail": f"{med_count} active medications",
            "color": "#5a8ffc",
        })

    # Drug interactions
    ddi = analysis.get("drug_interactions", [])
    if ddi:
        pts = min(25, len(ddi) * 8)
        total += pts
        factors.append({
            "category": "Drug Interactions",
            "points": pts,
            "detail": f"{len(ddi)} interactions found",
            "color": "#f05545",
        })

    # Clinical flags by severity
    sev_counts = {"critical": 0, "high": 0, "moderate": 0, "low": 0}
    for f in flags:
        sev = (f.get("severity") or "info").lower()
        if sev in sev_counts:
            sev_counts[sev] += 1

    if sev_counts["critical"]:
        pts = sev_counts["critical"] * 25
        total += pts
        factors.append({
            "category": "Critical Flags",
            "points": pts,
            "detail": f"{sev_counts['critical']} critical findings",
            "color": "#dc2626",
        })

    if sev_counts["high"]:
        pts = sev_counts["high"] * 15
        total += pts
        factors.append({
            "category": "High-Severity Flags",
            "points": pts,
            "detail": f"{sev_counts['high']} high findings",
            "color": "#f97316",
        })

    if sev_counts["moderate"]:
        pts = sev_counts["moderate"] * 8
        total += pts
        factors.append({
            "category": "Moderate Flags",
            "points": pts,
            "detail": f"{sev_counts['moderate']} moderate findings",
            "color": "#f0c550",
        })

    # Missing monitoring
    missing = [f for f in flags if f.get("category") == "Monitoring Gap"]
    if missing:
        pts = min(15, len(missing) * 5)
        total += pts
        factors.append({
            "category": "Missing Monitoring",
            "points": pts,
            "detail": f"{len(missing)} overdue tests",
            "color": "#a07aff",
        })

    return jsonify({
        "score": min(total, 100),
        "factors": sorted(factors, key=lambda f: f["points"], reverse=True),
    })


def _save_profile_to_vault():
    """Persist the current _profile_data back to the encrypted vault."""
    if not _passphrase or not _profile_data:
        return False
    try:
        from src.encryption import EncryptedVault
        vault = EncryptedVault(DATA_DIR, _passphrase)
        vault.active_profile_id = _active_profile_id
        vault.save_profile(_profile_data)
        return True
    except Exception as e:
        logger.error(
            "Failed to save profile to vault (error_type=%s)",
            type(e).__name__,
        )
        return False


def _compute_and_persist_deep_insight(insight_type: str) -> dict:
    """Run or retrieve one local insight and durably store new results."""
    from copy import deepcopy

    from src.analysis.deep_insights import INSIGHT_FIELDS, compute_deep_insight

    force = request.args.get("refresh", "").strip().lower() in {
        "1", "true", "yes",
    }
    analysis = _profile_data.setdefault("analysis", {})
    field_name = INSIGHT_FIELDS[insight_type]
    previous_snapshot = deepcopy(analysis.get(field_name))
    previous_updated_at = _profile_data.get("updated_at")
    result, changed = compute_deep_insight(
        _profile_data,
        insight_type,
        force=force,
    )
    if changed and not _save_profile_to_vault():
        if previous_snapshot is None:
            analysis.pop(field_name, None)
        else:
            analysis[field_name] = previous_snapshot
        if previous_updated_at is None:
            _profile_data.pop("updated_at", None)
        else:
            _profile_data["updated_at"] = previous_updated_at
        raise RuntimeError("Deep insight persistence failed")
    return result


# ── Report Download ───────────────────────────────────────────

@app.route("/api/report/download")
def download_report():
    """Download the latest generated report."""
    if not REPORTS_DIR.exists():
        return jsonify({"error": "No reports generated"}), 404

    reports = sorted(REPORTS_DIR.glob("*.docx"), reverse=True)
    if not reports:
        return jsonify({"error": "No reports found"}), 404

    return send_from_directory(
        str(REPORTS_DIR),
        reports[0].name,
        as_attachment=True,
    )


def _prepare_demo_for_model(data: dict) -> dict:
    """Transform demo profile dict to match Pydantic PatientProfile schema.

    Demo data is shaped for the dashboard API (flat, human-friendly) but the
    report builder needs strict Pydantic models with provenance, enums, etc.
    """
    import copy
    data = copy.deepcopy(data)

    demo_provenance = {
        "source_file": "demo_patient.json",
        "source_page": None,
        "extraction_model": "demo",
    }

    # Category mapping for ClinicalFlag.category (FindingCategory enum)
    flag_category_map = {
        "Lab Finding": "lab_threshold",
        "Trend Analysis": "lab_threshold",
        "Vital Sign": "lab_threshold",
        "Symptom Pattern": "adverse_event",
        "Imaging Finding": "imaging_change",
        "Monitoring Gap": "screening_gap",
    }

    timeline = data.get("clinical_timeline", {})

    # Add provenance to all clinical timeline items
    for key in ("medications", "diagnoses", "procedures", "genetics"):
        for item in timeline.get(key, []):
            if "provenance" not in item:
                item["provenance"] = demo_provenance

    # Labs: rename test_name → name, add provenance
    for lab in timeline.get("labs", []):
        if "test_name" in lab and "name" not in lab:
            lab["name"] = lab.pop("test_name")
        if "provenance" not in lab:
            lab["provenance"] = demo_provenance

    # Imaging: findings string → list of ImagingFinding dicts, add provenance
    for study in timeline.get("imaging", []):
        if isinstance(study.get("findings"), str):
            study["findings"] = [{"description": study["findings"]}]
        if "provenance" not in study:
            study["provenance"] = demo_provenance

    # Analysis flags: fix category enum, add description, fix evidence
    analysis = data.get("analysis", {})
    for flag in analysis.get("flags", []):
        raw_cat = flag.get("category", "")
        flag["category"] = flag_category_map.get(raw_cat, "lab_threshold")
        if "description" not in flag:
            flag["description"] = flag.get("title", "")
        if isinstance(flag.get("evidence"), list):
            flag["evidence"] = [
                e.get("value", str(e)) if isinstance(e, dict) else str(e)
                for e in flag["evidence"]
            ]

    # Drug interactions: add description + source from existing fields
    for interaction in analysis.get("drug_interactions", []):
        if "description" not in interaction:
            interaction["description"] = interaction.get("mechanism", "")
        if "source" not in interaction:
            interaction["source"] = interaction.get("evidence_source", "Clinical database")

    # Community insights: add required fields
    for insight in analysis.get("community_insights", []):
        if "subreddit" not in insight:
            insight["subreddit"] = insight.get("source", "r/medicine")
        if "description" not in insight:
            insight["description"] = insight.get("summary", insight.get("title", ""))
        if "upvote_count" not in insight:
            insight["upvote_count"] = 0

    # Questions for doctor: convert dicts to strings
    raw_questions = analysis.get("questions_for_doctor", [])
    analysis["questions_for_doctor"] = [
        q["question"] if isinstance(q, dict) else str(q)
        for q in raw_questions
    ]

    return data


@app.route("/api/report/generate", methods=["POST"])
def generate_report():
    """Generate a new report from current profile."""
    if not _profile_data:
        return jsonify({"error": "No profile loaded"}), 400

    try:
        from copy import deepcopy

        from src.analysis.deep_insights import compute_all_deep_insights
        from src.models import PatientProfile
        from src.report.builder import ReportBuilder

        previous_analysis = deepcopy(_profile_data.get("analysis"))
        previous_updated_at = _profile_data.get("updated_at")
        changed, insight_errors = compute_all_deep_insights(_profile_data)
        if changed and not _save_profile_to_vault():
            if previous_analysis is None:
                _profile_data.pop("analysis", None)
            else:
                _profile_data["analysis"] = previous_analysis
            if previous_updated_at is None:
                _profile_data.pop("updated_at", None)
            else:
                _profile_data["updated_at"] = previous_updated_at
            return jsonify({"error": "Deep insight persistence failed"}), 500
        if insight_errors:
            logger.warning(
                "Report generated with unavailable deep insights (types=%s)",
                ",".join(sorted(insight_errors)),
            )

        prepared = _prepare_demo_for_model(_profile_data)
        profile = PatientProfile.model_validate(prepared)
        builder = ReportBuilder()

        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        output_path = REPORTS_DIR / f"clinical_report_{int(time.time())}.docx"

        builder.generate(profile, output_path)
        return jsonify({"status": "generated", "path": str(output_path)})

    except Exception as e:
        logger.error("Report generation failed (error_type=%s)", type(e).__name__)
        return jsonify({"error": str(e)}), 500


# ── Symptom Patterns ───────────────────────────────────────────

@app.route("/api/symptom-patterns")
def symptom_patterns():
    """Analyze symptom patterns over time."""
    if not _passphrase:
        return jsonify({"error": "Vault not unlocked"}), 401

    profile = _profile_data or {}
    timeline = profile.get("clinical_timeline", {})
    symptoms = timeline.get("symptoms", [])
    medications = timeline.get("medications", [])

    try:
        from src.analysis.symptom_monitor import SymptomPatternMonitor

        monitor = SymptomPatternMonitor()
        result = monitor.analyze(symptoms, medications)
        return jsonify(result)

    except Exception as e:
        logger.error("Symptom-pattern analysis failed (error_type=%s)", type(e).__name__)
        return jsonify({"error": str(e)}), 500


# ── Symptom Analytics ──────────────────────────────────────────

@app.route("/api/symptom-analytics")
def symptom_analytics():
    """Deep symptom analytics for D3 visualizations."""
    if not _passphrase:
        return jsonify({"error": "Vault not unlocked"}), 401

    profile = _profile_data or {}
    timeline = profile.get("clinical_timeline", {})
    symptoms = timeline.get("symptoms", [])
    medications = timeline.get("medications", [])

    try:
        from src.analysis.symptom_analytics import SymptomAnalytics

        engine = SymptomAnalytics()
        result = engine.analyze(symptoms, medications)
        return jsonify(result)

    except Exception as e:
        logger.error("Symptom analytics failed (error_type=%s)", type(e).__name__)
        return jsonify({"error": str(e)}), 500


@app.route("/api/symptom-analytics/<symptom_id>")
def symptom_analytics_single(symptom_id):
    """Detailed analytics for one symptom."""
    if not _passphrase:
        return jsonify({"error": "Vault not unlocked"}), 401

    profile = _profile_data or {}
    timeline = profile.get("clinical_timeline", {})
    symptoms = timeline.get("symptoms", [])

    target = None
    for s in symptoms:
        if s.get("symptom_id") == symptom_id:
            target = s
            break

    if not target:
        return jsonify({"error": "Symptom not found"}), 404

    try:
        from src.analysis.symptom_analytics import SymptomAnalytics

        engine = SymptomAnalytics()
        result = engine.analyze_single(target)
        return jsonify(result)

    except Exception as e:
        logger.error("Single-symptom analytics failed (error_type=%s)", type(e).__name__)
        return jsonify({"error": str(e)}), 500


@app.route("/api/symptom-analytics/insights", methods=["POST"])
def symptom_analytics_insights():
    """AI-powered qualitative insights from symptom descriptions."""
    if not _passphrase:
        return jsonify({"error": "Vault not unlocked"}), 401

    profile = _profile_data or {}
    timeline = profile.get("clinical_timeline", {})
    symptoms = timeline.get("symptoms", [])

    try:
        from src.analysis.symptom_analytics import SymptomAnalytics

        engine = SymptomAnalytics()
        result = engine.generate_ai_insights(symptoms, profile_data=profile)
        return jsonify(result)

    except Exception as e:
        logger.error("Symptom AI insights failed (error_type=%s)", type(e).__name__)
        return jsonify({"error": str(e)}), 500


# ── Visit Prep ─────────────────────────────────────────────────

@app.route("/api/visit-prep", methods=["POST"])
def visit_prep():
    """Generate visit prep sections as JSON for on-screen display."""
    if not _passphrase:
        return jsonify({"error": "Vault not unlocked"}), 401

    profile = _profile_data or {}

    try:
        from src.analysis.visit_prep import VisitPrepGenerator

        generator = VisitPrepGenerator()
        result = generator.generate(profile)
        return jsonify(result)

    except Exception as e:
        logger.error("Visit prep failed (error_type=%s)", type(e).__name__)
        return jsonify({"error": str(e)}), 500


@app.route("/api/visit-prep/download")
def visit_prep_download():
    """Generate and download visit prep as a Word document."""
    if not _passphrase:
        return jsonify({"error": "Vault not unlocked"}), 401

    profile = _profile_data or {}

    try:
        from src.analysis.visit_prep import VisitPrepGenerator

        generator = VisitPrepGenerator()
        sections = generator.generate(profile)

        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        output_path = REPORTS_DIR / f"visit_prep_{int(time.time())}.docx"
        generator.generate_docx(sections, output_path)

        return send_from_directory(
            str(REPORTS_DIR),
            output_path.name,
            as_attachment=True,
        )

    except Exception as e:
        logger.error("Visit prep download failed (error_type=%s)", type(e).__name__)
        return jsonify({"error": str(e)}), 500


# ── Chat (RAG) ────────────────────────────────────────────────

@app.route("/api/chat", methods=["POST"])
def chat():
    """Handle profile-grounded chat using a local assistant model."""
    if not _profile_data:
        return jsonify({"error": "No profile loaded"}), 400

    data = request.get_json()
    user_message = data.get("message", "")

    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    response = _generate_chat_response(user_message)
    return jsonify({"response": response})


@app.route("/api/body-translation", methods=["POST"])
def body_translation():
    """Generate a plain-English explanation of organ findings for the Body Map.

    Takes a body region and list of clinical findings, returns a patient-friendly
    explanation suitable for a non-technical user (~60 year old).
    """
    data = request.get_json()
    region = data.get("region", "")
    findings = data.get("findings", [])

    if not findings:
        return jsonify({"error": "No findings to explain"}), 400

    # Build the explanation prompt
    findings_text = ", ".join(findings)
    region_name = region.replace("-", " ").title()

    prompt = (
        f"You are a patient health educator. A patient has the following clinical "
        f"findings in their {region_name} region: {findings_text}.\n\n"
        f"Explain in plain, simple English (reading level: 6th grade) what these "
        f"findings mean for the patient's body. Use analogies if helpful. "
        f"Be compassionate but honest. Do NOT diagnose or prescribe treatment. "
        f"Keep your explanation to 3-4 sentences.\n\n"
        f"Also provide 2-3 specific questions the patient should ask their doctor "
        f"about these findings. Return them as a JSON object with keys "
        f"'explanation' (string) and 'action_items' (array of strings)."
    )

    explanation = _generate_body_translation(prompt, region_name, findings)
    return jsonify(explanation)


@app.route("/api/snowball-diagnoses", methods=["POST"])
def snowball_diagnoses():
    """Run the Snowball Differential Diagnostician.

    Collects all patient findings from the loaded profile and runs
    the graph-theory engine to produce ranked differential diagnoses
    with a D3-compatible node/edge structure.
    """
    if not _profile_data:
        return jsonify({"nodes": [], "edges": [], "ranked_conditions": []})

    try:
        return jsonify(_compute_and_persist_deep_insight("snowball"))

    except Exception as e:
        logger.error(
            "Snowball analysis failed (error_type=%s)",
            type(e).__name__,
        )
        return jsonify({
            "nodes": [],
            "edges": [],
            "ranked_conditions": [],
            "error": "Snowball analysis unavailable",
        }), 500


# ── Symptom Tracking API ─────────────────────────────────────

def _fuzzy_symptom_match(name: str, symptoms: list) -> dict | None:
    """Find an archived symptom that fuzzy-matches `name`.

    Uses normalized Levenshtein distance. Returns the best match above
    80% similarity, or None. Handles typos, extra spaces, plural differences.
    """
    def _normalise(s):
        import re
        return re.sub(r'\s+', ' ', s.lower().strip())

    def _levenshtein(a, b):
        if len(a) < len(b):
            return _levenshtein(b, a)
        if not b:
            return len(a)
        prev = list(range(len(b) + 1))
        for i, ca in enumerate(a):
            curr = [i + 1]
            for j, cb in enumerate(b):
                cost = 0 if ca == cb else 1
                curr.append(min(curr[j] + 1, prev[j + 1] + 1, prev[j] + cost))
            prev = curr
        return prev[-1]

    query = _normalise(name)
    if not query:
        return None

    best_match = None
    best_score = 0.0

    for s in symptoms:
        if not s.get("archived"):
            continue
        candidate = _normalise(s.get("symptom_name", ""))
        if not candidate:
            continue

        max_len = max(len(query), len(candidate))
        if max_len == 0:
            continue
        dist = _levenshtein(query, candidate)
        similarity = 1.0 - (dist / max_len)

        if similarity > best_score:
            best_score = similarity
            best_match = s

    if best_match and best_score >= 0.75:
        return best_match
    return None


def _save_symptoms_to_vault():
    """Persist current symptoms back to the encrypted vault."""
    if not _passphrase or not _profile_data:
        return
    try:
        from src.encryption import EncryptedVault
        vault = EncryptedVault(DATA_DIR, _passphrase)
        vault.save_profile(_profile_data)
    except Exception as e:
        logger.error(
            "Failed to save symptoms to vault (error_type=%s)",
            type(e).__name__,
        )


def _compute_counter_stats(symptom: dict) -> list[dict]:
    """Compute aggregate statistics for each counter definition."""
    stats = []
    for counter in symptom.get("counter_definitions", []):
        cid = counter["counter_id"]
        claim = counter["doctor_claim"]
        mtype = counter["measure_type"]

        values = []
        for ep in symptom.get("episodes", []):
            cv = ep.get("counter_values", {})
            if cid in cv and cv[cid] is not None:
                values.append(cv[cid])

        stat = {
            "counter_id": cid,
            "doctor_claim": claim,
            "measure_type": mtype,
            "measure_label": counter.get("measure_label"),
            "archived": counter.get("archived", False),
            "total_episodes": len(symptom.get("episodes", [])),
            "episodes_tracked": len(values),
        }

        if mtype == "scale" and values:
            numeric = [v for v in values if isinstance(v, (int, float))]
            if numeric:
                stat["average"] = round(sum(numeric) / len(numeric), 1)
                stat["min"] = min(numeric)
                stat["max"] = max(numeric)
        elif mtype == "yes_no" and values:
            yes_count = sum(1 for v in values if v is True)
            stat["yes_count"] = yes_count
            stat["no_count"] = len(values) - yes_count
            stat["yes_percent"] = round(yes_count / len(values) * 100)

        stats.append(stat)
    return stats


@app.route("/api/symptoms")
def get_symptoms():
    """Return all symptom categories with episodes, counters, and computed stats."""
    if not _profile_data:
        return jsonify([])

    timeline = _profile_data.get("clinical_timeline", {})
    symptoms = timeline.get("symptoms", [])

    result = []
    for s in symptoms:
        entry = dict(s)
        entry["counter_stats"] = _compute_counter_stats(s)
        entry["episode_count"] = len(s.get("episodes", []))
        result.append(entry)

    return jsonify(result)


@app.route("/api/symptoms", methods=["POST"])
def create_symptom():
    """Create a new symptom category from the setup wizard."""
    global _profile_data

    if not _passphrase:
        return jsonify({"error": "Vault not unlocked"}), 401

    data = request.get_json()
    name = (data.get("symptom_name") or "").strip()
    if not name:
        return jsonify({"error": "Symptom name is required"}), 400

    # Initialise profile if needed
    if not _profile_data:
        _profile_data = {"clinical_timeline": {"symptoms": []}}
    timeline = _profile_data.setdefault("clinical_timeline", {})
    symptoms = timeline.setdefault("symptoms", [])

    # ── Smart restore: check if name fuzzy-matches an archived symptom ──
    archived_match = _fuzzy_symptom_match(name, symptoms)
    if archived_match:
        archived_match["archived"] = False
        _save_symptoms_to_vault()
        result = dict(archived_match)
        result["restored"] = True
        result["restored_name"] = archived_match["symptom_name"]
        return jsonify(result), 200

    # ── Exact-name duplicate guard (active symptoms) ──
    name_lower = name.lower().strip()
    for s in symptoms:
        if not s.get("archived") and (s.get("symptom_name") or "").lower().strip() == name_lower:
            return jsonify({"error": "A symptom with that name already exists", "existing_id": s["symptom_id"]}), 409

    import uuid as _uuid
    from datetime import datetime as _dt

    new_symptom = {
        "symptom_id": str(_uuid.uuid4()),
        "symptom_name": name,
        "episodes": [],
        "counter_definitions": [],
        "date_created": _dt.now().isoformat(),
    }

    # Optional counter from wizard card 2+3
    counter_data = data.get("counter")
    if counter_data and counter_data.get("doctor_claim"):
        claim = counter_data["doctor_claim"].strip()
        mtype = counter_data.get("measure_type", "scale")
        label = counter_data.get("measure_label") or claim.replace("_", " ").title() + " level"
        new_symptom["counter_definitions"].append({
            "counter_id": str(_uuid.uuid4()),
            "doctor_claim": claim,
            "measure_type": mtype,
            "measure_label": label,
            "date_added": _dt.now().isoformat(),
            "date_archived": None,
            "archived": False,
        })

    symptoms.append(new_symptom)
    _save_symptoms_to_vault()

    return jsonify(new_symptom), 201


@app.route("/api/symptoms/check-archived", methods=["POST"])
def check_archived_symptom():
    """Check if a name fuzzy-matches any archived symptom. Used by wizard for live hints."""
    if not _passphrase or not _profile_data:
        return jsonify({"match": None})

    data = request.get_json()
    name = (data.get("name") or "").strip()
    if not name or len(name) < 3:
        return jsonify({"match": None})

    timeline = _profile_data.get("clinical_timeline", {})
    symptoms = timeline.get("symptoms", [])
    match = _fuzzy_symptom_match(name, symptoms)
    if match:
        return jsonify({"match": {
            "symptom_id": match["symptom_id"],
            "symptom_name": match["symptom_name"],
            "episode_count": len(match.get("episodes", [])),
        }})
    return jsonify({"match": None})


@app.route("/api/symptoms/<symptom_id>", methods=["DELETE"])
def delete_symptom(symptom_id):
    """Remove an entire symptom category."""
    global _profile_data

    if not _passphrase or not _profile_data:
        return jsonify({"error": "Vault not unlocked"}), 401

    timeline = _profile_data.get("clinical_timeline", {})
    symptoms = timeline.get("symptoms", [])
    before = len(symptoms)
    timeline["symptoms"] = [s for s in symptoms if s.get("symptom_id") != symptom_id]

    if len(timeline["symptoms"]) == before:
        return jsonify({"error": "Symptom not found"}), 404

    _save_symptoms_to_vault()
    return jsonify({"status": "deleted"})


@app.route("/api/symptoms/<symptom_id>/archive", methods=["PATCH"])
def toggle_archive_symptom(symptom_id):
    """Toggle archived state on a symptom. Data is kept, just hidden from main view."""
    global _profile_data

    if not _passphrase or not _profile_data:
        return jsonify({"error": "Vault not unlocked"}), 401

    timeline = _profile_data.get("clinical_timeline", {})
    for s in timeline.get("symptoms", []):
        if s.get("symptom_id") == symptom_id:
            s["archived"] = not s.get("archived", False)
            _save_symptoms_to_vault()
            return jsonify({"symptom_id": symptom_id, "archived": s["archived"]})

    return jsonify({"error": "Symptom not found"}), 404


@app.route("/api/symptoms/<symptom_id>/episodes", methods=["POST"])
def add_episode(symptom_id):
    """Add an episode to a symptom, with optional counter values."""
    global _profile_data

    if not _passphrase or not _profile_data:
        return jsonify({"error": "Vault not unlocked"}), 401

    timeline = _profile_data.get("clinical_timeline", {})
    symptom = None
    for s in timeline.get("symptoms", []):
        if s.get("symptom_id") == symptom_id:
            symptom = s
            break

    if not symptom:
        return jsonify({"error": "Symptom not found"}), 404

    data = request.get_json()
    import uuid as _uuid
    from datetime import datetime as _dt

    episode = {
        "episode_id": str(_uuid.uuid4()),
        "episode_date": data.get("episode_date"),
        "time_of_day": data.get("time_of_day"),
        "intensity": data.get("intensity", "mid"),
        "description": data.get("description"),
        "duration": data.get("duration"),
        "triggers": data.get("triggers"),
        "end_date": data.get("end_date"),
        "resolution_notes": data.get("resolution_notes"),
        "linked_medication_id": data.get("linked_medication_id"),
        "counter_values": data.get("counter_values", {}),
        "date_logged": _dt.now().isoformat(),
    }

    symptom.setdefault("episodes", []).append(episode)
    _save_symptoms_to_vault()

    return jsonify(episode), 201


@app.route("/api/symptoms/<symptom_id>/episodes/<episode_id>", methods=["DELETE"])
def delete_episode(symptom_id, episode_id):
    """Remove an episode from a symptom."""
    global _profile_data

    if not _passphrase or not _profile_data:
        return jsonify({"error": "Vault not unlocked"}), 401

    timeline = _profile_data.get("clinical_timeline", {})
    symptom = None
    for s in timeline.get("symptoms", []):
        if s.get("symptom_id") == symptom_id:
            symptom = s
            break

    if not symptom:
        return jsonify({"error": "Symptom not found"}), 404

    episodes = symptom.get("episodes", [])
    before = len(episodes)
    symptom["episodes"] = [e for e in episodes if e.get("episode_id") != episode_id]

    if len(symptom["episodes"]) == before:
        return jsonify({"error": "Episode not found"}), 404

    _save_symptoms_to_vault()
    return jsonify({"status": "deleted"})


@app.route("/api/symptoms/<symptom_id>/counter", methods=["POST"])
def add_counter(symptom_id):
    """Add a new counter definition to a symptom."""
    global _profile_data

    if not _passphrase or not _profile_data:
        return jsonify({"error": "Vault not unlocked"}), 401

    timeline = _profile_data.get("clinical_timeline", {})
    symptom = None
    for s in timeline.get("symptoms", []):
        if s.get("symptom_id") == symptom_id:
            symptom = s
            break

    if not symptom:
        return jsonify({"error": "Symptom not found"}), 404

    data = request.get_json()
    claim = (data.get("doctor_claim") or "").strip()
    if not claim:
        return jsonify({"error": "Doctor claim is required"}), 400

    import uuid as _uuid
    from datetime import datetime as _dt

    mtype = data.get("measure_type", "scale")
    label = data.get("measure_label") or claim.replace("_", " ").title() + " level"

    counter = {
        "counter_id": str(_uuid.uuid4()),
        "doctor_claim": claim,
        "measure_type": mtype,
        "measure_label": label,
        "date_added": _dt.now().isoformat(),
        "date_archived": None,
        "archived": False,
    }

    symptom.setdefault("counter_definitions", []).append(counter)
    _save_symptoms_to_vault()

    return jsonify(counter), 201


@app.route("/api/symptoms/<symptom_id>/counter/<counter_id>", methods=["PUT"])
def toggle_counter_archive(symptom_id, counter_id):
    """Archive or unarchive a counter definition."""
    global _profile_data

    if not _passphrase or not _profile_data:
        return jsonify({"error": "Vault not unlocked"}), 401

    timeline = _profile_data.get("clinical_timeline", {})
    symptom = None
    for s in timeline.get("symptoms", []):
        if s.get("symptom_id") == symptom_id:
            symptom = s
            break

    if not symptom:
        return jsonify({"error": "Symptom not found"}), 404

    counter = None
    for c in symptom.get("counter_definitions", []):
        if c.get("counter_id") == counter_id:
            counter = c
            break

    if not counter:
        return jsonify({"error": "Counter not found"}), 404

    from datetime import datetime as _dt

    counter["archived"] = not counter.get("archived", False)
    counter["date_archived"] = _dt.now().isoformat() if counter["archived"] else None
    _save_symptoms_to_vault()

    return jsonify(counter)


# ── Active Medications ────────────────────────────────────────

@app.route("/api/medications/active")
def active_medications():
    """Return list of active medication names for UI dropdowns."""
    if not _passphrase and not _profile_data:
        return jsonify({"error": "No data loaded"}), 401

    profile = _profile_data or {}
    timeline = profile.get("clinical_timeline", {})
    medications = timeline.get("medications", [])

    active = []
    for med in medications:
        status = (med.get("status") or "unknown").lower()
        if status in ("active", "unknown"):
            name = med.get("name", "")
            if name and name not in active:
                active.append(name)

    return jsonify(active)


# ── Biomarker Cascades ────────────────────────────────────────

# ── Predictive Trajectory Forecasting ─────────────────────────

@app.route("/api/trajectories")
def trajectories():
    """Analyze lab trends and project future values."""
    if not _passphrase and not _profile_data:
        return jsonify({"error": "No data loaded"}), 401

    try:
        return jsonify(_compute_and_persist_deep_insight("trajectories"))

    except Exception as e:
        logger.error(
            "Trajectory analysis failed (error_type=%s)",
            type(e).__name__,
        )
        return jsonify({"error": "Trajectory analysis unavailable"}), 500


@app.route("/api/trajectories/investigate", methods=["POST"])
def trajectories_investigate():
    """Investigate what happened before an anomalous lab value."""
    if not _passphrase and not _profile_data:
        return jsonify({"error": "No data loaded"}), 401

    profile = _profile_data or {}

    body = request.get_json(silent=True) or {}
    test_name = body.get("test_name")
    anomaly_date = body.get("anomaly_date")

    if not test_name or not anomaly_date:
        return jsonify({"error": "test_name and anomaly_date are required"}), 400

    try:
        from src.analysis.anomaly_investigator import AnomalyInvestigator

        investigator = AnomalyInvestigator()
        result = investigator.investigate(
            anomaly_date=anomaly_date,
            test_name=test_name,
            profile_data=profile,
        )
        return jsonify(result)

    except Exception as e:
        logger.error("Anomaly investigation failed (error_type=%s)", type(e).__name__)
        return jsonify({"error": str(e)}), 500


# ── Symptom Landscape ─────────────────────────────────────────

@app.route("/api/symptom-landscape")
def symptom_landscape():
    """Return symptoms classified by body system with temporal clusters."""
    if not _profile_data:
        return jsonify({
            "by_body_system": {},
            "medications": [],
            "temporal_clusters": [],
            "unattributed": [],
            "summary": {
                "total_symptoms": 0,
                "total_episodes": 0,
                "body_systems_involved": 0,
                "unattributed_count": 0,
                "cluster_count": 0,
            },
        })

    try:
        from src.analysis.symptom_classifier import SymptomClassifier
        from src.analysis.symptom_analytics import SymptomAnalytics

        timeline = _profile_data.get("clinical_timeline", {})
        symptoms = timeline.get("symptoms", [])
        medications = timeline.get("medications", [])

        # Classify symptoms into body systems
        classifier = SymptomClassifier()
        by_body_system = classifier.classify_all(symptoms)

        # Build per-symptom response with body_system and linked_medication
        by_system_response = {}
        all_classified_symptoms = []
        for system, symptom_list in by_body_system.items():
            system_entries = []
            for s in symptom_list:
                episodes = []
                for ep in s.get("episodes", []):
                    episodes.append({
                        "episode_id": ep.get("episode_id", ""),
                        "episode_date": str(ep.get("episode_date", "")) if ep.get("episode_date") else None,
                        "intensity": ep.get("intensity", "mid"),
                        "description": ep.get("description"),
                        "time_of_day": ep.get("time_of_day"),
                        "duration": ep.get("duration"),
                        "triggers": ep.get("triggers"),
                        "end_date": str(ep.get("end_date", "")) if ep.get("end_date") else None,
                        "resolution_notes": ep.get("resolution_notes"),
                        "linked_medication_id": ep.get("linked_medication_id"),
                    })
                # Check if any episode has a linked medication
                linked_med = None
                for ep in s.get("episodes", []):
                    med_id = ep.get("linked_medication_id")
                    if med_id:
                        linked_med = med_id
                        break

                entry = {
                    "symptom_name": s.get("symptom_name", ""),
                    "symptom_id": s.get("symptom_id", ""),
                    "body_system": system,
                    "episodes": episodes,
                    "episode_count": len(episodes),
                    "linked_medication": linked_med,
                }
                system_entries.append(entry)
                all_classified_symptoms.append(entry)
            by_system_response[system] = system_entries

        # Medication bars for context
        med_colors = ["#3b82f6", "#f97316", "#a78bfa", "#ec4899", "#10b981", "#f0c550"]
        med_bars = []
        for i, med in enumerate(medications):
            med_dict = med if isinstance(med, dict) else {}
            if hasattr(med, "model_dump"):
                med_dict = med.model_dump()
            elif hasattr(med, "__dict__"):
                med_dict = med.__dict__

            start = med_dict.get("start_date")
            end = med_dict.get("end_date")
            name = med_dict.get("name", "Unknown")
            status = med_dict.get("status", "unknown")
            if hasattr(status, "value"):
                status = status.value

            med_bars.append({
                "name": name,
                "start_date": str(start) if start else None,
                "end_date": str(end) if end else None,
                "status": status,
                "color": med_colors[i % len(med_colors)],
            })

        # Temporal cluster detection
        # Enrich symptoms with body_system before passing to cluster detection
        enriched_symptoms = []
        for system, symptom_list in by_body_system.items():
            for s in symptom_list:
                enriched = dict(s)
                enriched["body_system"] = system
                enriched_symptoms.append(enriched)

        analytics = SymptomAnalytics()
        window_days = int(request.args.get("window_days", 14))
        clusters = analytics.detect_temporal_clusters(enriched_symptoms, window_days)

        # Unattributed symptoms (no linked_medication_id on any episode)
        unattributed = []
        for s in all_classified_symptoms:
            has_attribution = False
            for ep in s.get("episodes", []):
                if ep.get("linked_medication_id"):
                    has_attribution = True
                    break
            if not has_attribution and s.get("episode_count", 0) > 0:
                unattributed.append({
                    "symptom_name": s["symptom_name"],
                    "body_system": s["body_system"],
                    "episode_count": s["episode_count"],
                })

        # Summary stats
        total_symptoms = sum(len(v) for v in by_system_response.values())
        total_episodes = sum(
            s.get("episode_count", 0)
            for entries in by_system_response.values()
            for s in entries
        )

        result = {
            "by_body_system": by_system_response,
            "medications": med_bars,
            "temporal_clusters": clusters,
            "unattributed": unattributed,
            "summary": {
                "total_symptoms": total_symptoms,
                "total_episodes": total_episodes,
                "body_systems_involved": len(by_system_response),
                "unattributed_count": len(unattributed),
                "cluster_count": len(clusters),
            },
        }

        return jsonify(result)

    except Exception as e:
        logger.error("Symptom-landscape analysis failed (error_type=%s)", type(e).__name__)
        return jsonify({"error": str(e)}), 500


# ── Treatment Response Analysis ──────────────────────────────────

@app.route("/api/treatment-response")
def treatment_response():
    """Per-medication scorecard: lab effectiveness + tolerability + conversation guide."""
    if not _passphrase and not _profile_data:
        return jsonify({"error": "No data loaded"}), 401

    profile = _profile_data or {}

    try:
        from src.analysis.treatment_response import TreatmentResponseAnalyzer

        timeline = profile.get("clinical_timeline", {})
        medications = timeline.get("medications", [])
        labs = timeline.get("labs", [])
        symptoms = timeline.get("symptoms", [])
        genetics = timeline.get("genetics", [])

        analyzer = TreatmentResponseAnalyzer()
        result = analyzer.analyze(medications, labs, symptoms, genetics)
        return jsonify(result)

    except Exception as e:
        logger.error("Treatment-response analysis failed (error_type=%s)", type(e).__name__)
        return jsonify({"error": str(e)}), 500


# ── Drug-Drug Interaction Timeline ───────────────────────────────

@app.route("/api/interaction-timeline")
def interaction_timeline():
    """Analyze drug interaction overlap zones across the medication timeline."""
    if not _passphrase and not _profile_data:
        return jsonify({"error": "No data loaded"}), 401

    profile = _profile_data or {}

    try:
        from src.analysis.interaction_timeline import InteractionTimelineAnalyzer

        clinical = profile.get("clinical_timeline", {})
        analysis = profile.get("analysis", {})

        medications = clinical.get("medications", [])
        interactions = analysis.get("drug_interactions", [])
        symptoms = clinical.get("symptoms", [])
        genetics = clinical.get("genetics", [])

        analyzer = InteractionTimelineAnalyzer()
        result = analyzer.analyze(
            medications=medications,
            interactions=interactions,
            symptoms=symptoms,
            genetics=genetics,
        )
        return jsonify(result)

    except Exception as e:
        logger.error("Interaction-timeline analysis failed (error_type=%s)", type(e).__name__)
        return jsonify({"error": str(e)}), 500


@app.route("/api/biomarker-cascades", methods=["POST"])
def biomarker_cascades():
    """Analyze patient labs for biomarker cascade chains."""
    if not _passphrase and not _profile_data:
        return jsonify({"error": "No data loaded"}), 401

    try:
        return jsonify(_compute_and_persist_deep_insight("biomarker_cascades"))

    except Exception as e:
        logger.error(
            "Biomarker cascade analysis failed (error_type=%s)",
            type(e).__name__,
        )
        return jsonify({"error": "Biomarker cascade analysis unavailable"}), 500


# ── Pharmacogenomic Collision Map ─────────────────────────────

@app.route("/api/pgx-collisions", methods=["POST"])
def pgx_collisions():
    """Analyze gene-drug collisions from patient genetic data + medications."""
    if not _passphrase:
        return jsonify({"error": "Vault not unlocked"}), 401

    try:
        return jsonify(_compute_and_persist_deep_insight("pgx_collisions"))

    except Exception as e:
        logger.error(
            "PGx collision analysis failed (error_type=%s)",
            type(e).__name__,
        )
        return jsonify({"error": "PGx collision analysis unavailable"}), 500


@app.route("/api/deep-insights")
def deep_insights():
    """Retrieve all deep insights already stored in the encrypted profile."""
    if not _passphrase and not _profile_data:
        return jsonify({"error": "No data loaded"}), 401

    from src.analysis.deep_insights import persisted_deep_insights

    return jsonify(persisted_deep_insights(_profile_data or {}))


# ── Missing Negative Detection ────────────────────────────────

@app.route("/api/missing-negatives", methods=["POST"])
def missing_negatives():
    """Detect monitoring gaps: expected tests that are missing or overdue."""
    if not _passphrase:
        return jsonify({"error": "Vault not unlocked"}), 401

    profile = _profile_data or {}

    try:
        from src.analysis.missing_negatives import MissingNegativeDetector

        detector = MissingNegativeDetector()
        results = detector.analyze(profile)
        return jsonify(results)

    except Exception as e:
        logger.error("Missing-negative detection failed (error_type=%s)", type(e).__name__)
        return jsonify({"error": str(e)}), 500


def _release_local_model_memory():
    """Release Python and MPS memory after local model calls."""
    gc.collect()
    gc.collect()

    try:
        import torch

        if hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
            torch.mps.empty_cache()
    except Exception:
        pass


def _coerce_record(value) -> dict:
    """Normalize Pydantic models and plain objects into dicts."""
    if isinstance(value, dict):
        return value

    if hasattr(value, "model_dump"):
        try:
            return value.model_dump(mode="json")
        except Exception:
            return value.model_dump()

    if hasattr(value, "__dict__"):
        return dict(value.__dict__)

    return {}


def _record_name(record: dict, *keys: str) -> str:
    """Return the first non-empty display name from a clinical record."""
    for key in keys:
        value = record.get(key)
        if value:
            return str(value).strip()
    return ""


def _record_date(record: dict) -> str:
    """Return the most relevant date-like field from a clinical record."""
    for key in (
        "date",
        "study_date",
        "episode_date",
        "procedure_date",
        "start_date",
        "date_created",
        "date_diagnosed",
    ):
        value = record.get(key)
        if value:
            return str(value)
    return ""


def _latest_unique_records(records, *, name_keys: tuple[str, ...], limit: int, require_flag: bool = False) -> list[dict]:
    """Return latest unique records keyed by their display name."""
    normalized = []
    for item in records or []:
        record = _coerce_record(item)
        if not record:
            continue

        if require_flag:
            flag = str(record.get("flag") or "").strip().lower()
            if flag in {"", "normal", "n"}:
                continue

        normalized.append(record)

    normalized.sort(key=_record_date, reverse=True)

    selected = []
    seen = set()
    for record in normalized:
        name = _record_name(record, *name_keys).lower()
        if not name or name in seen:
            continue
        seen.add(name)
        selected.append(record)
        if len(selected) >= limit:
            break

    return selected


def _call_local_assistant_model(
    user_prompt: str,
    *,
    system_prompt: str,
    num_predict: int = 768,
    temperature: float = 0.2,
) -> str | None:
    """Call the local assistant model through Ollama and unload it afterward."""
    try:
        import ollama

        response = ollama.chat(
            model=LOCAL_ASSISTANT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            options={
                "temperature": temperature,
                "num_predict": num_predict,
            },
            keep_alive="0",
        )

        text = response.get("message", {}).get("content", "").strip()
        if text:
            logger.info("Local assistant response generated with %s", LOCAL_ASSISTANT_MODEL)
            return text
    except Exception as e:
        logger.warning(
            "Local assistant model unavailable (model=%s, error_type=%s)",
            LOCAL_ASSISTANT_MODEL,
            type(e).__name__,
        )
    finally:
        _release_local_model_memory()

    return None


def _parse_json_object_from_text(text: str) -> dict | None:
    """Extract the first JSON object from model text output."""
    if not text:
        return None

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    try:
        parsed = json.loads(text[start:end + 1])
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return None

    return None


def _build_chat_profile_context(profile: dict) -> str:
    """Build a compact, record-grounded summary for local chat prompts."""
    profile = _coerce_record(profile)
    demographics = _coerce_record(profile.get("demographics", {}))
    timeline = _coerce_record(profile.get("clinical_timeline", {}))
    analysis = _coerce_record(profile.get("analysis", {}))

    lines = []

    demo_parts = []
    if demographics.get("age"):
        demo_parts.append(f"age {demographics['age']}")
    if demographics.get("biological_sex"):
        demo_parts.append(f"sex {demographics['biological_sex']}")
    if demographics.get("location"):
        demo_parts.append(f"location {demographics['location']}")
    if demographics.get("bmi"):
        demo_parts.append(f"BMI {demographics['bmi']}")
    if demo_parts:
        lines.append("Demographics: " + ", ".join(demo_parts))

    diagnoses = [
        _coerce_record(item)
        for item in timeline.get("diagnoses", [])
        if str(_coerce_record(item).get("status") or "").lower() in {"active", "chronic"}
    ]
    diagnoses.sort(key=_record_date, reverse=True)
    if diagnoses:
        dx_bits = []
        for item in diagnoses[:6]:
            name = _record_name(item, "name", "diagnosis")
            severity = item.get("severity")
            if name:
                dx_bits.append(f"{name} ({severity})" if severity else name)
        if dx_bits:
            lines.append("Active diagnoses: " + "; ".join(dx_bits))

    meds = []
    for item in timeline.get("medications", []):
        record = _coerce_record(item)
        if str(record.get("status") or "").lower() not in {"active", "prn"}:
            continue
        name = _record_name(record, "name", "medication_name")
        if not name:
            continue
        bits = [name]
        if record.get("dose") or record.get("dosage"):
            bits.append(str(record.get("dose") or record.get("dosage")))
        if record.get("frequency"):
            bits.append(str(record.get("frequency")))
        if record.get("reason"):
            bits.append(f"for {record['reason']}")
        meds.append(", ".join(bits))
    if meds:
        lines.append("Active medications: " + "; ".join(meds[:8]))

    flagged_labs = _latest_unique_records(
        timeline.get("labs", []),
        name_keys=("test_name", "name"),
        limit=8,
        require_flag=True,
    )
    if flagged_labs:
        lab_bits = []
        for item in flagged_labs:
            name = _record_name(item, "test_name", "name")
            value = item.get("value")
            unit = item.get("unit")
            flag = item.get("flag")
            item_date = _record_date(item)
            detail = f"{name} {value or ''} {unit or ''}".strip()
            qualifiers = [part for part in (flag, item_date) if part]
            if qualifiers:
                detail = f"{detail} ({', '.join(str(part) for part in qualifiers)})"
            lab_bits.append(detail)
        if lab_bits:
            lines.append("Flagged labs: " + "; ".join(lab_bits))

    symptoms = []
    for item in timeline.get("symptoms", []):
        symptom = _coerce_record(item)
        name = _record_name(symptom, "symptom_name", "name")
        if not name:
            continue

        episodes = [_coerce_record(ep) for ep in symptom.get("episodes", [])]
        episodes.sort(key=_record_date, reverse=True)
        if episodes:
            latest = episodes[0]
            detail_parts = [name]
            if latest.get("intensity"):
                detail_parts.append(f"intensity {latest['intensity']}")
            if latest.get("episode_date"):
                detail_parts.append(f"latest {latest['episode_date']}")
            symptoms.append(", ".join(detail_parts))
        else:
            symptoms.append(name)
    if symptoms:
        lines.append("Recent symptoms: " + "; ".join(symptoms[:6]))

    interactions = []
    for item in analysis.get("drug_interactions", [])[:4]:
        record = _coerce_record(item)
        title = _record_name(record, "title")
        if not title:
            left = record.get("drug1") or record.get("medication_1")
            right = record.get("drug2") or record.get("medication_2")
            if left and right:
                title = f"{left} + {right}"
        if not title:
            continue
        severity = record.get("severity")
        detail = record.get("detail") or record.get("description")
        text = title
        if severity:
            text = f"{text} ({severity})"
        if detail:
            text = f"{text}: {detail}"
        interactions.append(text)
    if interactions:
        lines.append("Drug interaction alerts: " + "; ".join(interactions))

    cross_disciplinary = []
    for item in analysis.get("cross_disciplinary", [])[:4]:
        record = _coerce_record(item)
        title = _record_name(record, "title", "disease")
        detail = record.get("description") or ""
        if title:
            cross_disciplinary.append(f"{title}: {detail}".strip())
    if cross_disciplinary:
        lines.append("Cross-disciplinary findings: " + "; ".join(cross_disciplinary))

    return "\n".join(lines) if lines else "No structured patient summary available."


def _generate_body_translation(
    prompt: str, region_name: str, findings: list[str],
) -> dict:
    """Generate body translation locally, then fall back to a static explanation."""
    system_prompt = (
        "You are a patient health educator inside a local-first medical records tool. "
        "Use only the findings in the prompt. Do not claim to have searched the web. "
        "Return strict JSON with keys explanation and action_items. "
        "Keep the explanation clear, calm, and non-diagnostic."
    )

    text = _call_local_assistant_model(
        prompt,
        system_prompt=system_prompt,
        num_predict=512,
        temperature=0.1,
    )
    parsed = _parse_json_object_from_text(text or "")
    if parsed:
        return {
            "explanation": parsed.get("explanation", text),
            "action_items": parsed.get("action_items", []),
        }

    # Static fallback — no AI available
    findings_str = ", ".join(findings)
    return {
        "explanation": (
            f"Your medical records show findings in your {region_name.lower()} area: "
            f"{findings_str}. These findings were identified by your healthcare providers "
            f"across your medical records. For a detailed explanation of what each finding "
            f"means for your body, please discuss them with your doctor."
        ),
        "action_items": [
            f"Ask your doctor to explain what {findings[0]} means for your health.",
            f"Ask if any of these findings in the {region_name.lower()} require monitoring or follow-up.",
            "Ask if these findings are connected to each other or to other conditions you have.",
        ],
    }


def _simple_chat_response(message: str) -> str:
    """Deterministic fallback when the local assistant model is unavailable."""
    msg_lower = message.lower()
    timeline = _profile_data.get("clinical_timeline", {})

    if "medication" in msg_lower or "med" in msg_lower:
        meds = timeline.get("medications", [])
        active = [m for m in meds if str(m.get("status") or "").lower() in ("active", "prn")]
        if active:
            med_list = ", ".join(m["name"] for m in active)
            return f"Based on your records, your active medications are: {med_list}. Would you like details about any of these?"
        return "No active medications found in your records."

    if "lab" in msg_lower or "test" in msg_lower:
        labs = timeline.get("labs", [])
        flagged = [
            l for l in labs
            if l.get("flag") and str(l["flag"]).lower() not in ("normal", "")
        ]
        if flagged:
            lab_list = ", ".join(
                f"{l.get('test_name') or l.get('name', 'Unknown')} ({l.get('flag', '')})"
                for l in flagged[:5]
            )
            return f"Your flagged lab results include: {lab_list}. Would you like to know more about any of these?"
        return "Your lab results are all within normal range based on available records."

    if "diagnosis" in msg_lower or "condition" in msg_lower:
        dxs = timeline.get("diagnoses", [])
        active = [d for d in dxs if str(d.get("status") or "").lower() in ("active", "chronic")]
        if active:
            dx_list = ", ".join(d["name"] for d in active)
            return f"Your active conditions include: {dx_list}."
        return "No active conditions found in your records."

    return (
        "I can help you understand your medical records. Try asking about:\n"
        "• Your medications\n"
        "• Lab results and trends\n"
        "• Active conditions\n"
        "• Drug interactions\n"
        "• Cross-disciplinary connections\n\n"
        "What would you like to know?"
    )


def _generate_chat_response(message: str) -> str:
    """Answer chat questions with the local assistant model, then fall back safely."""
    profile_context = _build_chat_profile_context(_profile_data or {})
    system_prompt = (
        "You are the local clinical record assistant inside Clinical Intelligence Hub. "
        "Answer only from the patient summary you are given. "
        "Do not claim to have searched the web, reviewed literature, or seen source files beyond this summary. "
        "If the user asks for latest studies, web results, or external evidence, say that external research belongs in the research pipeline. "
        "Use plain language for a non-technical adult. "
        "Do not diagnose or prescribe. Frame next steps as questions for the clinician when appropriate. "
        "Keep answers concise and grounded."
    )
    user_prompt = (
        "PATIENT RECORD SUMMARY\n"
        f"{profile_context}\n\n"
        "USER QUESTION\n"
        f"{message}"
    )

    response = _call_local_assistant_model(
        user_prompt,
        system_prompt=system_prompt,
        num_predict=768,
        temperature=0.2,
    )
    if response:
        return response

    return _simple_chat_response(message)


# ── API Key Management ────────────────────────────────────────

@app.route("/api/keys", methods=["POST"])
def set_api_key():
    """Set an API key in the encrypted vault."""
    if not _passphrase:
        return jsonify({"error": "Vault not unlocked"}), 401

    data = request.get_json()
    service = data.get("service")
    key = data.get("key")

    if not service or not key:
        return jsonify({"error": "Service and key required"}), 400

    try:
        from src.encryption import EncryptedVault
        vault = EncryptedVault(DATA_DIR, _passphrase)
        vault.set_api_key(service, key)
        return jsonify({"status": "saved"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/keys/status")
def api_key_status():
    """Check which API keys are configured."""
    if not _passphrase:
        return jsonify({})

    try:
        from src.encryption import EncryptedVault
        vault = EncryptedVault(DATA_DIR, _passphrase)
        keys = vault.load_api_keys()
        return jsonify({
            service: bool(key) for service, key in keys.items()
        })
    except Exception:
        return jsonify({})


# ── Run Server ────────────────────────────────────────────────

def run(host: str = "127.0.0.1", port: int = 5000, debug: bool = False):
    """Start the Flask server."""
    global _passphrase, _profile_data

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # Auto-unlock from VAULT_PASSPHRASE env var (set by start.command)
    env_passphrase = os.environ.get("VAULT_PASSPHRASE")
    if env_passphrase and _passphrase is None:
        try:
            from src.encryption import EncryptedVault
            vault = EncryptedVault(DATA_DIR, env_passphrase)
            if vault.verify_passphrase():
                _passphrase = env_passphrase
                profile = vault.load_profile()
                if profile:
                    _profile_data = profile
                logger.info("Vault auto-unlocked from VAULT_PASSPHRASE")
            else:
                logger.warning("VAULT_PASSPHRASE did not match existing vault")
        except Exception as e:
            logger.warning(
                "Auto-unlock failed (error_type=%s)",
                type(e).__name__,
            )

    if _passphrase is None:
        _activate_dev_passphrase_bypass()

    should_start_worker = not debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    if should_start_worker:
        _start_environmental_sync_worker()

    logger.info(f"Starting Clinical Intelligence Hub on http://{host}:{port}")
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    port = int(os.environ.get("PORT", 5050))
    run(port=port, debug=True)
