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
        self._vec_conn = None  # apsw connection for vector ops (macOS fallback)
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
                page_count INTEGER,
                text_chunks_completed INTEGER NOT NULL DEFAULT 0,
                text_chunks_total INTEGER NOT NULL DEFAULT 0
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

        self._migrate_processing_state(conn)

        # Try to load sqlite-vec extension for vector search
        self._init_vector_storage(conn)

        conn.commit()
        logger.info("Local clinical database initialized")

    @staticmethod
    def _migrate_processing_state(conn: sqlite3.Connection):
        """Add resumable extraction columns to databases created pre-v3."""
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(processing_state)")
        }
        migrations = {
            "text_chunks_completed": (
                "ALTER TABLE processing_state ADD COLUMN "
                "text_chunks_completed INTEGER NOT NULL DEFAULT 0"
            ),
            "text_chunks_total": (
                "ALTER TABLE processing_state ADD COLUMN "
                "text_chunks_total INTEGER NOT NULL DEFAULT 0"
            ),
        }
        for column, statement in migrations.items():
            if column not in columns:
                conn.execute(statement)

    def _init_vector_storage(self, conn: sqlite3.Connection):
        """Initializes sqlite-vec for RAG chat vector storage.

        Tries stdlib sqlite3 first.  On macOS the module lacks
        enable_load_extension, so we fall back to apsw which ships
        its own SQLite with extension-loading enabled.
        """
        vec_table_ddl = """
            CREATE VIRTUAL TABLE IF NOT EXISTS clinical_vectors
            USING vec0(
                embedding float[384],
                +record_id TEXT,
                +record_type TEXT,
                +content TEXT
            )
        """

        # ── Attempt 1: stdlib sqlite3 (works on Linux / Homebrew Python) ──
        try:
            import sqlite_vec
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
            conn.execute(vec_table_ddl)
            self._vec_available = True
            logger.info("sqlite-vec loaded — vector search available")
            return
        except (AttributeError, Exception):
            pass  # enable_load_extension missing or load failed

        # ── Attempt 2: apsw fallback (macOS) ──
        try:
            import apsw
            import sqlite_vec

            vec_conn = apsw.Connection(str(self.db_path))
            vec_conn.pragma("journal_mode", "WAL")
            vec_conn.enableloadextension(True)
            vec_conn.loadextension(sqlite_vec.loadable_path())
            vec_conn.enableloadextension(False)
            vec_conn.execute(vec_table_ddl)
            self._vec_conn = vec_conn
            self._vec_available = True
            logger.info("sqlite-vec loaded via apsw — vector search available")
            return
        except Exception as e:
            self._vec_available = False
            logger.warning(
                "sqlite-vec not available; RAG chat will be limited "
                "(error_type=%s)",
                type(e).__name__,
            )

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

    def get_file_state_by_hash(self, sha256_hash: str) -> Optional[dict]:
        """Return the existing state for a file, including its resume cursor."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM processing_state WHERE sha256_hash = ?",
            (sha256_hash,),
        ).fetchone()
        return dict(row) if row else None

    def get_file_state(self, file_id: str) -> Optional[dict]:
        """Return operational state for one registered file."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM processing_state WHERE file_id = ?",
            (file_id,),
        ).fetchone()
        return dict(row) if row else None

    def update_text_checkpoint(self, file_id: str, chunks_completed: int,
                               chunks_total: int):
        """Persist the contiguous MedGemma chunk cursor for one file."""
        if chunks_completed < 0 or chunks_total < 0:
            raise ValueError("Text chunk counts cannot be negative")
        if chunks_completed > chunks_total:
            raise ValueError("Completed text chunks cannot exceed total chunks")

        conn = self._get_conn()
        cursor = conn.execute("""
            UPDATE processing_state SET
                status = 'extracting',
                current_pass = 'text_extraction',
                text_chunks_completed = ?,
                text_chunks_total = ?
            WHERE file_id = ?
        """, (chunks_completed, chunks_total, file_id))
        if cursor.rowcount != 1:
            raise RuntimeError("Cannot checkpoint an unregistered file")
        conn.commit()

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

    def _get_vec_conn(self):
        """Returns the connection for vector operations.

        Uses the dedicated apsw connection if sqlite-vec was loaded via the
        macOS fallback path, otherwise falls back to the main sqlite3 conn.
        """
        if self._vec_conn is not None:
            return self._vec_conn
        return self._get_conn()

    def _vec_exec(self, sql: str, params=None):
        """Execute a write statement on the vector connection.

        apsw's execute() returns a lazy iterator — statements only run when
        consumed.  This helper forces execution for INSERT/DELETE/UPDATE.
        """
        conn = self._get_vec_conn()
        if params is not None:
            list(conn.execute(sql, params))
        else:
            list(conn.execute(sql))

    def upsert_vector(self, record_id: str, record_type: str,
                      content: str, embedding: list[float]):
        """Store or update a vector embedding for RAG retrieval."""
        if not self._vec_available:
            return

        self._vec_exec(
            "DELETE FROM clinical_vectors WHERE record_id = ?",
            (record_id,)
        )
        self._vec_exec(
            "INSERT INTO clinical_vectors (record_id, record_type, content, embedding) VALUES (?, ?, ?, ?)",
            (record_id, record_type, content, json.dumps(embedding))
        )
        # stdlib sqlite3 needs explicit commit; apsw auto-commits outside a transaction
        if self._vec_conn is None:
            self._get_conn().commit()

    def search_vectors(self, query_embedding: list[float], n_results: int = 5) -> list[dict]:
        """Find the most similar vectors to a query embedding."""
        if not self._vec_available:
            return []

        conn = self._get_vec_conn()
        rows = conn.execute("""
            SELECT record_id, record_type, content, distance
            FROM clinical_vectors
            WHERE embedding MATCH ?
            ORDER BY distance
            LIMIT ?
        """, (json.dumps(query_embedding), n_results))

        if self._vec_conn is not None:
            # apsw yields tuples — convert to dicts
            return [
                {"record_id": r[0], "record_type": r[1], "content": r[2], "distance": r[3]}
                for r in rows
            ]
        return [dict(r) for r in rows.fetchall()]

    # ── Pipeline Run Tracking ──────────────────────────────

    def start_pipeline_run(self, run_id: str):
        """Record the start of a pipeline run."""
        conn = self._get_conn()
        conn.execute("""
            UPDATE pipeline_runs SET
                completed_at = datetime('now'),
                status = 'interrupted'
            WHERE status = 'running'
        """)
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

    def fail_pipeline_run(self, run_id: str):
        """Mark a started pipeline run as failed after an unhandled error."""
        conn = self._get_conn()
        conn.execute("""
            UPDATE pipeline_runs SET
                completed_at = datetime('now'),
                status = 'failed'
            WHERE run_id = ? AND status = 'running'
        """, (run_id,))
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
        conn.commit()
        if self._vec_available:
            self._vec_exec("DELETE FROM clinical_vectors")
        logger.info("All patient data cleared from database — ready for new session")

    # ── Cleanup ────────────────────────────────────────────

    def close(self):
        """Close all database connections."""
        if self._vec_conn is not None:
            self._vec_conn.close()
            self._vec_conn = None
        if self._conn:
            self._conn.close()
            self._conn = None
