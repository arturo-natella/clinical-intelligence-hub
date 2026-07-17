"""
Clinical Intelligence Hub — Unified Image Pipeline

Replaces the broken Pass 1b/1c orchestration with a single coordinator
that handles ALL image sources:

  1. PDF embedded images — extracted via PyMuPDF get_images()
  2. Standalone images (JPG/PNG) — used as-is
  3. DICOM files — metadata extracted, converted to PNG for vision

Classification:
  - DICOM headers provide modality + body region (most reliable)
  - Filename heuristics fill in gaps for non-DICOM images

Analysis:
  - MedGemma 4B vision analysis runs on ALL images
  - MONAI quantitative analysis runs on DICOM only (needs volumetric data)
  - Models loaded sequentially to stay under 36GB peak memory
"""

import gc
import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from src.models import ImagingFinding, ImagingStudy, PatientProfile, Provenance

logger = logging.getLogger("CIH-ImagePipeline")


@dataclass
class MedicalImage:
    """Internal routing model for images being processed."""
    image_path: Path
    source_file: str
    source_page: Optional[int] = None
    source_type: str = "standalone"   # "pdf_embedded", "standalone", "dicom"
    modality: Optional[str] = None
    body_region: Optional[str] = None
    original_dicom_path: Optional[Path] = None
    dicom_metadata: Optional[dict] = field(default_factory=dict)


@dataclass
class ImageProcessingSummary:
    """Observable outcome used by the paid-API safety gate."""

    images_found: int = 0
    vision_succeeded: int = 0
    vision_failed: int = 0
    errors: list[str] = field(default_factory=list)


class ImagePipeline:
    """
    Unified image analysis pipeline.

    Collects images from all preprocessed files, classifies them,
    routes to MedGemma 4B and MONAI, and writes ImagingStudy entries
    into the patient profile.
    """

    def __init__(self, data_dir: Path,
                 progress_callback: Callable = None,
                 pause_event=None):
        self.data_dir = data_dir
        self._progress = progress_callback or (lambda *a: None)
        self._pause_event = pause_event
        self._image_dir = data_dir / "extracted_images"
        self._errors: list[str] = []

    def _log(self, message: str):
        self._progress("log", message, -1)

    def _record_error(self, message: str):
        if message not in self._errors:
            self._errors.append(message)
        logger.error(message)

    def process(self, preprocessed: list[dict],
                profile: PatientProfile) -> ImageProcessingSummary:
        """
        Process all images from all preprocessed files.

        Modifies profile.clinical_timeline.imaging in place.
        """
        self._errors = []

        # 1. Collect images from all sources
        images = self._collect_images(preprocessed)

        if not images:
            logger.info("No medical images found — skipping image analysis")
            self._log("  No medical images found — skipped")
            return ImageProcessingSummary(errors=list(self._errors))

        logger.info(f"Found {len(images)} medical image(s) to analyze")
        self._log(f"  Found {len(images)} medical image(s) to analyze")

        # 2. Classify modality + body region
        self._classify_images(images)

        # 3. MedGemma 4B vision analysis — all images
        vision_succeeded, vision_failed = self._vision_analysis(images, profile)

        # Free memory before loading MONAI
        gc.collect()
        try:
            import torch
            if hasattr(torch, "mps"):
                torch.mps.empty_cache()
        except ImportError:
            pass

        # 4. MONAI quantitative analysis — DICOM only
        self._monai_analysis(images, profile)

        # Summary
        study_count = len(profile.clinical_timeline.imaging)
        finding_count = sum(
            len(s.findings) for s in profile.clinical_timeline.imaging
        )
        logger.info(
            f"Image analysis complete: {study_count} studies, "
            f"{finding_count} findings"
        )
        self._log(
            f"  Image analysis complete: {study_count} studies, "
            f"{finding_count} findings"
        )
        return ImageProcessingSummary(
            images_found=len(images),
            vision_succeeded=vision_succeeded,
            vision_failed=vision_failed,
            errors=list(self._errors),
        )

    # ── Collection ────────────────────────────────────────

    def _collect_images(self, preprocessed: list[dict]) -> list[MedicalImage]:
        """Extract images from PDFs, standalone files, and DICOM."""
        images = []

        for item in preprocessed:
            file_type = item.get("file_type", "")
            filepath = item.get("filepath", "")
            filename = item.get("filename", "unknown")

            # Standalone image files
            if file_type == "image":
                path = Path(filepath)
                if path.exists():
                    images.append(MedicalImage(
                        image_path=path,
                        source_file=filename,
                        source_type="standalone",
                    ))
                    self._log(f"  Collected standalone image: {filename}")

            # DICOM files — extract metadata + convert to PNG
            elif file_type == "dicom":
                dicom_images = self._process_dicom(Path(filepath), filename)
                images.extend(dicom_images)

            # PDFs — extract embedded images
            elif file_type in ("pdf_text", "pdf_scanned"):
                embedded = self._extract_pdf_images(Path(filepath), filename)
                images.extend(embedded)

        return images

    def _process_dicom(self, dicom_path: Path, filename: str) -> list[MedicalImage]:
        """Extract metadata from DICOM and convert to PNG for vision analysis."""
        try:
            from src.extraction.dicom_converter import DICOMConverter
            converter = DICOMConverter()

            # Extract metadata (headers only, no pixel data)
            metadata = converter.extract_metadata(dicom_path)

            # Convert pixel data to PNG for MedGemma 4B
            self._image_dir.mkdir(parents=True, exist_ok=True)
            png_path = converter.convert_to_png(dicom_path, self._image_dir)

            if png_path and png_path.exists():
                self._log(
                    f"  DICOM: {filename} → "
                    f"{metadata.get('modality', '?')} of "
                    f"{metadata.get('body_part', '?')}"
                )
                return [MedicalImage(
                    image_path=png_path,
                    source_file=filename,
                    source_type="dicom",
                    modality=metadata.get("modality"),
                    body_region=metadata.get("body_part"),
                    original_dicom_path=dicom_path,
                    dicom_metadata=metadata,
                )]
            else:
                logger.warning(
                    f"DICOM conversion produced no image for {filename} — "
                    "file may lack pixel data"
                )
                return []

        except ImportError:
            self._record_error(
                f"DICOM processing failed for {filename}: pydicom is not installed"
            )
            return []
        except Exception as e:
            self._record_error(f"DICOM processing failed for {filename}: {e}")
            return []

    def _extract_pdf_images(
        self, pdf_path: Path, source_filename: str
    ) -> list[MedicalImage]:
        """Extract displayed images from a PDF using PyMuPDF.

        ``Page.get_images()`` returns every image resource declared by a PDF,
        including unused resources. Some clinical exports declare hundreds of
        resources on every page. ``get_image_info()`` returns only images that
        are actually displayed. We hash the rendered crop so identical repeats
        are skipped while images with different visible annotations are kept.
        """
        try:
            import fitz
        except ImportError:
            self._record_error(
                f"PDF image extraction failed for {source_filename}: "
                "PyMuPDF is not installed"
            )
            return []

        images = []
        doc = None
        try:
            doc = fitz.open(str(pdf_path))
            img_count = 0
            seen_rendered_images = set()

            for page_num in range(len(doc)):
                page = doc[page_num]
                try:
                    image_list = page.get_image_info(hashes=False, xrefs=False)
                except Exception as e:
                    self._record_error(
                        f"Could not inspect displayed images on page "
                        f"{page_num + 1} of {source_filename}: {e}"
                    )
                    continue

                for img_idx, img_info in enumerate(image_list):
                    try:
                        # Skip small images (icons, logos, decorative elements)
                        width = int(img_info.get("width") or 0)
                        height = int(img_info.get("height") or 0)
                        bbox = fitz.Rect(img_info.get("bbox"))
                        if (
                            width < 100
                            or height < 100
                            or bbox.width < 40
                            or bbox.height < 40
                        ):
                            continue

                        # Render the displayed rectangle instead of extracting
                        # a raw xref. This avoids unused resources and preserves
                        # masks/overlays exactly as the patient sees them.
                        source_scale = max(
                            width / max(bbox.width, 1),
                            height / max(bbox.height, 1),
                        )
                        zoom = min(3.0, max(1.0, source_scale))
                        pix = page.get_pixmap(
                            matrix=fitz.Matrix(zoom, zoom),
                            clip=bbox,
                            alpha=False,
                        )

                        rendered_digest = hashlib.sha256(pix.samples).digest()
                        if rendered_digest in seen_rendered_images:
                            pix = None
                            continue

                        # Save as PNG
                        self._image_dir.mkdir(parents=True, exist_ok=True)
                        stem = pdf_path.stem
                        out_path = (
                            self._image_dir
                            / f"{stem}_p{page_num + 1}_display{img_idx}.png"
                        )
                        pix.save(str(out_path))
                        pix = None  # Free memory
                        seen_rendered_images.add(rendered_digest)

                        images.append(MedicalImage(
                            image_path=out_path,
                            source_file=source_filename,
                            source_page=page_num + 1,
                            source_type="pdf_embedded",
                        ))
                        img_count += 1

                    except Exception as e:
                        self._record_error(
                            f"Failed to extract image {img_idx} from "
                            f"page {page_num + 1} of {source_filename}: {e}"
                        )

            if img_count > 0:
                logger.info(
                    f"Extracted {img_count} embedded image(s) "
                    f"from {source_filename}"
                )
                self._log(
                    f"  Extracted {img_count} embedded image(s) "
                    f"from {source_filename}"
                )

        except Exception as e:
            self._record_error(
                f"PDF image extraction failed for {source_filename}: {e}"
            )
        finally:
            if doc is not None:
                doc.close()

        return images

    # ── Classification ────────────────────────────────────

    def _classify_images(self, images: list[MedicalImage]):
        """Classify modality and body region using DICOM headers and filename heuristics."""

        modality_keywords = {
            "ct": "CT", "cat_scan": "CT", "catscan": "CT",
            "mri": "MRI", "mr_": "MRI",
            "xray": "X-ray", "x-ray": "X-ray", "x_ray": "X-ray",
            "radiograph": "X-ray",
            "ultrasound": "Ultrasound", "sono": "Ultrasound",
            "echo": "Ultrasound",
            "mammogram": "Mammography", "mammo": "Mammography",
            "pet": "PET", "nuclear": "Nuclear Medicine",
            "dexa": "DEXA", "bone_density": "DEXA",
            "fluoro": "Fluoroscopy",
            "pathology": "Pathology", "histo": "Pathology",
            "biopsy": "Pathology", "microscop": "Pathology",
            "endoscop": "Endoscopy", "colonoscop": "Endoscopy",
        }

        body_keywords = {
            "chest": "CHEST", "thorax": "CHEST", "lung": "CHEST",
            "cardiac": "CHEST", "heart": "CHEST",
            "abdomen": "ABDOMEN", "abdominal": "ABDOMEN",
            "liver": "ABDOMEN", "kidney": "ABDOMEN", "renal": "ABDOMEN",
            "head": "HEAD", "brain": "HEAD", "cranial": "HEAD",
            "spine": "SPINE", "lumbar": "SPINE", "cervical": "SPINE",
            "thoracic_spine": "SPINE", "sacral": "SPINE",
            "pelvis": "PELVIS", "hip": "PELVIS",
            "knee": "KNEE", "shoulder": "SHOULDER",
            "ankle": "ANKLE", "wrist": "WRIST",
            "hand": "HAND", "foot": "FOOT",
            "neck": "NECK", "thyroid": "NECK",
        }

        for img in images:
            # DICOM images already classified from headers
            if img.modality and img.body_region:
                continue

            # Build searchable string from filename + image path
            searchable = (
                img.source_file.lower().replace(" ", "_")
                + "_"
                + img.image_path.stem.lower().replace(" ", "_")
            )

            if not img.modality:
                for keyword, modality in modality_keywords.items():
                    if keyword in searchable:
                        img.modality = modality
                        break

            if not img.body_region:
                for keyword, region in body_keywords.items():
                    if keyword in searchable:
                        img.body_region = region
                        break

    # ── Vision Analysis (MedGemma 4B) ─────────────────────

    def _vision_analysis(self, images: list[MedicalImage],
                         profile: PatientProfile) -> tuple[int, int]:
        """Run MedGemma 4B vision analysis on all images."""
        try:
            from src.imaging.vision_analyzer import VisionAnalyzer
        except ImportError:
            error = "VisionAnalyzer is not available"
            self._record_error(error)
            self._log("  VisionAnalyzer not available — skipped")
            return 0, len(images)

        analyzer = VisionAnalyzer()
        if not analyzer._available:
            error = analyzer.availability_error or "MedGemma 4B is not available"
            self._record_error(error)
            self._log("  MedGemma 4B not available — skipped")
            return 0, len(images)

        self._log(f"  Running MedGemma 4B vision on {len(images)} image(s)...")
        succeeded = 0
        failed = 0

        for i, img in enumerate(images, 1):
            # Pause check between images
            if self._pause_event and not self._pause_event.is_set():
                self._log(f"  Paused at image {i}/{len(images)}")
                self._pause_event.wait()
                self._log(f"  Resumed at image {i}/{len(images)}")

            modality_str = img.modality or "unknown"
            source_str = (
                f"{img.source_file} p.{img.source_page}"
                if img.source_page
                else img.source_file
            )
            self._log(
                f"  Image {i}/{len(images)}: {source_str} "
                f"({img.source_type}, {modality_str})"
            )

            try:
                result = analyzer.analyze_image(
                    image_path=img.image_path,
                    source_file=img.source_file,
                    modality=img.modality,
                    body_region=img.body_region,
                )

                if not result:
                    failed += 1
                    error = f"Vision analysis failed for {source_str}: no result"
                    self._record_error(error)
                    self._log("    Error: no result")
                    continue

                if result.get("_error"):
                    failed += 1
                    error = f"Vision analysis failed for {source_str}: {result['_error']}"
                    self._record_error(error)
                    self._log(f"    Error: {result['_error']}")
                    continue

                succeeded += 1

                if not result.get("description") and not result.get("findings"):
                    self._log(f"    → No findings")
                    continue

                # Build ImagingStudy
                study = ImagingStudy(
                    modality=img.modality,
                    body_region=img.body_region,
                    description=result.get("description"),
                    findings=result.get("findings", []),
                    provenance=Provenance(
                        source_file=img.source_file,
                        source_page=img.source_page,
                        extraction_model="medgemma-4b",
                    ),
                )

                # Enrich with DICOM metadata if available
                if img.dicom_metadata:
                    study.facility = img.dicom_metadata.get("institution")
                    raw_date = img.dicom_metadata.get("study_date")
                    if raw_date:
                        try:
                            from datetime import date
                            study.study_date = date.fromisoformat(raw_date)
                        except (ValueError, TypeError):
                            pass

                profile.clinical_timeline.imaging.append(study)

                finding_count = len(result.get("findings", []))
                self._log(f"    → {finding_count} finding(s) recorded")

            except Exception as e:
                failed += 1
                self._record_error(
                    f"Vision analysis failed for {source_str}: {e}"
                )
                self._log(f"    Error: {e}")

        logger.info("MedGemma 4B vision analysis complete")
        return succeeded, failed

    # ── MONAI Quantitative Analysis ───────────────────────

    def _monai_analysis(self, images: list[MedicalImage],
                        profile: PatientProfile):
        """Run MONAI quantitative analysis on DICOM images."""
        dicom_images = [i for i in images if i.original_dicom_path]

        if not dicom_images:
            return

        try:
            from src.imaging.monai_detector import MONAIDetector
        except ImportError:
            self._record_error("MONAIDetector is not available for DICOM analysis")
            self._log("  MONAI not available — skipped")
            return

        detector = MONAIDetector(model_dir=self.data_dir / "models" / "monai")
        if not detector._monai_available or not detector._torch_available:
            self._record_error(
                "MONAI or PyTorch is not available for DICOM analysis"
            )
            self._log("  MONAI dependencies not available — skipped")
            return

        self._log(
            f"  Running MONAI on {len(dicom_images)} DICOM file(s)..."
        )

        for img in dicom_images:
            try:
                findings = detector.detect(
                    image_path=img.original_dicom_path,
                    source_file=img.source_file,
                    modality=img.modality,
                    body_region=img.body_region,
                )

                if not findings:
                    continue

                # Find the existing MedGemma 4B study for this image
                # so MONAI findings are merged with vision findings
                merged = False
                for study in profile.clinical_timeline.imaging:
                    if (
                        study.provenance.source_file == img.source_file
                        and study.provenance.extraction_model == "medgemma-4b"
                    ):
                        study.findings.extend(findings)
                        merged = True
                        self._log(
                            f"    MONAI: {len(findings)} quantitative "
                            f"finding(s) merged into {img.source_file}"
                        )
                        break

                # No existing study — create a new one
                if not merged:
                    study = ImagingStudy(
                        modality=img.modality,
                        body_region=img.body_region,
                        findings=findings,
                        provenance=Provenance(
                            source_file=img.source_file,
                            extraction_model="monai",
                        ),
                    )
                    if img.dicom_metadata:
                        study.facility = img.dicom_metadata.get("institution")
                        raw_date = img.dicom_metadata.get("study_date")
                        if raw_date:
                            try:
                                from datetime import date
                                study.study_date = date.fromisoformat(raw_date)
                            except (ValueError, TypeError):
                                pass
                    profile.clinical_timeline.imaging.append(study)
                    self._log(
                        f"    MONAI: {len(findings)} quantitative "
                        f"finding(s) for {img.source_file}"
                    )

            except Exception as e:
                self._record_error(
                    f"MONAI detection failed for {img.source_file}: {e}"
                )
                self._log(f"    MONAI error: {e}")

        logger.info("MONAI quantitative analysis complete")
