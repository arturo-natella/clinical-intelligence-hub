import json
import logging
from pathlib import Path
import os
import ollama

logger = logging.getLogger("MedPrep-MedGemma")

class MedGemmaProcessor:
    def __init__(self, api_key: str = None):
        # We use Ollama for local, privacy-first inference as mandated by the CK Plan.
        # The 27B model provides the highest quality reasoning for clinical text.
        self.model_name = "hf.co/google/medgemma-27b-it"
        
        # Save the API key for Pass 2 (Fallback) if needed by the orchestrator, 
        # but the primary extraction engine is strictly local.
        self.fallback_key = api_key or os.environ.get("GEMINI_API_KEY")
        
        logger.info(f"Initialized Local Ollama Text Processor using model {self.model_name}")

    def extract_from_pdf(self, pdf_path: Path):
        """
        Reads text from a PDF, chunks it if necessary, and uses Gemini 
        to extract structured clinical data into a JSON profile.
        """
        logger.info(f"Initiating production extraction for {pdf_path.name}")
        pdf_text = self._extract_raw_text(pdf_path)
        if not pdf_text:
            logger.warning(f"No text extracted from {pdf_path.name}. Skipping.")
            return None

        prompt = self._build_extraction_prompt(pdf_text)
        return self._call_ollama(prompt)

    def _extract_raw_text(self, pdf_path: Path) -> str:
        """
        Extracts raw text from a PDF file using PyMuPDF (fitz).
        Maintains document layout structure to assist the LLM.
        """
        logger.info(f"Extracting raw text from {pdf_path.name}...")
        try:
            import fitz # PyMuPDF
            
            doc = fitz.open(pdf_path)
            full_text = []
            
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                # 'blocks' preserves the layout better than raw 'text'
                text_blocks = page.get_text("blocks")
                
                # Sort blocks vertically then horizontally
                text_blocks.sort(key=lambda b: (b[1], b[0]))
                
                for block in text_blocks:
                    if len(block) >= 5 and isinstance(block[4], str):
                        full_text.append(block[4].strip())
            
            doc.close()
            
            combined_text = "\n".join(full_text)
            logger.info(f"Extracted {len(combined_text)} characters from {pdf_path.name}")
            return combined_text
            
        except ImportError:
            logger.error("PyMuPDF (fitz) is not installed. Run: pip install PyMuPDF")
            return None
        except Exception as e:
            logger.error(f"Failed to extract text from {pdf_path.name}: {str(e)}")
            return None

    def _build_extraction_prompt(self, raw_text: str) -> str:
        """Constructs the prompt instructing MedGemma on how to format the output."""
        return f"""
You are an expert clinical data extractor. Read the following medical record and extract all clinical entities into strict JSON format matching the schema below.
Extract: 
1. Medications (name, dosage, status)
2. Labs (name, value, unit)
3. Symptoms/Diagnoses (description)

Record Text:
\"\"\"{raw_text}\"\"\"

Output purely valid JSON.
"""

    def _call_ollama(self, prompt: str) -> dict:
        """Makes a synchronous call to the local Ollama runtime enforcing JSON output."""
        logger.info(f"Executing LOCAL extraction via {self.model_name}...")
        
        try:
            response = ollama.chat(
                model=self.model_name,
                messages=[{'role': 'user', 'content': prompt}],
                format='json',
                options={'temperature': 0.0}
            )
            
            result_text = response['message']['content']
            return json.loads(result_text)
            
        except Exception as e:
            logger.error(f"Failed to communicate with Local Ollama: {str(e)}")
            return {}
