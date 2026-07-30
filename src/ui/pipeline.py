"""
Clinical Intelligence Hub — 6-Pass Pipeline Orchestrator

Coordinates the entire analysis pipeline:
  Pass 0: Preprocessing (OCR, dedup, classification)
  Pass 1a: MedGemma 27B text extraction
  Pass 1b: MedGemma 4B vision analysis
  Pass 1c: MONAI clinical detection
  Pass 1.5: PII redaction
  Pass 2: Gemini 3 Flash gap-filling
  Pass 3: Deep Research cross-disciplinary
  Pass 4: Deep Research literature search
  Pass 5: Clinical validation
  Pass 6: Report generation

Features:
  - State checkpointing (crash recovery via SQLite)
  - Real-time progress via callback
  - caffeinate for macOS (prevents sleep during analysis)
  - Sequential model loading (memory management)
"""

import hashlib
import logging
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from src.models import (
    Allergy,
    ClinicalNote,
    Diagnosis,
    FileType,
    GeneticVariant,
    LabResult,
    Medication,
    PatientProfile,
    ProcessedFile,
    ProcessingStatus,
    Provenance,
    Procedure,
)

logger = logging.getLogger("CIH-Pipeline")

GEMINI_FALLBACK_MAX_DOCUMENTS = 3
GEMINI_FALLBACK_MAX_DOCUMENT_CHARS = 60_000
GEMINI_FALLBACK_CHUNK_CHARS = 12_000


class Pipeline:
    """
    Orchestrates the 6-pass clinical analysis pipeline.

    Each pass has checkpointing — if the process crashes,
    it resumes from the last completed pass.
    """

    def __init__(self, data_dir: Path, passphrase: str,
                 progress_callback: Callable = None,
                 pause_event=None,
                 api_calls_event=None,
                 profile_update_callback: Callable = None):
        """
        Args:
            data_dir: Base directory for all data
            passphrase: Encryption passphrase for patient data
            progress_callback: Called with (pass_name, message, percent)
            pause_event: threading.Event — cleared when paused, set when running
            api_calls_event: threading.Event — cleared to pause external API calls
            profile_update_callback: Called with profile dict after each chunk
        """
        self.data_dir = data_dir
        self._passphrase = passphrase
        self._progress = progress_callback or (lambda *a: None)
        self._pause_event = pause_event
        self._api_calls_event = api_calls_event
        self._on_profile_update = profile_update_callback or (lambda p: None)
        self._caffeinate_proc = None
        self._local_processing_errors: list[str] = []

        # Lazy-initialized components
        self._db = None
        self._vault = None
        self._profile = None
        self._redacted_profile_dict = None
        self._fallback_candidates: list[dict] = []
        self._redacted_fallback_documents: list[dict] = []
        self._redactor = None
        self._loinc_db = None

    def _wait_if_paused(self):
        """Block until resumed if pipeline is paused."""
        if self._pause_event and not self._pause_event.is_set():
            logger.info("Pipeline paused — waiting for resume...")
            self._pause_event.wait()  # Blocks until set()
            logger.info("Pipeline resumed")

    def _wait_for_api_calls(self, stage: str, percent: int = -1):
        """Wait at a safe boundary while external API calls are paused.

        Local OCR, extraction, imaging, and redaction never wait on this event.
        A pause requested during an in-flight request takes effect before the
        next external stage begins.
        """
        if self._api_calls_event and not self._api_calls_event.is_set():
            message = (
                f"Local processing is complete. API calls are paused before {stage}."
            )
            logger.info(message)
            self._progress("api_waiting", message, percent)
            self._api_calls_event.wait()
            logger.info("API calls resumed")
            self._progress("log", f"API calls resumed — starting {stage}", -1)

    def _record_local_error(self, message: str):
        """Record a local-processing problem that must block external calls."""
        if message not in self._local_processing_errors:
            self._local_processing_errors.append(message)
        logger.warning("Local processing gate: %s", message)

    def _local_processing_ready(self, preprocessed: list[dict],
                                expected_file_count: int,
                                redaction_ok: bool) -> bool:
        """Return True only when every input finished the local passes safely."""
        if expected_file_count <= 0:
            self._record_local_error("No medical records were provided")
        if len(preprocessed) != expected_file_count:
            self._record_local_error(
                f"Only {len(preprocessed)} of {expected_file_count} file(s) "
                "completed preprocessing"
            )
        if not redaction_ok:
            self._record_local_error("PII redaction did not complete")
        return (
            bool(preprocessed)
            and len(preprocessed) == expected_file_count
            and redaction_ok
            and not self._local_processing_errors
        )

    def _finalize_local_file_states(self, preprocessed: list[dict], ready: bool):
        """Checkpoint the local-only result before any external request."""
        status = ProcessingStatus.COMPLETE if ready else ProcessingStatus.FAILED
        error_message = None if ready else "; ".join(self._local_processing_errors)
        completed_at = datetime.now()
        file_ids = {item.get("file_id") for item in preprocessed}

        for processed_file in self._profile.processed_files:
            if processed_file.file_id not in file_ids:
                continue
            processed_file.status = status
            processed_file.current_pass = "local_processing"
            processed_file.error_message = error_message
            processed_file.date_completed = completed_at
            if self._db:
                self._db.update_file_status(
                    processed_file.file_id,
                    status.value,
                    current_pass="local_processing",
                    error_message=error_message,
                )

        self._save_profile_checkpoint()

    def _log(self, message: str):
        """Send a detailed log line to the terminal viewer."""
        self._progress("log", message, -1)

    def run(self, input_files: list[Path]) -> PatientProfile:
        """
        Run the full pipeline on a set of input files.

        Returns the complete patient profile with all analysis results.
        """
        self._start_caffeinate()
        self._local_processing_errors = []
        run_id = None

        try:
            self._init_components()
            self._fallback_candidates = []
            self._redacted_fallback_documents = []
            self._progress("init", "Pipeline initialized", 0)

            # Load or create profile
            try:
                self._profile = self._vault.load_profile()
                if self._profile and isinstance(self._profile, dict):
                    self._profile = PatientProfile(**self._profile)
            except Exception as e:
                logger.warning(
                    "Could not load existing profile; starting fresh "
                    "(error_type=%s)",
                    type(e).__name__,
                )
                self._profile = None
            if not self._profile:
                self._profile = PatientProfile()

            run_id = f"run_{time.time_ns()}"
            self._db.start_pipeline_run(run_id)

            total_steps = 8  # approximate number of major passes
            step = 0

            # ── Pass 0: Preprocessing ──
            step += 1
            self._progress("pass_0", "Classifying and preprocessing files...",
                           int(step / total_steps * 100))
            self._log(f"Pass 0: Processing {len(input_files)} file(s)...")
            preprocessed = self._pass_0_preprocess(input_files)
            for index, item in enumerate(preprocessed, 1):
                self._log(
                    f"  \u2713 Record {index}: "
                    f"{len(item.get('text', '')):,} chars, "
                    f"{len(item.get('pages', []))} pages"
                )

            # ── Pass 1a: Text Extraction ──
            self._wait_if_paused()
            step += 1
            self._progress("pass_1a", "Extracting clinical data from text...",
                           int(step / total_steps * 100))
            self._log("Pass 1a: Loading MedGemma 27B for clinical extraction...")
            self._pass_1a_text_extraction(preprocessed)

            # ── Pass 1b+1c: Unified Image Analysis ──
            self._wait_if_paused()
            step += 2  # Covers both old 1b and 1c steps
            self._progress("pass_1b", "Analyzing medical images...",
                           int(step / total_steps * 100))
            self._log("Pass 1b+1c: Unified image analysis (PDF images, standalone, DICOM)...")
            self._pass_image_analysis(preprocessed)

            # ── Pass 1.5: PII Redaction ──
            self._wait_if_paused()
            step += 1
            self._progress("pass_1_5", "Removing personal information...",
                           int(step / total_steps * 100))
            self._log("Pass 1.5: PII redaction check...")
            redaction_ok = self._pass_1_5_redaction()

            # Hard safety boundary: all local processing and redaction must
            # finish successfully before any external API stage can begin.
            local_ready = self._local_processing_ready(
                preprocessed,
                expected_file_count=len(input_files),
                redaction_ok=redaction_ok,
            )
            self._finalize_local_file_states(preprocessed, local_ready)
            self._publish_profile_snapshot()

            if local_ready:
                self._progress(
                    "local_complete",
                    "Local record processing complete and verified.",
                    int(step / total_steps * 100),
                )
                self._log(
                    "Safety gate passed: all records processed locally before API calls."
                )

                # ── Pass 2-4: Cloud Analysis ──
                self._wait_if_paused()
                step += 1
                api_percent = int(step / total_steps * 100)
                self._wait_for_api_calls("cloud analysis", api_percent)
                self._progress("pass_2_4", "Analyzing patterns across specialties...",
                               api_percent)
                self._log("Pass 2-4: Cloud analysis (requires Gemini API key)...")
                self._pass_2_4_cloud_analysis()

                # ── Pass 5: Clinical Validation ──
                self._wait_if_paused()
                step += 1
                validation_percent = int(step / total_steps * 100)
                self._wait_for_api_calls("clinical validation", validation_percent)
                self._progress("pass_5", "Validating against clinical databases...",
                               validation_percent)
                self._log("Pass 5: Validating against OpenFDA, DrugBank, PubMed...")
                self._pass_5_validation()
            else:
                step += 2
                reason = "; ".join(self._local_processing_errors)
                self._progress(
                    "api_skipped",
                    "External API calls skipped because local record processing "
                    "did not complete safely.",
                    int(step / total_steps * 100),
                )
                self._log(f"API safety gate blocked external calls: {reason}")

            # ── Pass 6: Report Generation ──
            step += 1
            self._progress("pass_6", "Generating your clinical report...",
                           int(step / total_steps * 100))
            self._pass_6_report()

            # Save profile
            profile_dict = self._profile.model_dump(mode="json")
            self._vault.save_profile(profile_dict)

            # Complete pipeline run
            files_ok = len([f for f in self._profile.processed_files
                            if f.status == ProcessingStatus.COMPLETE])
            files_fail = len([f for f in self._profile.processed_files
                              if f.status == ProcessingStatus.FAILED])
            self._db.complete_pipeline_run(run_id, files_ok, files_fail)

            self._progress("complete", "Analysis complete!", 100)
            logger.info(
                f"Pipeline complete: {files_ok} files processed, "
                f"{files_fail} failures"
            )

            return self._profile

        except Exception as e:
            if run_id and self._db:
                try:
                    self._db.fail_pipeline_run(run_id)
                except Exception as tracking_error:
                    logger.error(
                        "Failed to mark pipeline run failed (error_type=%s)",
                        type(tracking_error).__name__,
                    )
            error_type = type(e).__name__
            logger.error("Pipeline failed (error_type=%s)", error_type)
            self._progress("error", f"Pipeline error ({error_type})", -1)
            raise

        finally:
            self._stop_caffeinate()

    # ── Pass 0: Preprocessing ─────────────────────────────────

    def _pass_0_preprocess(self, input_files: list[Path]) -> list[dict]:
        """Classify, deduplicate, and preprocess files."""
        from src.extraction.preprocessor import Preprocessor

        preprocessor = Preprocessor(self._db)
        results = []

        for filepath in input_files:
            try:
                result = preprocessor.process(filepath)
                if result:
                    results.append(result)

                    # Track in profile
                    pf = ProcessedFile(
                        file_id=result.get("file_id", ""),
                        filename=filepath.name,
                        file_type=FileType(result.get("file_type", "unknown")),
                        sha256_hash=result.get("sha256", ""),
                        file_size_bytes=filepath.stat().st_size,
                        status=ProcessingStatus.PREPROCESSING,
                        page_count=result.get("page_count"),
                    )
                    existing_file = next(
                        (
                            tracked
                            for tracked in self._profile.processed_files
                            if tracked.sha256_hash == pf.sha256_hash
                        ),
                        None,
                    )
                    if existing_file:
                        existing_file.file_id = pf.file_id
                        existing_file.filename = pf.filename
                        existing_file.file_type = pf.file_type
                        existing_file.file_size_bytes = pf.file_size_bytes
                        existing_file.status = pf.status
                        existing_file.current_pass = pf.current_pass
                        existing_file.error_message = None
                        existing_file.page_count = pf.page_count
                    else:
                        self._profile.processed_files.append(pf)

                else:
                    self._record_local_error(
                        "One record was duplicate, unsupported, or could not be "
                        "preprocessed"
                    )

            except Exception as e:
                error_type = type(e).__name__
                logger.error(
                    "Preprocessing failed for one record (error_type=%s)",
                    error_type,
                )
                self._record_local_error(
                    f"Preprocessing failed for one record ({error_type})"
                )

        if not results and input_files:
            logger.warning(
                f"Pass 0: 0 of {len(input_files)} files produced results. "
                f"All files were duplicates, unsupported, or failed preprocessing."
            )
            self._progress(
                "pass_0",
                f"Warning: Could not extract data from {len(input_files)} file(s). "
                "Check file format and try again.",
                int(1 / 8 * 100),
            )
        else:
            logger.info(f"Pass 0: {len(results)} of {len(input_files)} files preprocessed")

        return results

    # ── Pass 1a: Text Extraction ──────────────────────────────

    def _pass_1a_text_extraction(self, preprocessed: list[dict]):
        """Extract clinical data from text using MedGemma 27B."""
        # Cap pages for initial extraction — process the first N pages
        # to get data on the dashboard quickly. Full extraction can run later.
        MAX_PAGES_PER_FILE = int(os.environ.get("MEDPREP_MAX_PAGES", "0"))

        try:
            from src.extraction.text_extractor import TextExtractor

            # Per-chunk callback: merge into profile and publish snapshot
            def _on_chunk_complete(delta):
                """Merge each chunk's results into profile and update dashboard."""
                self._append_extraction_results(delta)
                self._publish_profile_snapshot()

            checkpoint_target = {"file_id": None}

            def _on_chunk_checkpoint(chunks_completed, chunks_total):
                """Advance SQLite only after the encrypted profile is durable."""
                file_id = checkpoint_target["file_id"]
                if not file_id:
                    raise RuntimeError("Text checkpoint is missing its file ID")
                self._db.update_text_checkpoint(
                    file_id,
                    chunks_completed,
                    chunks_total,
                )

            extractor = TextExtractor(
                progress_callback=self._progress,
                pause_event=self._pause_event,
                on_chunk_complete=_on_chunk_complete,
                on_chunk_checkpoint=_on_chunk_checkpoint,
            )

            for item in preprocessed:
                pages = item.get("pages", [])
                text = item.get("text", "")
                filename = item.get("filename", "unknown")
                file_type = item.get("file_type", "")
                requires_text_extraction = file_type in {
                    FileType.PDF_TEXT.value,
                    FileType.PDF_SCANNED.value,
                    FileType.FHIR_JSON.value,
                    FileType.GENETIC.value,
                }
                if not text or len(text.strip()) < 50:
                    if requires_text_extraction:
                        self._record_local_error(
                            "One record did not produce enough readable text"
                        )
                    continue

                # TextExtractor expects pages list [{page, text}]
                if not pages:
                    pages = [{"page": 1, "text": text}]

                checkpoint_target["file_id"] = item.get("file_id")

                # Optional page cap (0 = no limit, process everything)
                total_pages = len(pages)
                if MAX_PAGES_PER_FILE > 0 and total_pages > MAX_PAGES_PER_FILE:
                    logger.info(
                        "Capping one record to first %d of %d pages "
                        "(set MEDPREP_MAX_PAGES=0 to process all pages)",
                        MAX_PAGES_PER_FILE,
                        total_pages,
                    )
                    pages = pages[:MAX_PAGES_PER_FILE]
                    self._record_local_error(
                        "One record was only partially processed "
                        f"({MAX_PAGES_PER_FILE} of {total_pages} pages)"
                    )
                else:
                    estimated_chunks = max(1, total_pages // 7)
                    estimated_minutes = estimated_chunks * 6
                    logger.info(
                        f"Processing all {total_pages} pages (~{estimated_chunks} chunks, "
                        f"~{estimated_minutes // 60}h {estimated_minutes % 60}m estimated)"
                    )
                    self._log(
                        f"Processing all {total_pages} pages "
                        f"(~{estimated_minutes // 60}h {estimated_minutes % 60}m estimated)"
                    )

                try:
                    total_chunks = extractor.count_chunks(pages)
                    completed_chunks = int(
                        item.get("text_chunks_completed") or 0
                    )
                    stored_total = int(item.get("text_chunks_total") or 0)
                    if (
                        completed_chunks > total_chunks
                        or (stored_total and stored_total != total_chunks)
                    ):
                        logger.warning(
                            "Stored text checkpoint does not match current chunk "
                            "plan; restarting from chunk 1"
                        )
                        completed_chunks = 0
                        self._db.update_text_checkpoint(
                            item.get("file_id"),
                            0,
                            total_chunks,
                        )

                    had_prior_extractions = (
                        self._profile_has_extractions_for_source(filename)
                    )
                    results = extractor.extract(
                        pages=pages,
                        source_file=filename,
                        start_chunk=completed_chunks,
                    )
                    item_count = sum(
                        len(values)
                        for values in results.values()
                        if isinstance(values, list)
                    ) if isinstance(results, dict) else 0
                    checkpoint_state = self._db.get_file_state(
                        item.get("file_id")
                    )
                    checkpoint_complete = bool(
                        checkpoint_state
                        and checkpoint_state["text_chunks_completed"]
                        == total_chunks
                        and checkpoint_state["text_chunks_total"]
                        == total_chunks
                    )
                    if requires_text_extraction and not checkpoint_complete:
                        self._record_local_error(
                            "Local text extraction did not finish all chunks"
                        )
                    if (
                        requires_text_extraction
                        and checkpoint_complete
                        and item_count == 0
                        and not had_prior_extractions
                    ):
                        self._fallback_candidates.append({
                            "source_file": filename,
                            "text": text,
                        })
                        logger.info(
                            "Local extraction returned no clinical data; "
                            "document is eligible for redacted Gemini fallback"
                        )
                    # No need to call _merge_extraction_results here —
                    # merging happens per-chunk via _on_chunk_complete
                except Exception as e:
                    error_type = type(e).__name__
                    logger.error(
                        "Text extraction failed (error_type=%s)",
                        error_type,
                    )
                    self._log(f"  Error: text extraction failed ({error_type})")
                    self._record_local_error(
                        f"Text extraction failed for one record ({error_type})"
                    )

            # Summary of what was extracted
            tl = self._profile.clinical_timeline
            self._log(f"Pass 1a complete: {len(tl.medications)} meds, "
                      f"{len(tl.labs)} labs, {len(tl.diagnoses)} diagnoses")

        except ImportError:
            logger.warning("TextExtractor not available — skipping Pass 1a")
            self._log("TextExtractor not available — skipped")
            self._record_local_error("Local text extractor is not available")

    # ── Pass 1b+1c: Unified Image Analysis ──────────────────

    def _pass_image_analysis(self, preprocessed: list[dict]):
        """
        Unified image analysis replacing old Pass 1b + 1c.

        Handles all image sources (PDF embedded, standalone, DICOM),
        classifies modality/body region, and routes to MedGemma 4B
        vision analysis and MONAI quantitative analysis.
        """
        image_only_sources = {
            item.get("filename", "unknown")
            for item in preprocessed
            if item.get("file_type") in {
                FileType.IMAGE.value,
                FileType.DICOM.value,
            }
        }

        try:
            from src.imaging.image_pipeline import ImagePipeline

            img_pipeline = ImagePipeline(
                data_dir=self.data_dir,
                progress_callback=self._progress,
                pause_event=self._pause_event,
            )
            summary = img_pipeline.process(preprocessed, self._profile)

            # Graceful degradation still allows local report generation, but
            # any image-processing failure must prevent paid API stages from
            # consuming incomplete record data. This includes images embedded
            # in PDFs, not only standalone image/DICOM uploads.
            for error in getattr(summary, "errors", []):
                self._record_local_error(f"Local image processing: {error}")

            processed_image_sources = {
                study.provenance.source_file
                for study in self._profile.clinical_timeline.imaging
                if study.provenance
            }
            for _filename in sorted(image_only_sources - processed_image_sources):
                self._record_local_error(
                    "Local image analysis returned no usable data for one record"
                )

            # Publish updated profile so dashboard shows imaging findings
            self._publish_profile_snapshot()

        except ImportError as e:
            logger.warning(
                "ImagePipeline not available — skipping (error_type=%s)",
                type(e).__name__,
            )
            self._log("  Image analysis not available — skipped")
            if image_only_sources:
                self._record_local_error("Local image analysis is not available")
        except Exception as e:
            error_type = type(e).__name__
            logger.error("Image analysis failed (error_type=%s)", error_type)
            self._log(f"  Image analysis error ({error_type})")
            if image_only_sources:
                self._record_local_error(
                    f"Local image analysis failed ({error_type})"
                )

    # ── Pass 1.5: PII Redaction ───────────────────────────────

    @classmethod
    def _sanitize_cloud_metadata(cls, value):
        """Remove local filenames that may themselves contain patient names."""
        if isinstance(value, dict):
            sanitized = {}
            for key, child in value.items():
                if key in {"source_file", "filename", "file_source"}:
                    sanitized[key] = "[LOCAL_SOURCE_REDACTED]"
                else:
                    sanitized[key] = cls._sanitize_cloud_metadata(child)
            return sanitized
        if isinstance(value, list):
            return [cls._sanitize_cloud_metadata(child) for child in value]
        return value

    def _pass_1_5_redaction(self):
        """Redact PII before cloud analysis.

        Creates self._redacted_profile_dict — a deep copy of the profile
        with all PII stripped. The original profile keeps raw data;
        only the redacted copy is sent to cloud APIs.
        """
        try:
            from src.privacy.redactor import PIIRedactor

            redactor = PIIRedactor(db=self._db)
            self._redactor = redactor
            if (
                self._fallback_candidates
                and not getattr(redactor, "_presidio_available", False)
            ):
                raise RuntimeError(
                    "Presidio is required before raw-document cloud fallback"
                )
            profile_dict = self._profile.model_dump(mode="json")
            self._redacted_profile_dict = self._sanitize_cloud_metadata(
                redactor.redact_dict(
                    profile_dict,
                    source_file="pipeline_pass_1.5",
                )
            )

            self._redacted_fallback_documents = []
            eligible = self._fallback_candidates[:GEMINI_FALLBACK_MAX_DOCUMENTS]
            skipped_for_run_cap = max(
                0,
                len(self._fallback_candidates) - len(eligible),
            )
            skipped_for_size = 0
            for index, candidate in enumerate(eligible, 1):
                raw_text = candidate.get("text") or ""
                if len(raw_text) > GEMINI_FALLBACK_MAX_DOCUMENT_CHARS:
                    skipped_for_size += 1
                    continue
                redacted_text = redactor.redact(
                    raw_text,
                    source_file=f"fallback_document_{index}",
                )
                self._redacted_fallback_documents.append({
                    "source_file": candidate.get("source_file", "unknown"),
                    "redacted_text": redacted_text,
                })

            if skipped_for_run_cap or skipped_for_size:
                logger.warning(
                    "Gemini fallback skipped whole documents to honor the hard "
                    "spend ceiling (run_cap=%d, size_cap=%d)",
                    skipped_for_run_cap,
                    skipped_for_size,
                )
            summary = redactor.get_redaction_summary()
            count = summary.get("total", 0) if summary else 0
            logger.info(f"PII redaction complete — {count} entities redacted")
            return True
        except Exception as e:
            error_type = type(e).__name__
            logger.error(
                "PII redaction failed — external API calls will be blocked "
                "(error_type=%s)",
                error_type,
            )
            self._redacted_profile_dict = None
            self._redacted_fallback_documents = []
            self._redactor = None
            self._record_local_error(
                f"PII redaction failed ({error_type})"
            )
            return False

    # ── Pass 2-4: Cloud Analysis ──────────────────────────────

    def _pass_2_4_cloud_analysis(self):
        """Run Gemini fallback and Deep Research."""
        gemini_key = None
        if self._vault:
            gemini_key = self._vault.get_api_key("gemini")

        if not gemini_key:
            logger.info("No Gemini API key — skipping cloud analysis (Passes 2-4)")
            return

        # The hard gate guarantees this exists. Never fall back to the raw
        # profile here: a missing redacted copy must block cloud work.
        if self._redacted_profile_dict is None:
            logger.error("Cloud analysis blocked because redacted profile is missing")
            return
        redacted = self._redacted_profile_dict

        # Pass 2: Gemini fallback gap-filling
        fallback_items_added = 0
        if self._redacted_fallback_documents:
            self._wait_for_api_calls("Gemini fallback extraction")
            try:
                from src.analysis.gemini_fallback import GeminiFallback

                fallback = GeminiFallback(api_key=gemini_key)
                for document in self._redacted_fallback_documents:
                    chunks = fallback.chunk_redacted_text(
                        document.get("redacted_text", ""),
                        GEMINI_FALLBACK_CHUNK_CHARS,
                    )
                    for chunk in chunks:
                        self._wait_for_api_calls("Gemini fallback extraction")
                        results = fallback.extract(
                            chunk,
                            document.get("source_file", "unknown"),
                        )
                        item_count = sum(
                            len(items)
                            for items in results.values()
                            if isinstance(items, list)
                        ) if isinstance(results, dict) else 0
                        if item_count:
                            self._append_extraction_results(results)
                            fallback_items_added += item_count
                            self._publish_profile_snapshot()

                logger.info(
                    "Pass 2 Gemini fallback complete (documents=%d, items=%d)",
                    len(self._redacted_fallback_documents),
                    fallback_items_added,
                )
            except Exception as e:
                logger.warning(
                    "Gemini fallback unavailable (error_type=%s)",
                    type(e).__name__,
                )
        else:
            logger.info("Pass 2 Gemini fallback not needed")

        if fallback_items_added and self._redactor:
            refreshed = self._redactor.redact_dict(
                self._profile.model_dump(mode="json"),
                source_file="pipeline_pass_2_refresh",
            )
            redacted = self._sanitize_cloud_metadata(refreshed)
            self._redacted_profile_dict = redacted

        # Pass 3-4: Deep Research
        self._wait_for_api_calls("Gemini 3 Flash research")
        try:
            from src.analysis.deep_research import DeepResearch
            dr = DeepResearch(api_key=gemini_key)

            import json
            profile_summary = json.dumps(redacted, indent=2, default=str)

            # Fan out the 29-specialty + 7-domain query engine over the
            # redacted timeline (this was a literal [] until 2026-07-30).
            queries = []
            try:
                from src.analysis.cross_disciplinary import CrossDisciplinaryEngine

                timeline = redacted.get("clinical_timeline", {}) or {}
                queries = CrossDisciplinaryEngine().build_prioritized_queries({
                    "medications": timeline.get("medications", []),
                    "labs": timeline.get("labs", []),
                    "diagnoses": timeline.get("diagnoses", []),
                    "genetics": timeline.get("genetics", []),
                })
            except Exception as e:
                logger.warning(
                    "Cross-disciplinary query fan-out failed (error_type=%s)",
                    type(e).__name__,
                )
            logger.info(
                "Pass 3 fan-out: %d cross-disciplinary queries", len(queries)
            )

            # analyze() runs both Pass 3 and Pass 4 internally
            results = dr.analyze(profile_summary, queries)

            self._profile.analysis.cross_disciplinary.extend(
                results.get("connections", [])
            )
            self._profile.analysis.flags.extend(results.get("flags", []))
            self._profile.analysis.literature.extend(
                results.get("literature", [])
            )

        except Exception as e:
            logger.warning(
                "Deep Research failed (error_type=%s)",
                type(e).__name__,
            )

        # Community insights
        self._wait_for_api_calls("community research")
        try:
            from src.analysis.community_insights import CommunityInsights
            community = CommunityInsights(api_key=gemini_key)

            meds = [{"name": m.name} for m in self._profile.clinical_timeline.medications]
            dxs = [{"name": d.name} for d in self._profile.clinical_timeline.diagnoses]

            insights = community.search(meds, dxs)
            self._profile.analysis.community_insights.extend(insights)
        except Exception as e:
            logger.warning(
                "Community insights not available (error_type=%s)",
                type(e).__name__,
            )

    # ── Pass 5: Clinical Validation ───────────────────────────

    def _pass_5_validation(self):
        """Validate findings against clinical databases."""
        try:
            from src.validation.validator import ClinicalValidator

            pubmed_key = None
            if self._vault:
                pubmed_key = self._vault.get_api_key("pubmed")

            validator = ClinicalValidator(pubmed_api_key=pubmed_key)
            results = validator.validate(self._profile)

            self._profile.analysis.drug_interactions.extend(
                results.get("drug_interactions", [])
            )

            for flag in results.get("adverse_events", []):
                self._profile.analysis.flags.append(flag)

            for flag in results.get("recalls", []):
                self._profile.analysis.flags.append(flag)

            self._profile.analysis.literature.extend(
                results.get("literature", [])
            )

        except Exception as e:
            logger.warning(
                "Clinical validation error (error_type=%s)",
                type(e).__name__,
            )

    # ── Pass 6: Report Generation ─────────────────────────────

    def _pass_6_report(self):
        """Generate the clinical report document."""
        try:
            from src.analysis.deep_insights import compute_all_deep_insights
            from src.models import PatientProfile
            from src.report.builder import ReportBuilder

            profile_data = self._profile.model_dump(mode="json")
            changed, insight_errors = compute_all_deep_insights(profile_data)
            self._profile = PatientProfile.model_validate(profile_data)
            if changed:
                self._save_profile_checkpoint()
            if insight_errors:
                logger.warning(
                    "Report continuing without some deep insights (types=%s)",
                    ",".join(sorted(insight_errors)),
                )

            builder = ReportBuilder()
            output_path = self.data_dir / "reports" / (
                f"clinical_report_{int(time.time())}.docx"
            )

            redaction_summary = self._db.get_redaction_summary() if self._db else []

            builder.generate(
                profile=self._profile,
                output_path=output_path,
                redaction_summary=redaction_summary,
                file_count=len(self._profile.processed_files),
            )

            logger.info("Clinical report generated locally")

        except Exception as e:
            logger.warning(
                "Report generation failed (error_type=%s)",
                type(e).__name__,
            )

    # ── Helpers ───────────────────────────────────────────────

    def _publish_profile_snapshot(self):
        """Serialize the current profile and publish to the UI layer."""
        try:
            snapshot = self._profile.model_dump(mode="json")
            self._save_profile_checkpoint()
            self._on_profile_update(snapshot)
            # Signal the SSE stream so the frontend refreshes
            item_count = self._clinical_item_count()
            self._progress(
                "profile_updated",
                f"Dashboard updated — {item_count} clinical items found so far",
                -1,
            )
        except Exception as e:
            logger.warning(
                "Profile snapshot failed (error_type=%s)",
                type(e).__name__,
            )
            raise RuntimeError("Profile snapshot persistence failed") from None

    def _save_profile_checkpoint(self):
        """Persist the current profile so chunked progress survives crashes."""
        if not self._vault or not self._profile:
            return

        try:
            self._profile.updated_at = datetime.now()
            self._vault.save_profile(self._profile.model_dump(mode="json"))
        except Exception as e:
            logger.warning(
                "Profile checkpoint save failed (error_type=%s)",
                type(e).__name__,
            )
            raise RuntimeError("Profile checkpoint save failed") from None

    def _clinical_item_count(self) -> int:
        """Count all timeline items shown to the user across extraction passes."""
        tl = self._profile.clinical_timeline
        collections = (
            tl.medications,
            tl.labs,
            tl.imaging,
            tl.diagnoses,
            tl.procedures,
            tl.allergies,
            tl.genetics,
            tl.notes,
            tl.vitals,
            tl.symptoms,
        )
        return sum(len(items) for items in collections)

    def _profile_has_extractions_for_source(self, source_file: str) -> bool:
        """Return whether a resumed file already has durable timeline data."""
        timeline = self._profile.clinical_timeline
        collections = (
            timeline.medications,
            timeline.labs,
            timeline.diagnoses,
            timeline.procedures,
            timeline.allergies,
            timeline.genetics,
            timeline.notes,
        )
        return any(
            getattr(getattr(item, "provenance", None), "source_file", None)
            == source_file
            for items in collections
            for item in items
        )

    @staticmethod
    def _fingerprint(item, key: str) -> str:
        """Build a deduplication fingerprint for a clinical item.

        Uses the identity fields that distinguish unique clinical events
        (ignoring provenance metadata which differs across extraction runs).
        """
        def _norm(val):
            """Normalise a field value for comparison."""
            if val is None:
                return ""
            return str(val).strip().lower()

        if key == "medications":
            return f"med|{_norm(item.name)}|{_norm(item.dosage)}|{_norm(item.frequency)}|{_norm(item.route)}"
        if key == "labs":
            loinc_code = _norm(item.loinc_code)
            normalized_name = re.sub(
                r"[^a-z0-9]+",
                " ",
                _norm(item.name),
            ).strip()
            identity = (
                f"loinc:{loinc_code}"
                if loinc_code
                else f"name:{normalized_name}"
            )
            return (
                f"lab|{identity}|{_norm(item.value)}|{_norm(item.unit)}|"
                f"{_norm(item.test_date)}"
            )
        if key == "diagnoses":
            return f"dx|{_norm(item.name)}|{_norm(item.date_diagnosed)}|{_norm(item.status)}"
        if key == "procedures":
            return f"proc|{_norm(item.name)}|{_norm(item.procedure_date)}"
        if key == "allergies":
            return f"allergy|{_norm(item.allergen)}|{_norm(item.reaction)}"
        if key == "genetics":
            return f"gene|{_norm(item.gene)}|{_norm(item.variant)}"
        if key == "notes":
            return f"note|{_norm(item.summary)[:120]}|{_norm(item.note_date)}"
        # Fallback: use the full model dump
        return f"{key}|{item.model_dump_json(exclude={'provenance'})}"

    def _standardize_lab(self, lab: LabResult) -> LabResult:
        """Attach local LOINC identity/reference metadata when confidently known."""
        if self._loinc_db is None:
            from src.standardization.loinc import LOINCDatabase

            self._loinc_db = LOINCDatabase(data_dir=self.data_dir)

        match = None
        if lab.loinc_code:
            match = self._loinc_db.lookup_by_code(lab.loinc_code)
        if match is None and lab.name:
            match = self._loinc_db.lookup(lab.name)
        if not match:
            return lab

        lab.loinc_code = match.get("code") or lab.loinc_code
        if lab.reference_low is None:
            lab.reference_low = match.get("reference_low")
        if lab.reference_high is None:
            lab.reference_high = match.get("reference_high")
        return lab

    def _append_extraction_results(self, results: dict):
        """Append extracted timeline items, skipping duplicates.

        Builds a fingerprint set from existing items on first call,
        then checks each new item against it before appending.
        """
        timeline = self._profile.clinical_timeline
        model_map = (
            ("medications", Medication, timeline.medications),
            ("labs", LabResult, timeline.labs),
            ("diagnoses", Diagnosis, timeline.diagnoses),
            ("procedures", Procedure, timeline.procedures),
            ("allergies", Allergy, timeline.allergies),
            ("genetics", GeneticVariant, timeline.genetics),
            ("notes", ClinicalNote, timeline.notes),
        )

        for key, model_cls, target in model_map:
            # Build fingerprint set from items already in the profile
            existing_fps = set()
            for existing in target:
                try:
                    if key == "labs":
                        self._standardize_lab(existing)
                    existing_fps.add(self._fingerprint(existing, key))
                except Exception:
                    pass  # If fingerprinting fails, allow the item through

            skipped = 0
            for item in results.get(key, []):
                try:
                    parsed = (
                        item
                        if isinstance(item, model_cls)
                        else model_cls.model_validate(item)
                    )
                    if key == "labs":
                        parsed = self._standardize_lab(parsed)
                    fp = self._fingerprint(parsed, key)
                    if fp in existing_fps:
                        skipped += 1
                        continue
                    existing_fps.add(fp)
                    target.append(parsed)
                except Exception as e:
                    logger.warning(
                        "Dropped %s during merge "
                        "(validation_error_type=%s)",
                        key[:-1] if key.endswith("s") else key,
                        type(e).__name__,
                    )

            if skipped:
                logger.info(
                    "Dedup: skipped %d duplicate %s (already in profile)",
                    skipped, key,
                )

    def _merge_extraction_results(self, results: dict, item: dict):
        """Merge extracted clinical data into the profile."""
        del item  # legacy argument retained for compatibility
        self._append_extraction_results(results)

    def _init_components(self):
        """Initialize database and encryption vault."""
        from src.database import Database
        from src.encryption import EncryptedVault

        self._db = Database(self.data_dir / "cih.db")
        self._vault = EncryptedVault(self.data_dir, self._passphrase)

    def _start_caffeinate(self):
        """Prevent macOS from sleeping during analysis."""
        try:
            self._caffeinate_proc = subprocess.Popen(
                ["caffeinate", "-dims"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.debug("caffeinate started — system will stay awake")
        except Exception:
            logger.debug("caffeinate not available (non-macOS?)")

    def _stop_caffeinate(self):
        """Release caffeinate when analysis is done."""
        if self._caffeinate_proc:
            self._caffeinate_proc.terminate()
            self._caffeinate_proc = None
            logger.debug("caffeinate stopped")

    # ── Session Management ────────────────────────────────────

    def clear_session(self):
        """Clear all patient data for a new session."""
        self._init_components()
        self._db.clear_patient_data()
        self._vault.clear_patient_profile()
        logger.info("Session cleared — ready for new patient data")
