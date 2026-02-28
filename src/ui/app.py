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
import shutil
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, jsonify, request, Response, send_from_directory

logger = logging.getLogger("CIH-App")

# ── App Configuration ─────────────────────────────────────────

BASE_DIR = Path(__file__).parent.parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
REPORTS_DIR = DATA_DIR / "reports"
STATIC_DIR = Path(__file__).parent / "static"

app = Flask(__name__, static_folder=str(STATIC_DIR))
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB max upload

# Global state
_pipeline_thread: threading.Thread = None
_progress_queue: queue.Queue = queue.Queue()
_passphrase: str = None
_profile_data: dict = None


# ── Static Files ──────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the main SPA."""
    return send_from_directory(str(STATIC_DIR), "index.html")


@app.route("/assets/<path:filename>")
def assets(filename):
    """Serve static assets (anatomy images, etc.)."""
    return send_from_directory(str(STATIC_DIR / "assets"), filename)


@app.route("/<path:filename>")
def static_files(filename):
    """Serve any static file."""
    return send_from_directory(str(STATIC_DIR), filename)


# ── Vault / Session ───────────────────────────────────────────

@app.route("/api/unlock", methods=["POST"])
def unlock_vault():
    """Unlock the encrypted vault with a passphrase."""
    global _passphrase, _profile_data

    data = request.get_json()
    passphrase = data.get("passphrase", "")

    if not passphrase:
        return jsonify({"error": "Passphrase is required"}), 400

    try:
        from src.encryption import EncryptedVault

        vault = EncryptedVault(DATA_DIR, passphrase)

        if not vault.verify_passphrase():
            return jsonify({"error": "Incorrect passphrase"}), 401

        _passphrase = passphrase

        # Load existing profile if available
        profile = vault.load_profile()
        if profile:
            _profile_data = profile

        return jsonify({
            "status": "unlocked",
            "has_profile": profile is not None,
        })

    except Exception as e:
        logger.error(f"Vault unlock failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/session/clear", methods=["POST"])
def clear_session():
    """Clear all patient data for a new session."""
    global _profile_data

    if not _passphrase:
        return jsonify({"error": "Vault not unlocked"}), 401

    try:
        from src.ui.pipeline import Pipeline

        pipeline = Pipeline(DATA_DIR, _passphrase)
        pipeline.clear_session()
        _profile_data = None

        # Clear upload directory
        if UPLOAD_DIR.exists():
            shutil.rmtree(UPLOAD_DIR)
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

        return jsonify({"status": "cleared"})

    except Exception as e:
        logger.error(f"Session clear failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/session/status")
def session_status():
    """Get current session status."""
    return jsonify({
        "unlocked": _passphrase is not None,
        "has_profile": _profile_data is not None,
        "pipeline_running": _pipeline_thread is not None and _pipeline_thread.is_alive(),
    })


# ── File Upload ───────────────────────────────────────────────

@app.route("/api/upload", methods=["POST"])
def upload_files():
    """Handle file upload (drag-and-drop or file picker)."""
    if not _passphrase:
        return jsonify({"error": "Vault not unlocked"}), 401

    if "files" not in request.files:
        return jsonify({"error": "No files provided"}), 400

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
    input_files = [f for f in input_files if f.is_file()]

    if not input_files:
        return jsonify({"error": "No files to analyze"}), 400

    # Clear progress queue
    while not _progress_queue.empty():
        try:
            _progress_queue.get_nowait()
        except queue.Empty:
            break

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

    try:
        from src.ui.pipeline import Pipeline

        def progress_callback(pass_name, message, percent):
            _progress_queue.put({
                "pass": pass_name,
                "message": message,
                "percent": percent,
                "timestamp": time.time(),
            })

        pipeline = Pipeline(DATA_DIR, _passphrase, progress_callback)
        profile = pipeline.run(input_files)

        _profile_data = profile.model_dump(mode="json")

    except Exception as e:
        logger.error(f"Pipeline thread failed: {e}")
        _progress_queue.put({
            "pass": "error",
            "message": f"Analysis failed: {str(e)}",
            "percent": -1,
            "timestamp": time.time(),
        })


@app.route("/api/progress")
def progress_stream():
    """Server-Sent Events stream for pipeline progress."""
    def generate():
        while True:
            try:
                event = _progress_queue.get(timeout=30)
                yield f"data: {json.dumps(event)}\n\n"

                if event.get("pass") in ("complete", "error"):
                    break

            except queue.Empty:
                # Send keepalive
                yield f"data: {json.dumps({'pass': 'heartbeat', 'message': 'waiting', 'percent': -1})}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Profile Data API ──────────────────────────────────────────

@app.route("/api/profile")
def get_profile():
    """Get the full patient profile."""
    if not _profile_data:
        return jsonify({"error": "No profile loaded"}), 404
    return jsonify(_profile_data)


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


@app.route("/api/flags")
def get_flags():
    """Get clinical flags and patterns."""
    if not _profile_data:
        return jsonify([])
    analysis = _profile_data.get("analysis", {})
    return jsonify(analysis.get("flags", []))


@app.route("/api/interactions")
def get_interactions():
    """Get drug interactions."""
    if not _profile_data:
        return jsonify([])
    analysis = _profile_data.get("analysis", {})
    return jsonify(analysis.get("drug_interactions", []))


@app.route("/api/cross-disciplinary")
def get_cross_disciplinary():
    """Get cross-disciplinary connections."""
    if not _profile_data:
        return jsonify([])
    analysis = _profile_data.get("analysis", {})
    return jsonify(analysis.get("cross_disciplinary", []))


@app.route("/api/community")
def get_community():
    """Get community insights."""
    if not _profile_data:
        return jsonify([])
    analysis = _profile_data.get("analysis", {})
    return jsonify(analysis.get("community_insights", []))


@app.route("/api/literature")
def get_literature():
    """Get literature citations."""
    if not _profile_data:
        return jsonify([])
    analysis = _profile_data.get("analysis", {})
    return jsonify(analysis.get("literature", []))


@app.route("/api/questions")
def get_questions():
    """Get questions for doctor."""
    if not _profile_data:
        return jsonify([])
    analysis = _profile_data.get("analysis", {})
    return jsonify(analysis.get("questions_for_doctor", []))


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


@app.route("/api/timeline")
def get_timeline():
    """Get all dated events for the timeline view."""
    if not _profile_data:
        return jsonify([])

    timeline = _profile_data.get("clinical_timeline", {})
    events = []

    for med in timeline.get("medications", []):
        if med.get("start_date"):
            events.append({
                "date": med["start_date"],
                "type": "medication",
                "title": f"Started {med['name']}",
                "detail": f"{med.get('dosage', '')} {med.get('frequency', '')}".strip(),
            })

    for lab in timeline.get("labs", []):
        if lab.get("test_date"):
            events.append({
                "date": lab["test_date"],
                "type": "lab",
                "title": lab["name"],
                "detail": f"{lab.get('value', lab.get('value_text', ''))} {lab.get('unit', '')} [{lab.get('flag', '')}]",
            })

    for dx in timeline.get("diagnoses", []):
        if dx.get("date_diagnosed"):
            events.append({
                "date": dx["date_diagnosed"],
                "type": "diagnosis",
                "title": dx["name"],
                "detail": dx.get("status", ""),
            })

    for proc in timeline.get("procedures", []):
        if proc.get("procedure_date"):
            events.append({
                "date": proc["procedure_date"],
                "type": "procedure",
                "title": proc["name"],
                "detail": proc.get("provider", ""),
            })

    for img in timeline.get("imaging", []):
        if img.get("study_date"):
            events.append({
                "date": img["study_date"],
                "type": "imaging",
                "title": f"{img.get('modality', 'Study')} — {img.get('body_region', '')}",
                "detail": img.get("description", ""),
            })

    events.sort(key=lambda e: e["date"], reverse=True)
    return jsonify(events)


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


@app.route("/api/report/generate", methods=["POST"])
def generate_report():
    """Generate a new report from current profile."""
    if not _profile_data or not _passphrase:
        return jsonify({"error": "No profile or vault not unlocked"}), 400

    try:
        from src.models import PatientProfile
        from src.report.builder import ReportBuilder

        profile = PatientProfile(**_profile_data)
        builder = ReportBuilder()

        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        output_path = REPORTS_DIR / f"clinical_report_{int(time.time())}.docx"

        builder.generate(profile, output_path)
        return jsonify({"status": "generated", "path": str(output_path)})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Chat (RAG) ────────────────────────────────────────────────

@app.route("/api/chat", methods=["POST"])
def chat():
    """Handle chat messages (RAG clinical assistant)."""
    if not _profile_data:
        return jsonify({"error": "No profile loaded"}), 400

    data = request.get_json()
    user_message = data.get("message", "")

    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    # Simple context-grounded response
    # In full implementation, this uses sqlite-vec for RAG retrieval
    # and Gemini for response generation
    response = _simple_chat_response(user_message)
    return jsonify({"response": response})


def _simple_chat_response(message: str) -> str:
    """
    Simple chat response using profile context.

    In the full implementation, this would:
    1. Embed the query with sentence-transformers
    2. Search sqlite-vec for relevant clinical records
    3. Build a context-grounded prompt
    4. Call Gemini 3.1 Pro Preview for the response
    """
    msg_lower = message.lower()
    timeline = _profile_data.get("clinical_timeline", {})

    if "medication" in msg_lower or "med" in msg_lower:
        meds = timeline.get("medications", [])
        active = [m for m in meds if m.get("status") in ("active", "prn")]
        if active:
            med_list = ", ".join(m["name"] for m in active)
            return f"Based on your records, your active medications are: {med_list}. Would you like details about any of these?"
        return "No active medications found in your records."

    if "lab" in msg_lower or "test" in msg_lower:
        labs = timeline.get("labs", [])
        flagged = [l for l in labs if l.get("flag") and l["flag"].lower() not in ("normal", "")]
        if flagged:
            lab_list = ", ".join(f"{l['name']} ({l.get('flag', '')})" for l in flagged[:5])
            return f"Your flagged lab results include: {lab_list}. Would you like to know more about any of these?"
        return "Your lab results are all within normal range based on available records."

    if "diagnosis" in msg_lower or "condition" in msg_lower:
        dxs = timeline.get("diagnoses", [])
        active = [d for d in dxs if d.get("status", "").lower() in ("active", "chronic")]
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
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    logger.info(f"Starting Clinical Intelligence Hub on http://{host}:{port}")
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run(debug=True)
