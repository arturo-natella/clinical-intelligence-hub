import logging
from pathlib import Path
import os
import ollama
import json

logger = logging.getLogger("MedPrep-Vision")

class MedGemmaVisionProcessor:
    def __init__(self, api_key: str = None):
        # We use Ollama for local, privacy-first image description as mandated by the CK Plan.
        self.model_name = "hf.co/google/medgemma-4b-it"
        
        # Save the API key for Pass 2 (Fallback) if needed by the orchestrator
        self.fallback_key = api_key or os.environ.get("GEMINI_API_KEY")
        
        logger.info(f"Initialized Local Ollama Vision Processor using model {self.model_name}")

    def describe_image(self, image_path: Path) -> dict:
        """
        Takes a path to an image file and asks the local visual model to describe what it sees clinically.
        """
        logger.info(f"Analyzing image {image_path.name} with Local MedGemma 4B Vision...")
        
        prompt = self._build_vision_prompt()
        return self._call_ollama_vision(prompt, image_path)

    def _build_vision_prompt(self) -> str:
        return """
        You are an expert radiologist. Review the attached medical imaging slice.
        Provide a concise, qualitative description of the anatomy and any obvious abnormalities.
        Do not provide a definitive diagnosis. Output strict JSON with a "description" key.
        """

    def _call_ollama_vision(self, prompt: str, image_path: Path) -> dict:
        """Makes a synchronous call to the local Ollama API with the image payload."""
        try:
            response = ollama.chat(
                model=self.model_name,
                messages=[{
                    'role': 'user',
                    'content': prompt,
                    'images': [str(image_path)]
                }],
                format='json',
                options={'temperature': 0.1}
            )
            
            result_text = response['message']['content']
            return json.loads(result_text)
            
        except Exception as e:
            logger.error(f"Failed to communicate with Local Ollama Vision: {str(e)}")
            return {"description": "Error analyzing image."}
