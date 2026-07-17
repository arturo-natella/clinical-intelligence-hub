"""
Clinical Intelligence Hub — Pass 1b: MedGemma 4B Vision Analysis

Uses local MedGemma 4B (via Ollama) to describe medical images
(X-rays, CT slices, MRI, pathology) in clinical language.

Runs 100% locally — no network calls. No raw images leave the machine.

Salvaged Ollama vision call pattern from old medgemma_vision.py.
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

from src.models import ImagingFinding

logger = logging.getLogger("CIH-VisionAnalyzer")

# Official Ollama tag for the multimodal MedGemma 4B model. The previous
# ``medgemma:4b-it`` value is a Hugging Face-style name and does not exist in
# Ollama's registry. Allow an explicit local override for custom builds.
MODEL_NAME = (
    os.environ.get("MEDPREP_VISION_MODEL", "medgemma:4b").strip()
    or "medgemma:4b"
)


class VisionAnalyzer:
    """Pass 1b: Describes medical images using MedGemma 4B vision model."""

    def __init__(self, model_name: str = None):
        self.model_name = model_name or MODEL_NAME
        self.availability_error: Optional[str] = None
        self.last_error: Optional[str] = None
        self._available = self._check_ollama()

    def analyze_image(self, image_path: Path, source_file: str,
                      modality: str = None, body_region: str = None) -> dict:
        """
        Analyze a medical image and return clinical description + findings.

        Args:
            image_path: Path to PNG/JPG image
            source_file: Original filename for provenance
            modality: Imaging modality (CT, MRI, X-ray, etc.)
            body_region: Body part imaged

        Returns:
            dict with 'description' and 'findings' list
        """
        if not self._available:
            error = self.availability_error or "Local vision model is not available"
            logger.warning("%s — skipping vision analysis", error)
            return {"description": None, "findings": [], "_error": error}

        if not image_path.exists():
            error = f"Image not found: {image_path}"
            self.last_error = error
            logger.error(error)
            return {"description": None, "findings": [], "_error": error}

        prompt = self._build_prompt(modality, body_region)
        result = self._call_ollama_vision(prompt, image_path)

        # Unload model from memory
        self._unload_model()

        if not result:
            error = self.last_error or "Local vision model returned no result"
            return {"description": None, "findings": [], "_error": error}

        # Parse findings into models
        findings = []
        for finding_data in result.get("findings", []):
            if isinstance(finding_data, dict) and finding_data.get("description"):
                findings.append(ImagingFinding(
                    description=finding_data["description"],
                    body_region=finding_data.get("body_region", body_region),
                    measurements=finding_data.get("measurements"),
                    confidence=finding_data.get("confidence"),
                ))

        return {
            "description": result.get("description", ""),
            "findings": findings,
        }

    def _build_prompt(self, modality: str = None, body_region: str = None) -> str:
        """Build the clinical image analysis prompt."""
        context = ""
        if modality:
            context += f"This is a {modality} image"
        if body_region:
            context += f" of the {body_region}" if context else f"This is an image of the {body_region}"
        context = context + "." if context else "This is a medical image."

        return f"""{context}

You are an expert radiologist providing a preliminary read. Review this medical image and provide:

1. **description**: A concise qualitative description of the anatomy visible and any obvious abnormalities.
2. **findings**: An array of specific findings, each with:
   - description: what you observe
   - body_region: anatomical location
   - measurements: any measurable quantities (e.g., {{"diameter_mm": 8}})
   - confidence: your confidence level (0.0-1.0)

Important:
- Do NOT provide a definitive diagnosis
- Describe only what is visually apparent
- Note any areas that warrant further evaluation
- Be specific about locations (e.g., "right upper lobe" not just "lung")

Output strictly valid JSON with "description" and "findings" keys."""

    def _call_ollama_vision(self, prompt: str, image_path: Path) -> Optional[dict]:
        """Call Ollama with an image for vision analysis."""
        self.last_error = None
        try:
            import ollama

            response = ollama.chat(
                model=self.model_name,
                messages=[{
                    "role": "user",
                    "content": prompt,
                    "images": [str(image_path)],
                }],
                format="json",
                options={
                    "temperature": 0.1,
                    "num_predict": 2048,
                },
                keep_alive="0",
            )

            result_text = response["message"]["content"]
            result = json.loads(result_text)
            if not isinstance(result, dict):
                self.last_error = "Local vision model returned JSON that was not an object"
                logger.warning(self.last_error)
                return None
            return result

        except json.JSONDecodeError as e:
            self.last_error = f"MedGemma 4B returned invalid JSON: {e}"
            logger.warning(self.last_error)
            return None
        except Exception as e:
            self.last_error = f"MedGemma 4B vision analysis failed: {e}"
            logger.error(self.last_error)
            return None

    def _unload_model(self):
        """Explicitly unload MedGemma 4B from memory."""
        try:
            import ollama
            ollama.generate(model=self.model_name, prompt="", keep_alive="0")
            logger.info("MedGemma 4B unloaded from memory")
        except Exception:
            pass

    def _check_ollama(self) -> bool:
        """Verify both the Ollama daemon and the configured vision model."""
        try:
            import ollama
            listing = ollama.list()
        except Exception as e:
            self.availability_error = (
                f"Ollama daemon is not reachable ({e}). Start it with "
                "`ollama serve` or launch the Ollama app."
            )
            logger.warning(self.availability_error)
            return False

        entries = getattr(listing, "models", None)
        if entries is None and isinstance(listing, dict):
            entries = listing.get("models", [])
        entries = entries or []

        available = set()
        for entry in entries:
            name = getattr(entry, "model", None)
            if name is None and isinstance(entry, dict):
                name = entry.get("model") or entry.get("name")
            if name:
                available.add(str(name))

        requested = self.model_name
        candidates = {requested}
        if ":" not in requested:
            candidates.add(f"{requested}:latest")

        if not (candidates & available):
            self.availability_error = (
                f"Ollama is running but vision model '{requested}' is not pulled. "
                f"Run: ollama pull {requested}"
            )
            logger.warning(self.availability_error)
            return False

        return True
