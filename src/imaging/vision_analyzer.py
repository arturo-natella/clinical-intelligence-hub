"""
Clinical Intelligence Hub — Pass 1b: MedGemma 4B Vision Analysis

Uses local MedGemma 4B (via Ollama) to describe medical images
(X-rays, CT slices, MRI, pathology) in clinical language.

Runs 100% locally — no network calls. No raw images leave the machine.

Salvaged Ollama vision call pattern from old medgemma_vision.py.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from src.models import ImagingFinding, Provenance

logger = logging.getLogger("CIH-VisionAnalyzer")

# MedGemma 4B model for vision analysis
MODEL_NAME = "medgemma:4b-it"


class VisionAnalyzer:
    """Pass 1b: Describes medical images using MedGemma 4B vision model."""

    def __init__(self):
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
            logger.warning("Ollama not available — skipping vision analysis")
            return {"description": None, "findings": []}

        if not image_path.exists():
            logger.error(f"Image not found: {image_path}")
            return {"description": None, "findings": []}

        prompt = self._build_prompt(modality, body_region)
        result = self._call_ollama_vision(prompt, image_path)

        # Unload model from memory
        self._unload_model()

        if not result:
            return {"description": None, "findings": []}

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
        try:
            import ollama

            response = ollama.chat(
                model=MODEL_NAME,
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
            return json.loads(result_text)

        except json.JSONDecodeError as e:
            logger.warning(f"MedGemma 4B returned invalid JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"MedGemma 4B vision analysis failed: {e}")
            return None

    def _unload_model(self):
        """Explicitly unload MedGemma 4B from memory."""
        try:
            import ollama
            ollama.generate(model=MODEL_NAME, prompt="", keep_alive="0")
            logger.info("MedGemma 4B unloaded from memory")
        except Exception:
            pass

    @staticmethod
    def _check_ollama() -> bool:
        """Check if Ollama is running."""
        try:
            import ollama
            ollama.list()
            return True
        except Exception:
            return False
