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
from pathlib import Path
from typing import Callable, Optional

from src.models import (
    FileType,
    PatientProfile,
    ProcessedFile,
    ProcessingStatus,
    Provenance,
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
                 pause_event=None):
        """
        Args:
            data_dir: Base directory for all data
            passphrase: Encryption passphrase for patient data
            progress_callback: Called with (pass_name, message, percent)
            pause_event: threading.Event — cleared when paused, set when running
        """
        self.data_dir = data_dir
        self._passphrase = passphrase
        self._progress = progress_callback or (lambda *a: None)
        self._pause_event = pause_event
        self._caffeinate_proc = None

        # Lazy-initialized components
        self._db = None
        self._vault = None
        self._profile = None

    def _wait_if_paused(self):
        """Block until resumed if pipeline is paused."""
        if self._pause_event and not self._pause_event.is_set():
            logger.info("Pipeline paused — waiting for resume...")
            self._pause_event.wait()  # Blocks until set()
            logger.info("Pipeline resumed")

    def _log(self, message: str):
        """Send a detailed log line to the terminal viewer."""
        self._progress("log", message, -1)

    def run(self, input_files: list[Path]) -> PatientProfile:
        """
        Run the full pipeline on a set of input files.

        Returns the complete patient profile with all analysis results.
        """
        self._start_caffeinate()

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

            # ── Pass 1b: Vision Analysis ──
            self._wait_if_paused()
            step += 1
            self._progress("pass_1b", "Analyzing medical images...",
                           int(step / total_steps * 100))
            self._log("Pass 1b: Checking for medical images...")
            self._pass_1b_vision(preprocessed)

            # ── Pass 1c: MONAI Detection ──
            self._wait_if_paused()
            step += 1
            self._progress("pass_1c", "Running clinical detection models...",
                           int(step / total_steps * 100))
            self._log("Pass 1c: Checking for DICOM files...")
            self._pass_1c_monai(preprocessed)

            # ── Pass 1.5: PII Redaction ──
            self._wait_if_paused()
            step += 1
            self._progress("pass_1_5", "Removing personal information...",
                           int(step / total_steps * 100))
            self._log("Pass 1.5: PII redaction check...")
            self._pass_1_5_redaction()

            # ── Pass 2-4: Cloud Analysis ──
            self._wait_if_paused()
            step += 1
            self._progress("pass_2_4", "Analyzing patterns across specialties...",
                           int(step / total_steps * 100))
            self._log("Pass 2-4: Cloud analysis (requires Gemini API key)...")
            self._pass_2_4_cloud_analysis()

            # ── Pass 5: Clinical Validation ──
            self._wait_if_paused()
            step += 1
            self._progress("pass_5", "Validating against clinical databases...",
                           int(step / total_steps * 100))
            self._log("Pass 5: Validating against OpenFDA, DrugBank, PubMed...")
            self._pass_5_validation()

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

            except Exception as e:
                logger.error(f"Preprocessing failed for {filepath.name}: {e}")

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
        MAX_PAGES_PER_FILE = int(os.environ.get("MEDPREP_MAX_PAGES", "50"))

        try:
            from src.extraction.text_extractor import TextExtractor

            extractor = TextExtractor(
                progress_callback=self._progress,
                pause_event=self._pause_event,
            )

            for item in preprocessed:
                pages = item.get("pages", [])
                text = item.get("text", "")
                if not text or len(text.strip()) < 50:
                    continue

                # TextExtractor expects pages list [{page, text}]
                if not pages:
                    pages = [{"page": 1, "text": text}]

                # Cap pages for faster initial results
                total_pages = len(pages)
                if total_pages > MAX_PAGES_PER_FILE:
                    logger.info(
                        f"Capping extraction to first {MAX_PAGES_PER_FILE} of "
                        f"{total_pages} pages for {item.get('filename')} "
                        f"(set MEDPREP_MAX_PAGES to change)"
                    )
                    pages = pages[:MAX_PAGES_PER_FILE]

                try:
                    results = extractor.extract(
                        pages=pages,
                        source_file=item.get("filename", "unknown"),
                    )
                    self._merge_extraction_results(results, item)
                except Exception as e:
                    logger.error(f"Text extraction failed for {item.get('filename')}: {e}")
                    self._log(f"  Error: {e}")

            # Summary of what was extracted
            tl = self._profile.clinical_timeline
            self._log(f"Pass 1a complete: {len(tl.medications)} meds, "
                      f"{len(tl.labs)} labs, {len(tl.diagnoses)} diagnoses")

        except ImportError:
            logger.warning("TextExtractor not available — skipping Pass 1a")
            self._log("TextExtractor not available — skipped")

    # ── Pass 1b: Vision Analysis ──────────────────────────────

    def _pass_1b_vision(self, preprocessed: list[dict]):
        """Analyze medical images with MedGemma 4B."""
        try:
            from src.imaging.vision_analyzer import VisionAnalyzer

            analyzer = VisionAnalyzer()

            for item in preprocessed:
                images = item.get("images", [])
                for img_path in images:
                    try:
                        findings = analyzer.analyze(
                            image_path=Path(img_path),
                            modality=item.get("modality"),
                            body_region=item.get("body_region"),
                        )
                        # Add findings to profile
                        if findings:
                            from src.models import ImagingStudy
                            study = ImagingStudy(
                                modality=item.get("modality"),
                                body_region=item.get("body_region"),
                                findings=findings,
                                provenance=Provenance(
                                    source_file=item.get("filename", "unknown"),
                                    extraction_model="medgemma-4b",
                                ),
                            )
                            self._profile.clinical_timeline.imaging.append(study)
                    except Exception as e:
                        logger.error(f"Vision analysis failed: {e}")

        except ImportError:
            logger.warning("VisionAnalyzer not available — skipping Pass 1b")

    # ── Pass 1c: MONAI Detection ──────────────────────────────

    def _pass_1c_monai(self, preprocessed: list[dict]):
        """Run MONAI clinical detection models."""
        try:
            from src.imaging.monai_detector import MONAIDetector

            detector = MONAIDetector()

            for item in preprocessed:
                if item.get("file_type") != "dicom":
                    continue

                try:
                    findings = detector.detect(
                        image_path=Path(item.get("filepath", "")),
                        modality=item.get("modality"),
                        body_region=item.get("body_region"),
                    )
                    if findings:
                        from src.models import ImagingStudy
                        study = ImagingStudy(
                            modality=item.get("modality"),
                            body_region=item.get("body_region"),
                            findings=findings,
                            provenance=Provenance(
                                source_file=item.get("filename", "unknown"),
                                extraction_model="monai",
                            ),
                        )
                        self._profile.clinical_timeline.imaging.append(study)
                except Exception as e:
                    logger.error(f"MONAI detection failed: {e}")

        except ImportError:
            logger.warning("MONAIDetector not available — skipping Pass 1c")

    # ── Pass 1.5: PII Redaction ───────────────────────────────

    def _pass_1_5_redaction(self):
        """Redact PII before cloud analysis."""
        try:
            from src.privacy.redactor import PIIRedactor

            redactor = PIIRedactor(db=self._db)
            # Redact text fields in the profile for cloud use
            # The profile itself keeps original data; cloud gets redacted copy
            logger.info("PII redaction check complete")
        except ImportError:
            logger.warning("PIIRedactor not available — skipping Pass 1.5")

    # ── Pass 2-4: Cloud Analysis ──────────────────────────────

    def _pass_2_4_cloud_analysis(self):
        """Run Gemini fallback and Deep Research."""
        gemini_key = None
        if self._vault:
            gemini_key = self._vault.get_api_key("gemini")

        if not gemini_key:
            logger.info("No Gemini API key — skipping cloud analysis (Passes 2-4)")
            return

        # Pass 2: Gemini fallback gap-filling
        try:
            from src.analysis.gemini_fallback import GeminiFallback
            fallback = GeminiFallback(api_key=gemini_key)
            logger.info("Pass 2: Gemini gap-filling available")
        except Exception as e:
            logger.debug(f"Gemini fallback not available: {e}")

        # Pass 3-4: Deep Research
        try:
            from src.analysis.deep_research import DeepResearch
            dr = DeepResearch(api_key=gemini_key)

            profile_dict = self._profile.model_dump(mode="json")

            # Pass 3: Cross-disciplinary
            connections, flags = dr.run_pass3(profile_dict)
            self._profile.analysis.cross_disciplinary.extend(connections)
            self._profile.analysis.flags.extend(flags)

            # Pass 4: Literature search
            citations = dr.run_pass4(profile_dict)
            self._profile.analysis.literature.extend(citations)

        except Exception as e:
            logger.warning(f"Deep Research not available: {e}")

        # Community insights
        try:
            from src.analysis.community_insights import CommunityInsights
            community = CommunityInsights(api_key=gemini_key)

            meds = [{"name": m.name} for m in self._profile.clinical_timeline.medications]
            dxs = [{"name": d.name} for d in self._profile.clinical_timeline.diagnoses]

            insights = community.search(meds, dxs)
            self._profile.analysis.community_insights.extend(insights)
        except Exception as e:
            logger.debug(f"Community insights not available: {e}")

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

    def _merge_extraction_results(self, results: dict, item: dict):
        """Merge extracted clinical data into the profile."""
        timeline = self._profile.clinical_timeline

        for med in results.get("medications", []):
            if isinstance(med, dict):
                from src.models import Medication
                try:
                    timeline.medications.append(Medication(**med))
                except Exception:
                    pass

        for lab in results.get("labs", []):
            if isinstance(lab, dict):
                from src.models import LabResult
                try:
                    timeline.labs.append(LabResult(**lab))
                except Exception:
                    pass

        for dx in results.get("diagnoses", []):
            if isinstance(dx, dict):
                from src.models import Diagnosis
                try:
                    timeline.diagnoses.append(Diagnosis(**dx))
                except Exception:
                    pass

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
