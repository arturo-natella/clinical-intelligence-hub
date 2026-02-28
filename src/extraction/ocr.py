"""
Clinical Intelligence Hub — OCR Engine

Primary: Apple Vision framework (macOS native, runs locally, no network calls)
Fallback: Tesseract OCR

Converts scanned PDFs and images to searchable text with page tracking.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("CIH-OCR")


class OCREngine:
    """OCR with Apple Vision primary, Tesseract fallback."""

    def __init__(self):
        self._vision_available = self._check_vision()
        self._tesseract_available = self._check_tesseract()

        if self._vision_available:
            logger.info("OCR engine: Apple Vision framework (primary)")
        elif self._tesseract_available:
            logger.info("OCR engine: Tesseract (fallback)")
        else:
            logger.warning("No OCR engine available. Scanned documents cannot be processed.")

    def process_pdf(self, pdf_path: Path) -> list[dict]:
        """
        OCR a scanned PDF page by page.
        Returns list of {page: int, text: str}.
        """
        images = self._pdf_to_images(pdf_path)
        if not images:
            return []

        results = []
        for page_num, image_path in enumerate(images, start=1):
            text = self.ocr_image(image_path)
            if text and text.strip():
                results.append({"page": page_num, "text": text})

            # Clean up temp image
            if image_path.exists():
                image_path.unlink()

        logger.info(f"OCR extracted text from {len(results)} pages of {pdf_path.name}")
        return results

    def ocr_image(self, image_path: Path) -> Optional[str]:
        """OCR a single image file."""
        if self._vision_available:
            text = self._ocr_with_vision(image_path)
            if text:
                return text

        if self._tesseract_available:
            return self._ocr_with_tesseract(image_path)

        logger.error("No OCR engine available")
        return None

    # ── Apple Vision Framework ─────────────────────────────

    def _ocr_with_vision(self, image_path: Path) -> Optional[str]:
        """Use macOS Apple Vision framework for OCR."""
        try:
            import objc
            from Foundation import NSURL
            from Vision import (
                VNRecognizeTextRequest,
                VNImageRequestHandler,
                VNRequestTextRecognitionLevelAccurate,
            )

            image_url = NSURL.fileURLWithPath_(str(image_path))
            request_handler = VNImageRequestHandler.alloc().initWithURL_options_(
                image_url, None
            )

            request = VNRecognizeTextRequest.alloc().init()
            request.setRecognitionLevel_(VNRequestTextRecognitionLevelAccurate)
            request.setUsesLanguageCorrection_(True)

            success = request_handler.performRequests_error_([request], None)
            if not success[0]:
                return None

            observations = request.results()
            if not observations:
                return None

            lines = []
            for obs in observations:
                candidates = obs.topCandidates_(1)
                if candidates:
                    lines.append(candidates[0].string())

            return "\n".join(lines)

        except Exception as e:
            logger.debug(f"Apple Vision OCR failed: {e}")
            return None

    # ── Tesseract Fallback ─────────────────────────────────

    def _ocr_with_tesseract(self, image_path: Path) -> Optional[str]:
        """Use Tesseract OCR as fallback."""
        try:
            import pytesseract
            from PIL import Image

            image = Image.open(image_path)
            text = pytesseract.image_to_string(image)
            return text

        except Exception as e:
            logger.error(f"Tesseract OCR failed: {e}")
            return None

    # ── PDF to Images ──────────────────────────────────────

    def _pdf_to_images(self, pdf_path: Path) -> list[Path]:
        """Convert each PDF page to a temporary PNG image for OCR."""
        try:
            import fitz  # PyMuPDF
            from PIL import Image
            import tempfile

            doc = fitz.open(str(pdf_path))
            temp_dir = Path(tempfile.mkdtemp())
            image_paths = []

            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                # Render at 300 DPI for good OCR quality
                mat = fitz.Matrix(300 / 72, 300 / 72)
                pix = page.get_pixmap(matrix=mat)

                img_path = temp_dir / f"page_{page_num + 1}.png"
                pix.save(str(img_path))
                image_paths.append(img_path)

            doc.close()
            return image_paths

        except Exception as e:
            logger.error(f"Failed to convert PDF to images: {e}")
            return []

    # ── Availability Checks ────────────────────────────────

    def _check_vision(self) -> bool:
        """Check if Apple Vision framework is available."""
        try:
            import Vision
            return True
        except ImportError:
            return False

    def _check_tesseract(self) -> bool:
        """Check if Tesseract is installed."""
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False
