"""
Clinical Intelligence Hub — 6-Pass Pipeline Orchestrator

Coordinates the entire analysis pipeline:
  Pass 0: Preprocessing (OCR, dedup, classification)
  Pass 1a: MedGemma 27B text extraction
  Pass 1b: MedGemma 4B vision analysis
  Pass 1c: MONAI clinical detection
  Pass 1.5: PII redaction
  Pass 2: Gemini 3.1 Pro Preview gap-filling
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

        try:
            self._init_components()
            self._progress("init", "Pipeline initialized", 0)

            # Load or create profile
            try:
                self._profile = self._vault.load_profile()
                if self._profile and isinstance(self._profile, dict):
                    self._profile = PatientProfile(**self._profile)
            except Exception as e:
                logger.warning(
                    f"Could not load existing profile ({e}). "
                    "Starting fresh."
                )
                self._profile = None
            if not self._profile:
                self._profile = PatientProfile()

            run_id = f"run_{int(time.time())}"
            self._db.start_pipeline_run(run_id)

            total_steps = 8  # approximate number of major passes
            step = 0

            # ── Pass 0: Preprocessing ──
            step += 1
            self._progress("pass_0", "Classifying and preprocessing files...",
                           int(step / total_steps * 100))
            self._log(f"Pass 0: Processing {len(input_files)} file(s)...")
            preprocessed = self._pass_0_preprocess(input_files)
            for item in preprocessed:
                self._log(f"  \u2713 {item.get('filename', '?')}: "
                          f"{len(item.get('text', '')):,} chars, "
                          f"{len(item.get('pages', []))} pages")

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
            logger.error(f"Pipeline failed: {e}")
            self._progress("error", f"Pipeline error: {str(e)}", -1)
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
                    self._profile.processed_files.append(pf)

                else:
                    self._record_local_error(
                        f"{filepath.name} was duplicate, unsupported, or could not "
                        "be preprocessed"
                    )

            except Exception as e:
                logger.error(f"Preprocessing failed for {filepath.name}: {e}")
                self._record_local_error(
                    f"Preprocessing failed for {filepath.name}: {e}"
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

            extractor = TextExtractor(
                progress_callback=self._progress,
                pause_event=self._pause_event,
                on_chunk_complete=_on_chunk_complete,
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
                            f"{filename} did not produce enough readable text"
                        )
                    continue

                # TextExtractor expects pages list [{page, text}]
                if not pages:
                    pages = [{"page": 1, "text": text}]

                # Optional page cap (0 = no limit, process everything)
                total_pages = len(pages)
                if MAX_PAGES_PER_FILE > 0 and total_pages > MAX_PAGES_PER_FILE:
                    logger.info(
                        f"Capping extraction to first {MAX_PAGES_PER_FILE} of "
                        f"{total_pages} pages for {item.get('filename')} "
                        f"(set MEDPREP_MAX_PAGES=0 to process all pages)"
                    )
                    pages = pages[:MAX_PAGES_PER_FILE]
                    self._record_local_error(
                        f"{filename} was only partially processed "
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
                    results = extractor.extract(
                        pages=pages,
                        source_file=filename,
                    )
                    item_count = sum(
                        len(values)
                        for values in results.values()
                        if isinstance(values, list)
                    ) if isinstance(results, dict) else 0
                    if requires_text_extraction and item_count == 0:
                        self._record_local_error(
                            f"Local extraction returned no clinical data for {filename}"
                        )
                    # No need to call _merge_extraction_results here —
                    # merging happens per-chunk via _on_chunk_complete
                except Exception as e:
                    logger.error(f"Text extraction failed for {filename}: {e}")
                    self._log(f"  Error: {e}")
                    self._record_local_error(
                        f"Text extraction failed for {filename}: {e}"
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
            for filename in sorted(image_only_sources - processed_image_sources):
                self._record_local_error(
                    f"Local image analysis returned no usable data for {filename}"
                )

            # Publish updated profile so dashboard shows imaging findings
            self._publish_profile_snapshot()

        except ImportError as e:
            logger.warning(f"ImagePipeline not available — skipping: {e}")
            self._log("  Image analysis not available — skipped")
            if image_only_sources:
                self._record_local_error("Local image analysis is not available")
        except Exception as e:
            logger.error(f"Image analysis failed: {e}")
            self._log(f"  Image analysis error: {e}")
            if image_only_sources:
                self._record_local_error(f"Local image analysis failed: {e}")

    # ── Pass 1.5: PII Redaction ───────────────────────────────

    def _pass_1_5_redaction(self):
        """Redact PII before cloud analysis.

        Creates self._redacted_profile_dict — a deep copy of the profile
        with all PII stripped. The original profile keeps raw data;
        only the redacted copy is sent to cloud APIs.
        """
        try:
            from src.privacy.redactor import PIIRedactor

            redactor = PIIRedactor(db=self._db)
            profile_dict = self._profile.model_dump(mode="json")
            self._redacted_profile_dict = redactor.redact_dict(
                profile_dict, source_file="pipeline_pass_1.5"
            )
            summary = redactor.get_redaction_summary()
            count = summary.get("total", 0) if summary else 0
            logger.info(f"PII redaction complete — {count} entities redacted")
            return True
        except Exception as e:
            logger.error(
                "PII redaction failed — external API calls will be blocked: %s", e
            )
            self._redacted_profile_dict = None
            self._record_local_error(f"PII redaction failed: {e}")
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

        # Use redacted profile for all cloud calls
        redacted = self._redacted_profile_dict or self._profile.model_dump(mode="json")

        # Pass 2: Gemini fallback gap-filling
        try:
            from src.analysis.gemini_fallback import GeminiFallback
            fallback = GeminiFallback(api_key=gemini_key)
            logger.info("Pass 2: Gemini 3 Flash gap-filling available")
        except Exception as e:
            logger.warning(f"Gemini fallback not available: {e}")

        # Pass 3-4: Deep Research
        self._wait_for_api_calls("Gemini 3 Flash research")
        try:
            from src.analysis.deep_research import DeepResearch
            dr = DeepResearch(api_key=gemini_key)

            import json
            profile_summary = json.dumps(redacted, indent=2, default=str)

            # analyze() runs both Pass 3 and Pass 4 internally
            results = dr.analyze(profile_summary, [])

            self._profile.analysis.cross_disciplinary.extend(
                results.get("connections", [])
            )
            self._profile.analysis.flags.extend(results.get("flags", []))
            self._profile.analysis.literature.extend(
                results.get("literature", [])
            )

        except Exception as e:
            logger.warning(f"Deep Research failed: {e}")

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
            logger.warning(f"Community insights not available: {e}")

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
            logger.warning(f"Clinical validation error: {e}")

    # ── Pass 6: Report Generation ─────────────────────────────

    def _pass_6_report(self):
        """Generate the clinical report document."""
        try:
            from src.report.builder import ReportBuilder

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

            logger.info(f"Report generated: {output_path}")

        except Exception as e:
            logger.warning(f"Report generation failed: {e}")

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
            logger.warning(f"Profile snapshot failed: {e}")

    def _save_profile_checkpoint(self):
        """Persist the current profile so chunked progress survives crashes."""
        if not self._vault or not self._profile:
            return

        try:
            self._profile.updated_at = datetime.now()
            self._vault.save_profile(self._profile.model_dump(mode="json"))
        except Exception as e:
            logger.warning(f"Profile checkpoint save failed: {e}")

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
            return f"lab|{_norm(item.name)}|{_norm(item.value)}|{_norm(item.unit)}|{_norm(item.test_date)}"
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

    def _append_extraction_results(self, results: dict):
        """Append extracted timeline items, skipping duplicates.

        Builds a fingerprint set from existing items on first call,
        then checks each new item against it before appending.
        """
        timeline = self._profile.clinical_timeline
        model_map = (
            ("medications", Medication, timeline.medications, "name"),
            ("labs", LabResult, timeline.labs, "name"),
            ("diagnoses", Diagnosis, timeline.diagnoses, "name"),
            ("procedures", Procedure, timeline.procedures, "name"),
            ("allergies", Allergy, timeline.allergies, "allergen"),
            ("genetics", GeneticVariant, timeline.genetics, "gene"),
            ("notes", ClinicalNote, timeline.notes, "summary"),
        )

        for key, model_cls, target, label_field in model_map:
            # Build fingerprint set from items already in the profile
            existing_fps = set()
            for existing in target:
                try:
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
                    fp = self._fingerprint(parsed, key)
                    if fp in existing_fps:
                        skipped += 1
                        continue
                    existing_fps.add(fp)
                    target.append(parsed)
                except Exception as e:
                    label = "?"
                    if isinstance(item, dict):
                        label = item.get(label_field, "?")
                    else:
                        label = getattr(item, label_field, "?")
                    logger.warning(
                        "Dropped %s during merge (validation failed): %s — %s",
                        key[:-1] if key.endswith("s") else key,
                        label,
                        e,
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
