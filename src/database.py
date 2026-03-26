"""
Clinical Intelligence Hub — SQLite + sqlite-vec Database Layer

Responsibilities:
  - Processing state tracking (pipeline checkpoint/resume)
  - Vector storage for RAG chat (sqlite-vec)
  - PII redaction audit log
  - Monitoring alert storage

Patient profile data is stored separately as encrypted JSON (see encryption.py).
This database handles operational state that doesn't contain raw patient data.
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger("CIH-Database")


class Database:
    """SQLite database for pipeline state, vectors, and audit logs."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._initialize()

    def _get_conn(self) -> sqlite3.Connection:
        """Returns a connection, creating one if needed."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            # WAL mode for concurrent reads during pipeline writes
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def _initialize(self):
        """Creates all tables if they don't exist."""
        conn = self._get_conn()

        conn.executescript("""
            -- Pipeline processing state (checkpoint/resume)
            CREATE TABLE IF NOT EXISTS processing_state (
                file_id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                file_type TEXT NOT NULL,
                sha256_hash TEXT NOT NULL UNIQUE,
                file_size_bytes INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                current_pass TEXT,
                error_message TEXT,
                date_added TEXT NOT NULL,
                date_completed TEXT,
                page_count INTEGER
            );

            -- PII redaction audit log
            CREATE TABLE IF NOT EXISTS redaction_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_type TEXT NOT NULL,
                context TEXT,
                file_source TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );

            -- Monitoring alerts
            CREATE TABLE IF NOT EXISTS monitoring_alerts (
                alert_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                relevance_explanation TEXT NOT NULL,
                severity TEXT NOT NULL,
                url TEXT,
                date_detected TEXT NOT NULL,
                addressed INTEGER DEFAULT 0
            );

            -- Pipeline run metadata
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                run_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                files_processed INTEGER DEFAULT 0,
                files_failed INTEGER DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'running'
            );

            -- Patient profiles (identity + status; visible immediately on upload)
            CREATE TABLE IF NOT EXISTS profiles (
                profile_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'processing',
                display_name TEXT
            );

            -- Per-upload source files linked to a profile
            CREATE TABLE IF NOT EXISTS source_files (
                file_id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                sha256_hash TEXT,
                file_size_bytes INTEGER,
                date_added TEXT NOT NULL,
                FOREIGN KEY (profile_id) REFERENCES profiles(profile_id)
            );

            -- Background processing jobs
            CREATE TABLE IF NOT EXISTS processing_jobs (
                job_id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL DEFAULT 'queued',
                progress_pct INTEGER DEFAULT 0,
                FOREIGN KEY (profile_id) REFERENCES profiles(profile_id)
            );

            -- Per-file per-stage checkpoints for resumability
            CREATE TABLE IF NOT EXISTS processing_checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                file_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'completed',
                parser_version TEXT,
                artifact_json TEXT,
                saved_at TEXT NOT NULL,
                UNIQUE(job_id, file_id, stage)
            );

            -- Lightweight profile snapshots written after each meaningful stage
            CREATE TABLE IF NOT EXISTS profile_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id TEXT NOT NULL,
                snapshot_json TEXT NOT NULL,
                saved_at TEXT NOT NULL,
                FOREIGN KEY (profile_id) REFERENCES profiles(profile_id)
            );
        """)

        # Try to load sqlite-vec extension for vector search
        self._init_vector_storage(conn)

        conn.commit()
        logger.info(f"Database initialized at {self.db_path}")

    def _init_vector_storage(self, conn: sqlite3.Connection):
        """Initializes sqlite-vec for RAG chat vector storage."""
        try:
            import sqlite_vec
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)

            # Vector table for clinical record embeddings
            # Using 384 dimensions (all-MiniLM-L6-v2 output size)
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS clinical_vectors
                USING vec0(
                    embedding float[384],
                    +record_id TEXT,
                    +record_type TEXT,
                    +content TEXT
                )
            """)
            self._vec_available = True
            logger.info("sqlite-vec loaded — vector search available")
        except Exception as e:
            self._vec_available = False
            logger.warning(f"sqlite-vec not available: {e}. RAG chat will be limited.")

    # ── Processing State ───────────────────────────────────

    def upsert_file_state(self, file_id: str, filename: str, file_type: str,
                          sha256_hash: str, file_size_bytes: int,
                          status: str = "pending", current_pass: str = None,
                          error_message: str = None, page_count: int = None):
        """Insert or update a file's processing state."""
        conn = self._get_conn()
        # Delete any prior row with the same sha256 but different file_id
        # (happens when re-uploading the same file after a failed run)
        conn.execute(
            "DELETE FROM processing_state WHERE sha256_hash = ? AND file_id != ?",
            (sha256_hash, file_id),
        )
        conn.execute("""
            INSERT INTO processing_state
                (file_id, filename, file_type, sha256_hash, file_size_bytes,
                 status, current_pass, error_message, date_added, page_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)
            ON CONFLICT(file_id) DO UPDATE SET
                status = excluded.status,
                current_pass = excluded.current_pass,
                error_message = excluded.error_message,
                date_completed = CASE WHEN excluded.status IN ('complete', 'failed', 'skipped')
                                      THEN datetime('now') ELSE date_completed END
        """, (file_id, filename, file_type, sha256_hash, file_size_bytes,
              status, current_pass, error_message, page_count))
        conn.commit()

    def update_file_status(self, file_id: str, status: str,
                           current_pass: str = None, error_message: str = None):
        """Update just the status of an existing file."""
        conn = self._get_conn()
        conn.execute("""
            UPDATE processing_state SET
                status = ?,
                current_pass = ?,
                error_message = ?,
                date_completed = CASE WHEN ? IN ('complete', 'failed', 'skipped')
                                      THEN datetime('now') ELSE date_completed END
            WHERE file_id = ?
        """, (status, current_pass, error_message, status, file_id))
        conn.commit()

    def is_duplicate(self, sha256_hash: str) -> bool:
        """Check if a file with this hash has already been processed."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT 1 FROM processing_state WHERE sha256_hash = ? AND status = 'complete'",
            (sha256_hash,)
        ).fetchone()
        return row is not None

    def get_pending_files(self) -> list[dict]:
        """Get all files that haven't completed processing."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM processing_state WHERE status NOT IN ('complete', 'skipped') ORDER BY date_added"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_processing_stats(self) -> dict:
        """Get summary statistics of file processing."""
        conn = self._get_conn()
        row = conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'complete' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status NOT IN ('complete', 'failed', 'pending', 'skipped') THEN 1 ELSE 0 END) as in_progress
            FROM processing_state
        """).fetchone()
        return dict(row)

    # ── Redaction Audit Log ────────────────────────────────

    def log_redaction(self, original_type: str, context: str, file_source: str):
        """Log a PII redaction event for the audit trail."""
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO redaction_log (original_type, context, file_source, timestamp) VALUES (?, ?, ?, datetime('now'))",
            (original_type, context, file_source)
        )
        conn.commit()

    def get_redaction_summary(self) -> list[dict]:
        """Get redaction counts by type for Section 10 of the report."""
        conn = self._get_conn()
        rows = conn.execute("""
            SELECT original_type, COUNT(*) as count
            FROM redaction_log
            GROUP BY original_type
            ORDER BY count DESC
        """).fetchall()
        return [dict(r) for r in rows]

    # ── Monitoring Alerts ──────────────────────────────────

    def save_alert(self, alert_id: str, source: str, title: str,
                   description: str, relevance: str, severity: str,
                   url: str = None):
        """Save a monitoring alert."""
        conn = self._get_conn()
        conn.execute("""
            INSERT OR REPLACE INTO monitoring_alerts
                (alert_id, source, title, description, relevance_explanation,
                 severity, url, date_detected)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (alert_id, source, title, description, relevance, severity, url))
        conn.commit()

    def get_unaddressed_alerts(self) -> list[dict]:
        """Get all alerts that haven't been addressed."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM monitoring_alerts WHERE addressed = 0 ORDER BY date_detected DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_alert_addressed(self, alert_id: str):
        """Mark an alert as addressed."""
        conn = self._get_conn()
        conn.execute(
            "UPDATE monitoring_alerts SET addressed = 1 WHERE alert_id = ?",
            (alert_id,)
        )
        conn.commit()

    # ── Vector Storage (RAG Chat) ──────────────────────────

    def upsert_vector(self, record_id: str, record_type: str,
                      content: str, embedding: list[float]):
        """Store or update a vector embedding for RAG retrieval."""
        if not self._vec_available:
            return

        conn = self._get_conn()
        # Delete existing entry if present
        conn.execute(
            "DELETE FROM clinical_vectors WHERE record_id = ?",
            (record_id,)
        )
        conn.execute(
            "INSERT INTO clinical_vectors (record_id, record_type, content, embedding) VALUES (?, ?, ?, ?)",
            (record_id, record_type, content, json.dumps(embedding))
        )
        conn.commit()

    def search_vectors(self, query_embedding: list[float], n_results: int = 5) -> list[dict]:
        """Find the most similar vectors to a query embedding."""
        if not self._vec_available:
            return []

        conn = self._get_conn()
        rows = conn.execute("""
            SELECT record_id, record_type, content, distance
            FROM clinical_vectors
            WHERE embedding MATCH ?
            ORDER BY distance
            LIMIT ?
        """, (json.dumps(query_embedding), n_results)).fetchall()
        return [dict(r) for r in rows]

    # ── Pipeline Run Tracking ──────────────────────────────

    def start_pipeline_run(self, run_id: str):
        """Record the start of a pipeline run."""
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO pipeline_runs (run_id, started_at, status) VALUES (?, datetime('now'), 'running')",
            (run_id,)
        )
        conn.commit()

    def complete_pipeline_run(self, run_id: str, files_processed: int, files_failed: int):
        """Record the completion of a pipeline run."""
        conn = self._get_conn()
        conn.execute("""
            UPDATE pipeline_runs SET
                completed_at = datetime('now'),
                files_processed = ?,
                files_failed = ?,
                status = 'complete'
            WHERE run_id = ?
        """, (files_processed, files_failed, run_id))
        conn.commit()

    # ── Profile Persistence ───────────────────────────────

    def create_profile(self, profile_id: str, status: str = "processing",
                       display_name: str = None):
        """Create a new profile record (called immediately on upload)."""
        conn = self._get_conn()
        conn.execute("""
            INSERT OR IGNORE INTO profiles (profile_id, created_at, updated_at, status, display_name)
            VALUES (?, datetime('now'), datetime('now'), ?, ?)
        """, (profile_id, status, display_name))
        conn.commit()

    def update_profile_status(self, profile_id: str, status: str):
        """Update the status of an existing profile."""
        conn = self._get_conn()
        conn.execute("""
            UPDATE profiles SET status = ?, updated_at = datetime('now')
            WHERE profile_id = ?
        """, (status, profile_id))
        conn.commit()

    def get_profile_record(self, profile_id: str) -> Optional[dict]:
        """Get a profile record by ID."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM profiles WHERE profile_id = ?", (profile_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_profiles(self) -> list[dict]:
        """List all profiles (including processing and partial) ordered newest first."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM profiles ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Source Files ──────────────────────────────────────

    def create_source_file(self, file_id: str, profile_id: str, filename: str,
                           sha256_hash: str = None, file_size_bytes: int = None):
        """Register a source file linked to a profile."""
        conn = self._get_conn()
        conn.execute("""
            INSERT OR IGNORE INTO source_files
                (file_id, profile_id, filename, sha256_hash, file_size_bytes, date_added)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        """, (file_id, profile_id, filename, sha256_hash, file_size_bytes))
        conn.commit()

    def get_source_files(self, profile_id: str) -> list[dict]:
        """Get all source files for a profile."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM source_files WHERE profile_id = ?", (profile_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Processing Jobs ───────────────────────────────────

    def create_processing_job(self, job_id: str, profile_id: str):
        """Create a processing job record (queued state)."""
        conn = self._get_conn()
        conn.execute("""
            INSERT OR IGNORE INTO processing_jobs
                (job_id, profile_id, started_at, status, progress_pct)
            VALUES (?, ?, datetime('now'), 'queued', 0)
        """, (job_id, profile_id))
        conn.commit()

    def update_job_status(self, job_id: str, status: str, progress_pct: int = None):
        """Update job status and optionally its progress percentage."""
        conn = self._get_conn()
        if progress_pct is not None:
            conn.execute("""
                UPDATE processing_jobs SET status = ?, progress_pct = ?
                WHERE job_id = ?
            """, (status, progress_pct, job_id))
        else:
            conn.execute(
                "UPDATE processing_jobs SET status = ? WHERE job_id = ?",
                (status, job_id)
            )
        conn.commit()

    def complete_job(self, job_id: str, status: str = "completed"):
        """Mark a job as completed (or failed)."""
        conn = self._get_conn()
        conn.execute("""
            UPDATE processing_jobs SET
                status = ?,
                completed_at = datetime('now'),
                progress_pct = CASE WHEN ? = 'completed' THEN 100 ELSE progress_pct END
            WHERE job_id = ?
        """, (status, status, job_id))
        conn.commit()

    def get_job(self, job_id: str) -> Optional[dict]:
        """Get a processing job by ID."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM processing_jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        return dict(row) if row else None

    # ── Processing Checkpoints ────────────────────────────

    def save_checkpoint(self, job_id: str, file_id: str, stage: str,
                        status: str = "completed", parser_version: str = None,
                        artifact_json: str = None):
        """Save or update a per-file per-stage checkpoint."""
        conn = self._get_conn()
        conn.execute("""
            INSERT INTO processing_checkpoints
                (job_id, file_id, stage, status, parser_version, artifact_json, saved_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(job_id, file_id, stage) DO UPDATE SET
                status = excluded.status,
                parser_version = excluded.parser_version,
                artifact_json = excluded.artifact_json,
                saved_at = datetime('now')
        """, (job_id, file_id, stage, status, parser_version, artifact_json))
        conn.commit()

    def get_completed_stages(self, file_id: str,
                             parser_version: str = None) -> list[str]:
        """Return stage names already completed for a file.

        Optionally filters by parser_version so version bumps force re-extraction.
        """
        conn = self._get_conn()
        if parser_version:
            rows = conn.execute("""
                SELECT DISTINCT stage FROM processing_checkpoints
                WHERE file_id = ? AND status = 'completed' AND parser_version = ?
            """, (file_id, parser_version)).fetchall()
        else:
            rows = conn.execute("""
                SELECT DISTINCT stage FROM processing_checkpoints
                WHERE file_id = ? AND status = 'completed'
            """, (file_id,)).fetchall()
        return [r["stage"] for r in rows]

    def is_stage_completed(self, file_id: str, stage: str,
                           parser_version: str = None) -> bool:
        """Return True if a stage has already been completed for this file."""
        return stage in self.get_completed_stages(file_id, parser_version)

    # ── Profile Snapshots ─────────────────────────────────

    def save_profile_snapshot(self, profile_id: str, snapshot_json: str):
        """Persist a new profile snapshot (appends; latest is max saved_at)."""
        conn = self._get_conn()
        conn.execute("""
            INSERT INTO profile_snapshots (profile_id, snapshot_json, saved_at)
            VALUES (?, ?, datetime('now'))
        """, (profile_id, snapshot_json))
        conn.commit()

    def get_latest_snapshot(self, profile_id: str) -> Optional[dict]:
        """Return the most recent profile snapshot for a profile."""
        conn = self._get_conn()
        row = conn.execute("""
            SELECT snapshot_json, saved_at FROM profile_snapshots
            WHERE profile_id = ?
            ORDER BY id DESC
            LIMIT 1
        """, (profile_id,)).fetchone()
        if not row:
            return None
        try:
            data = json.loads(row["snapshot_json"])
            data["_snapshot_saved_at"] = row["saved_at"]
            return data
        except Exception:
            return None

    # ── Session Reset ────────────────────────────────────────

    def clear_patient_data(self):
        """
        Clear all patient-specific data for a new session.

        Wipes: processing state, redaction log, alerts, vectors, pipeline runs,
               profiles, source_files, processing_jobs, checkpoints, snapshots.
        Preserves: database schema (tables remain, ready for new data).
        Does NOT touch: API key vault (encrypted separately).
        """
        conn = self._get_conn()
        conn.execute("DELETE FROM processing_state")
        conn.execute("DELETE FROM redaction_log")
        conn.execute("DELETE FROM monitoring_alerts")
        conn.execute("DELETE FROM pipeline_runs")
        conn.execute("DELETE FROM profile_snapshots")
        conn.execute("DELETE FROM processing_checkpoints")
        conn.execute("DELETE FROM processing_jobs")
        conn.execute("DELETE FROM source_files")
        conn.execute("DELETE FROM profiles")
        if self._vec_available:
            conn.execute("DELETE FROM clinical_vectors")
        conn.commit()
        logger.info("All patient data cleared from database — ready for new session")

    # ── Cleanup ────────────────────────────────────────────

    def close(self):
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
