"""
Clinical Intelligence Hub — DICOM Converter

Extracts metadata from DICOM medical imaging files and converts
pixel data to PNG for viewing and vision model analysis.

Salvaged DICOM header reading pattern from old monai_imaging.py,
enhanced with provenance tracking and safer memory handling.
"""

import logging
from pathlib import Path
from typing import Optional

from src.models import ImagingStudy, Provenance

logger = logging.getLogger("CIH-DICOM")


class DICOMConverter:
    """Extracts metadata and converts DICOM to PNG."""

    def extract_metadata(self, dicom_path: Path) -> dict:
        """
        Read DICOM headers without loading pixel data.
        Uses stop_before_pixels=True to save memory during routing.

        Salvaged from old monai_imaging.py._read_dicom_headers.
        """
        try:
            import pydicom

            ds = pydicom.dcmread(str(dicom_path), stop_before_pixels=True)

            metadata = {
                "patient_id": getattr(ds, "PatientID", None),
                "study_date": self._format_dicom_date(getattr(ds, "StudyDate", None)),
                "modality": getattr(ds, "Modality", None),
                "body_part": getattr(ds, "BodyPartExamined", "").upper(),
                "study_description": getattr(ds, "StudyDescription", None),
                "series_description": getattr(ds, "SeriesDescription", None),
                "institution": getattr(ds, "InstitutionName", None),
                "manufacturer": getattr(ds, "Manufacturer", None),
                "rows": getattr(ds, "Rows", None),
                "columns": getattr(ds, "Columns", None),
                "slice_thickness": getattr(ds, "SliceThickness", None),
                "pixel_spacing": list(getattr(ds, "PixelSpacing", [])) if hasattr(ds, "PixelSpacing") else None,
            }

            logger.info(
                f"DICOM metadata: {metadata['modality']} of {metadata['body_part']} "
                f"from {metadata.get('institution', 'unknown')}"
            )
            return metadata

        except ImportError:
            logger.error("pydicom not installed. Run: pip install pydicom")
            return {}
        except Exception as e:
            logger.error(f"Failed to read DICOM headers from {dicom_path.name}: {e}")
            return {}

    def convert_to_png(self, dicom_path: Path, output_dir: Path) -> Optional[Path]:
        """
        Convert DICOM pixel data to PNG for vision model analysis.
        Returns the path to the generated PNG file.
        """
        try:
            import pydicom
            import numpy as np
            from PIL import Image

            ds = pydicom.dcmread(str(dicom_path))

            if not hasattr(ds, "pixel_array"):
                logger.warning(f"No pixel data in {dicom_path.name}")
                return None

            pixel_array = ds.pixel_array

            # Handle multi-frame DICOM (take middle frame)
            if pixel_array.ndim == 3 and pixel_array.shape[0] > 1:
                middle = pixel_array.shape[0] // 2
                pixel_array = pixel_array[middle]

            # Normalize to 0-255 for PNG
            if pixel_array.max() > 0:
                normalized = (
                    (pixel_array - pixel_array.min())
                    / (pixel_array.max() - pixel_array.min())
                    * 255
                ).astype(np.uint8)
            else:
                normalized = pixel_array.astype(np.uint8)

            # Apply window/level if available (for CT)
            if hasattr(ds, "WindowCenter") and hasattr(ds, "WindowWidth"):
                center = float(ds.WindowCenter) if not isinstance(ds.WindowCenter, list) else float(ds.WindowCenter[0])
                width = float(ds.WindowWidth) if not isinstance(ds.WindowWidth, list) else float(ds.WindowWidth[0])
                lower = center - width / 2
                upper = center + width / 2
                windowed = np.clip(pixel_array, lower, upper)
                normalized = ((windowed - lower) / (upper - lower) * 255).astype(np.uint8)

            img = Image.fromarray(normalized)

            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"{dicom_path.stem}.png"
            img.save(str(output_path))

            logger.info(f"Converted {dicom_path.name} → {output_path.name}")
            return output_path

        except ImportError as e:
            logger.error(f"Missing dependency for DICOM conversion: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to convert {dicom_path.name} to PNG: {e}")
            return None

    def create_imaging_study(self, dicom_path: Path, metadata: dict) -> ImagingStudy:
        """Create an ImagingStudy model from DICOM metadata."""
        from datetime import date as date_type

        study_date = None
        raw_date = metadata.get("study_date")
        if raw_date:
            try:
                study_date = date_type.fromisoformat(raw_date)
            except (ValueError, TypeError):
                pass

        return ImagingStudy(
            study_date=study_date,
            modality=metadata.get("modality"),
            body_region=metadata.get("body_part"),
            description=metadata.get("study_description"),
            facility=metadata.get("institution"),
            findings=[],
            provenance=Provenance(
                source_file=dicom_path.name,
                extraction_model="dicom-header",
                confidence=1.0,
            ),
        )

    @staticmethod
    def _format_dicom_date(raw: Optional[str]) -> Optional[str]:
        """Convert DICOM date (YYYYMMDD) to ISO format (YYYY-MM-DD)."""
        if not raw or len(raw) < 8:
            return None
        try:
            return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
        except (IndexError, ValueError):
            return None
