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


@app.route("/models/<path:filename>")
def models(filename):
    """Serve 3D model files (GLB, etc.)."""
    return send_from_directory(str(STATIC_DIR / "models"), filename)


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
        vault = EncryptedVault(DATA_DIR, _passphrase)
        vault.save_profile(_profile_data)
    except Exception as e:
        logger.error("Failed to save location: %s", e)
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "saved", "location": location})


@app.route("/api/environmental")
def get_environmental():
    """Analyze environmental/geographic health risks for patient's location."""
    if not _profile_data:
        return jsonify({"location": None, "risks": [], "summary": {}})

    try:
        from src.analysis.environmental import EnvironmentalRiskEngine
        engine = EnvironmentalRiskEngine()
        result = engine.analyze(_profile_data)
        return jsonify(result)
    except Exception as e:
        logger.error("Environmental analysis failed: %s", e)
        return jsonify({"error": str(e)}), 500


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
        logger.debug("Missing negative detection in flags: %s", e)

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
        logger.debug("Environmental risk detection in flags: %s", e)

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
        logger.debug("Radiomic flag extraction in flags: %s", e)

    return jsonify(flags)


# ── Dashboard Helpers ─────────────────────────────────────

def _get_latest_labs(labs):
    """Return the most recent result for each unique lab test name."""
    latest = {}
    for lab in labs:
        name = lab.get("test_name") or lab.get("name") or "Unknown"
        date = lab.get("date") or lab.get("collected_date") or ""
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


def _get_lab_trends(labs):
    """Return labs that have 3+ data points, suitable for sparkline rendering."""
    from collections import defaultdict
    by_name = defaultdict(list)
    for lab in labs:
        name = lab.get("test_name") or lab.get("name") or "Unknown"
        value = lab.get("value")
        date = lab.get("date") or lab.get("collected_date") or ""
        if value is not None:
            try:
                numeric_val = float(str(value).replace(",", ""))
            except (ValueError, TypeError):
                continue
            by_name[name].append({
                "date": date,
                "value": numeric_val,
                "unit": lab.get("unit", ""),
                "ref_low": lab.get("reference_low"),
                "ref_high": lab.get("reference_high"),
            })
    # Only return tests with 3+ data points, sorted by date
    trends = {}
    for name, points in by_name.items():
        if len(points) >= 3:
            trends[name] = sorted(points, key=lambda p: p["date"])
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

    # Active medications
    meds = clinical.get("medications", [])
    active_meds = [m for m in meds if (m.get("status") or "").lower() != "discontinued"]

    # Active diagnoses
    diagnoses = clinical.get("diagnoses", [])

    # Symptoms count
    symptoms = clinical.get("symptoms", [])

    # Flags — use lightweight count rather than full computation
    flags = list(analysis.get("flags", []))

    # Missing negatives / monitoring gaps
    missing = [f for f in flags if f.get("category") == "Monitoring Gap"]

    # PGx collision count
    pgx_alerts = analysis.get("drug_gene_interactions", [])

    # Cross-specialty count
    cross_spec_count = len(analysis.get("cross_disciplinary", []))

    return jsonify({
        "has_data": True,
        "latest_labs": latest_labs,
        "lab_trends": lab_trends,
        "active_medications": len(active_meds),
        "diagnoses_count": len(diagnoses),
        "symptoms_count": len(symptoms),
        "flags_count": len(flags),
        "missing_tests": missing,
        "pgx_collisions": len(pgx_alerts),
        "cross_specialty_count": cross_spec_count,
        "visit_prep_items": _count_visit_prep_items(),
    })


@app.route("/api/interactions")
def get_interactions():
    """Get drug interactions."""
    if not _profile_data:
        return jsonify([])
    analysis = _profile_data.get("analysis", {})
    return jsonify(analysis.get("drug_interactions", []))


@app.route("/api/cross-disciplinary")
def get_cross_disciplinary():
    """Get cross-disciplinary connections, including cross-specialty correlations."""
    if not _profile_data:
        return jsonify([])

    analysis = _profile_data.get("analysis", {})
    connections = list(analysis.get("cross_disciplinary", []))

    # Run cross-specialty systemic disease correlation on demand
    try:
        from src.analysis.diagnostic_engine.cross_specialty import CrossSpecialtyEngine
        from src.encryption import EncryptedVault

        api_key = None
        try:
            vault = EncryptedVault(DATA_DIR, _passphrase)
            keys = vault.load_api_keys() or {}
            api_key = keys.get("gemini")
        except Exception:
            pass

        engine = CrossSpecialtyEngine(api_key=api_key)
        correlations = engine.analyze(_profile_data)

        for c in correlations:
            evidence = c.get("matched_symptoms", []) + c.get("matched_labs", [])
            hits = c.get("total_hits", 0)
            possible = c.get("total_possible", 0)
            connections.append({
                "type": c.get("type", "systemic_correlation"),
                "title": c["disease"],
                "specialties": c["specialties"],
                "severity": c.get("severity", "moderate"),
                "description": c["description"],
                "patient_data_points": evidence,
                "question_for_doctor": c.get("recommendation", ""),
                "total_hits": hits,
                "total_possible": possible,
            })
    except Exception as e:
        logger.debug("Cross-specialty correlation: %s", e)

    return jsonify(connections)


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
        logger.error("PubMed sweep failed: %s", e)
        return jsonify({"error": str(e)}), 500


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

    for symptom in timeline.get("symptoms", []):
        for ep in symptom.get("episodes", []):
            if ep.get("episode_date"):
                sev = (ep.get("severity") or "mid").upper()
                tod = ep.get("time_of_day") or ""
                tod_label = f" — {tod}" if tod else ""
                detail = ep.get("description") or ""
                events.append({
                    "date": ep["episode_date"],
                    "type": "symptom",
                    "title": f"{symptom.get('symptom_name', 'Symptom')} ({sev}){tod_label}",
                    "detail": detail,
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
        logger.error("Symptom pattern analysis failed: %s", e)
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
        logger.error("Symptom analytics failed: %s", e)
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
        logger.error("Single symptom analytics failed: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/symptom-analytics/insights", methods=["POST"])
def symptom_analytics_insights():
    """AI-powered qualitative insights from symptom descriptions."""
    if not _passphrase:
        return jsonify({"error": "Vault not unlocked"}), 401

    profile = _profile_data or {}
    timeline = profile.get("clinical_timeline", {})
    symptoms = timeline.get("symptoms", [])

    # Get Gemini key if available
    api_key = None
    try:
        from src.encryption import EncryptedVault

        vault = EncryptedVault(DATA_DIR, _passphrase)
        keys = vault.load_api_keys() or {}
        api_key = keys.get("gemini")
    except Exception:
        pass

    try:
        from src.analysis.symptom_analytics import SymptomAnalytics

        engine = SymptomAnalytics()
        result = engine.generate_ai_insights(
            symptoms, profile_data=profile, api_key=api_key
        )
        return jsonify(result)

    except Exception as e:
        logger.error("Symptom AI insights failed: %s", e)
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
        from src.encryption import EncryptedVault

        # Try to get Gemini key for narrative
        api_key = None
        try:
            vault = EncryptedVault(DATA_DIR, _passphrase)
            keys = vault.load_api_keys() or {}
            api_key = keys.get("gemini")
        except Exception:
            pass

        generator = VisitPrepGenerator(api_key=api_key)
        result = generator.generate(profile)
        return jsonify(result)

    except Exception as e:
        logger.error("Visit prep failed: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/visit-prep/download")
def visit_prep_download():
    """Generate and download visit prep as a Word document."""
    if not _passphrase:
        return jsonify({"error": "Vault not unlocked"}), 401

    profile = _profile_data or {}

    try:
        from src.analysis.visit_prep import VisitPrepGenerator
        from src.encryption import EncryptedVault

        api_key = None
        try:
            vault = EncryptedVault(DATA_DIR, _passphrase)
            keys = vault.load_api_keys() or {}
            api_key = keys.get("gemini")
        except Exception:
            pass

        generator = VisitPrepGenerator(api_key=api_key)
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
        logger.error("Visit prep download failed: %s", e)
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

    # Try Gemini first, then Ollama, then static fallback
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
        from src.analysis.snowball_engine import SnowballEngine

        # Load Gemini key + demographics for AI-enhanced matching
        api_key = None
        demographics = {}
        try:
            from src.security.vault import SecureVault
            vault = SecureVault()
            if _passphrase:
                keys = vault.load_api_keys() or {}
                api_key = keys.get("gemini")
        except Exception:
            pass

        timeline = _profile_data.get("clinical_timeline", {})
        demo = timeline.get("demographics", {})
        if demo:
            demographics = {
                "age": demo.get("age"),
                "sex": demo.get("sex"),
            }

        engine = SnowballEngine(api_key=api_key, demographics=demographics)
        graph = engine.analyze(_profile_data)
        return jsonify(graph)

    except Exception as e:
        logger.error(f"Snowball analysis failed: {e}")
        return jsonify({"nodes": [], "edges": [], "ranked_conditions": [], "error": str(e)})


# ── Symptom Tracking API ─────────────────────────────────────

def _save_symptoms_to_vault():
    """Persist current symptoms back to the encrypted vault."""
    if not _passphrase or not _profile_data:
        return
    try:
        from src.encryption import EncryptedVault
        vault = EncryptedVault(DATA_DIR, _passphrase)
        vault.save_profile(_profile_data)
    except Exception as e:
        logger.error(f"Failed to save symptoms to vault: {e}")


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
        "severity": data.get("severity", "mid"),
        "description": data.get("description"),
        "duration": data.get("duration"),
        "triggers": data.get("triggers"),
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


# ── Biomarker Cascades ────────────────────────────────────────

# ── Predictive Trajectory Forecasting ─────────────────────────

@app.route("/api/trajectories")
def trajectories():
    """Analyze lab trends and project future values."""
    if not _passphrase:
        return jsonify({"error": "Vault not unlocked"}), 401

    profile = _profile_data or {}

    try:
        from src.analysis.trajectory import TrajectoryForecaster

        forecaster = TrajectoryForecaster()
        result = forecaster.analyze(profile)
        return jsonify(result)

    except Exception as e:
        logger.error("Trajectory analysis failed: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/biomarker-cascades", methods=["POST"])
def biomarker_cascades():
    """Analyze patient labs for biomarker cascade chains."""
    if not _passphrase:
        return jsonify({"error": "Vault not unlocked"}), 401

    profile = _profile_data or {}

    try:
        from src.analysis.biomarker_cascades import BiomarkerCascadeEngine

        engine = BiomarkerCascadeEngine()
        result = engine.analyze(profile)
        return jsonify(result)

    except Exception as e:
        logger.error("Biomarker cascade analysis failed: %s", e)
        return jsonify({"error": str(e)}), 500


# ── Pharmacogenomic Collision Map ─────────────────────────────

@app.route("/api/pgx-collisions", methods=["POST"])
def pgx_collisions():
    """Analyze gene-drug collisions from patient genetic data + medications."""
    if not _passphrase:
        return jsonify({"error": "Vault not unlocked"}), 401

    profile = _profile_data or {}

    try:
        from src.analysis.diagnostic_engine.pharmacogenomics import PharmacogenomicEngine

        engine = PharmacogenomicEngine()
        result = engine.analyze(profile)
        return jsonify(result)

    except Exception as e:
        logger.error("PGx collision analysis failed: %s", e)
        return jsonify({"error": str(e)}), 500


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
        logger.error("Missing negative detection failed: %s", e)
        return jsonify({"error": str(e)}), 500


def _generate_body_translation(
    prompt: str, region_name: str, findings: list[str],
) -> dict:
    """Generate body translation via Gemini, Ollama, or static fallback."""
    # 1. Try Gemini API
    try:
        from src.encryption import EncryptedVault
        vault = EncryptedVault(DATA_DIR, _passphrase)
        keys = vault.load_api_keys()
        gemini_key = keys.get("gemini")

        if gemini_key:
            import google.generativeai as genai

            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-2.0-flash")
            response = model.generate_content(prompt)
            text = response.text

            # Try to parse JSON from response
            import re
            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                return {
                    "explanation": parsed.get("explanation", text),
                    "action_items": parsed.get("action_items", []),
                }
            return {"explanation": text, "action_items": []}
    except Exception as e:
        logger.debug(f"Gemini body translation failed: {e}")

    # 2. Try local Ollama (MedGemma or any available model)
    try:
        import requests as req

        ollama_response = req.post(
            "http://localhost:11434/api/generate",
            json={"model": "medgemma", "prompt": prompt, "stream": False},
            timeout=30,
        )
        if ollama_response.status_code == 200:
            text = ollama_response.json().get("response", "")
            import re
            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                return {
                    "explanation": parsed.get("explanation", text),
                    "action_items": parsed.get("action_items", []),
                }
            return {"explanation": text, "action_items": []}
    except Exception as e:
        logger.debug(f"Ollama body translation failed: {e}")

    # 3. Static fallback — no AI available
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
    port = int(os.environ.get("PORT", 5050))
    run(port=port, debug=True)
