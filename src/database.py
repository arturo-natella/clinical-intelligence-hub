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

    # ── Session Reset ────────────────────────────────────────

    def clear_patient_data(self):
        """
        Clear all patient-specific data for a new session.

        Wipes: processing state, redaction log, alerts, vectors, pipeline runs.
        Preserves: database schema (tables remain, ready for new data).
        Does NOT touch: API key vault (encrypted separately).
        """
        conn = self._get_conn()
        conn.execute("DELETE FROM processing_state")
        conn.execute("DELETE FROM redaction_log")
        conn.execute("DELETE FROM monitoring_alerts")
        conn.execute("DELETE FROM pipeline_runs")
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
