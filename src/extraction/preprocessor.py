"""
Clinical Intelligence Hub — Pass 0: Preprocessing

Responsibilities:
  - File type classification (PDF, DICOM, FHIR, image, genetic)
  - SHA-256 deduplication
  - Text layer detection (digital vs scanned PDF)
  - OCR for scanned documents
  - File routing to correct extraction pipeline
  - State checkpointing in SQLite for crash recovery
"""

import hashlib
import logging
from pathlib import Path
from typing import Optional

from src.models import FileType, ProcessedFile, ProcessingStatus
from src.database import Database

logger = logging.getLogger("CIH-Preprocessor")

# Supported file extensions mapped to types
EXTENSION_MAP = {
    ".pdf": None,          # Needs text layer check → pdf_text or pdf_scanned
    ".dcm": FileType.DICOM,
    ".dicom": FileType.DICOM,
    ".json": None,         # Could be FHIR or config → checked at content level
    ".jpg": FileType.IMAGE,
    ".jpeg": FileType.IMAGE,
    ".png": FileType.IMAGE,
    ".tif": FileType.IMAGE,
    ".tiff": FileType.IMAGE,
    ".bmp": FileType.IMAGE,
}


class Preprocessor:
    """Pass 0: classifies, deduplicates, and routes files for extraction."""

    def __init__(self, db: Database):
        self.db = db

    def classify_file(self, file_path: Path) -> FileType:
        """Determine the type of a medical record file."""
        ext = file_path.suffix.lower()

        # Check extension first
        mapped = EXTENSION_MAP.get(ext)
        if mapped is not None:
            return mapped

        # PDF needs text layer check
        if ext == ".pdf":
            return self._classify_pdf(file_path)

        # JSON might be FHIR
        if ext == ".json":
            return self._classify_json(file_path)

        # Genetic test formats
        if ext in (".vcf", ".tsv") or "genetic" in file_path.name.lower():
            return FileType.GENETIC

        return FileType.UNKNOWN

    def compute_hash(self, file_path: Path) -> str:
        """SHA-256 hash of a file for deduplication."""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            while chunk := f.read(65536):
                sha256.update(chunk)
        return sha256.hexdigest()

    def is_duplicate(self, sha256_hash: str) -> bool:
        """Check if this exact file has already been processed."""
        return self.db.is_duplicate(sha256_hash)

    def register_file(self, file_path: Path) -> Optional[ProcessedFile]:
        """
        Classify, hash, and register a file for processing.
        Returns None if the file is a duplicate or unsupported.
        """
        file_type = self.classify_file(file_path)

        if file_type == FileType.UNKNOWN:
            logger.warning(f"Unsupported file type: {file_path.name}")
            return None

        sha256 = self.compute_hash(file_path)

        if self.is_duplicate(sha256):
            logger.debug(f"Duplicate file skipped: {file_path.name}")
            return None

        file_size = file_path.stat().st_size
        page_count = self._count_pages(file_path, file_type)

        processed = ProcessedFile(
            filename=file_path.name,
            file_type=file_type,
            sha256_hash=sha256,
            file_size_bytes=file_size,
            page_count=page_count,
        )

        # Register in database for checkpoint tracking
        self.db.upsert_file_state(
            file_id=processed.file_id,
            filename=processed.filename,
            file_type=processed.file_type.value,
            sha256_hash=processed.sha256_hash,
            file_size_bytes=processed.file_size_bytes,
            status=ProcessingStatus.PREPROCESSING.value,
            page_count=page_count,
        )

        logger.info(f"Registered: {file_path.name} ({file_type.value}, {file_size:,} bytes)")
        return processed

    def process(self, file_path: Path) -> Optional[dict]:
        """
        Full preprocessing pipeline for a single file.

        Classifies, deduplicates, extracts text (for PDFs), and returns
        a result dict ready for downstream passes.

        Returns None for duplicates/unsupported files.
        Returns dict with keys: file_id, filename, filepath, file_type,
            sha256, page_count, text, pages, images
        """
        registered = self.register_file(file_path)
        if registered is None:
            return None

        result = {
            "file_id": registered.file_id,
            "filename": registered.filename,
            "filepath": str(file_path),
            "file_type": registered.file_type.value,
            "sha256": registered.sha256_hash,
            "page_count": registered.page_count,
            "text": "",
            "pages": [],
            "images": [],
        }

        # Extract text from PDFs (the primary medical record format)
        if registered.file_type == FileType.PDF_TEXT:
            pages = self.extract_text_from_pdf(file_path)
            result["pages"] = pages
            result["text"] = "\n\n".join(p["text"] for p in pages)

        elif registered.file_type == FileType.PDF_SCANNED:
            pages = self.extract_text_with_ocr(file_path)
            result["pages"] = pages
            result["text"] = "\n\n".join(p["text"] for p in pages)
            if not pages:
                logger.warning(
                    f"OCR returned no text for scanned PDF: {file_path.name}"
                )

        # Image files → pass path for vision analysis
        elif registered.file_type in (FileType.IMAGE, FileType.DICOM):
            result["images"] = [str(file_path)]

        # FHIR JSON → read raw content for structured extraction
        elif registered.file_type == FileType.FHIR_JSON:
            try:
                result["text"] = file_path.read_text(encoding="utf-8")
            except Exception as e:
                logger.error(f"Failed to read FHIR JSON {file_path.name}: {e}")

        # Update DB status
        self.db.upsert_file_state(
            file_id=registered.file_id,
            filename=registered.filename,
            file_type=registered.file_type.value,
            sha256_hash=registered.sha256_hash,
            file_size_bytes=registered.file_size_bytes,
            status=ProcessingStatus.EXTRACTING.value,
            page_count=registered.page_count,
        )

        text_len = len(result["text"])
        img_count = len(result["images"])
        logger.info(
            f"Processed: {file_path.name} → "
            f"{text_len:,} chars text, {img_count} images"
        )
        return result

    def extract_text_from_pdf(self, pdf_path: Path) -> list[dict]:
        """
        Extract text from a digital PDF using PyMuPDF.
        Returns list of {page: int, text: str} for each page.

        Salvaged from old medgemma_text.py PyMuPDF extraction pattern,
        enhanced with page-level tracking for provenance.
        """
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(str(pdf_path))
            pages = []

            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                # 'blocks' preserves layout better than raw text
                text_blocks = page.get_text("blocks")
                text_blocks.sort(key=lambda b: (b[1], b[0]))

                page_text = "\n".join(
                    block[4].strip()
                    for block in text_blocks
                    if len(block) >= 5 and isinstance(block[4], str)
                )

                if page_text.strip():
                    pages.append({
                        "page": page_num + 1,  # 1-indexed for human readability
                        "text": page_text,
                    })

            doc.close()
            logger.info(f"Extracted text from {len(pages)} pages of {pdf_path.name}")
            return pages

        except ImportError:
            logger.error("PyMuPDF not installed. Run: pip install PyMuPDF")
            return []
        except Exception as e:
            logger.error(f"Failed to extract text from {pdf_path.name}: {e}")
            return []

    def extract_text_with_ocr(self, pdf_path: Path) -> list[dict]:
        """
        Extract text from a scanned PDF using OCR.
        Delegates to src.extraction.ocr module.
        Returns list of {page: int, text: str}.
        """
        try:
            from src.extraction.ocr import OCREngine
            engine = OCREngine()
            return engine.process_pdf(pdf_path)
        except Exception as e:
            logger.error(f"OCR failed for {pdf_path.name}: {e}")
            return []

    # ── Private helpers ────────────────────────────────────

    def _classify_pdf(self, pdf_path: Path) -> FileType:
        """Check if a PDF has an extractable text layer."""
        try:
            import fitz
            doc = fitz.open(str(pdf_path))

            text_found = False
            # Check first 3 pages for text content
            for i in range(min(3, len(doc))):
                page = doc.load_page(i)
                text = page.get_text("text").strip()
                if len(text) > 50:  # Meaningful text threshold
                    text_found = True
                    break

            doc.close()
            return FileType.PDF_TEXT if text_found else FileType.PDF_SCANNED

        except Exception:
            return FileType.PDF_SCANNED  # Safer default

    def _classify_json(self, json_path: Path) -> FileType:
        """Check if a JSON file is a FHIR bundle."""
        try:
            import json
            with open(json_path, 'r') as f:
                data = json.load(f)

            # FHIR bundles have resourceType
            if isinstance(data, dict) and data.get("resourceType") in ("Bundle", "Patient", "Observation"):
                return FileType.FHIR_JSON

            return FileType.UNKNOWN
        except Exception:
            return FileType.UNKNOWN

    def _count_pages(self, file_path: Path, file_type: FileType) -> Optional[int]:
        """Count pages for PDFs, None for other types."""
        if file_type not in (FileType.PDF_TEXT, FileType.PDF_SCANNED):
            return None
        try:
            import fitz
            doc = fitz.open(str(file_path))
            count = len(doc)
            doc.close()
            return count
        except Exception:
            return None
