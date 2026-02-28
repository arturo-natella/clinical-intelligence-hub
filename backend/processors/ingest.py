import os
import json
import logging
from pathlib import Path
from datetime import datetime
import hashlib
from typing import Dict, List, Any
import pydicom
import numpy as np
from PIL import Image

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("MedPrep-Ingest")

from medgemma_text import MedGemmaProcessor
from monai_imaging import MonaiProcessor
from medgemma_vision import MedGemmaVisionProcessor
import sys
sys.path.append(str(Path(__file__).resolve().parent.parent / "utils"))
from standardize import StandardizationEngine
from encryption import SecurityManager

class IngestionPipeline:
    def __init__(self, raw_dir: str, processed_dir: str, profile_path: str, config_path: str = None):
        self.raw_dir = Path(raw_dir)
        self.processed_dir = Path(processed_dir)
        self.profile_path = Path(profile_path)
        
        # Load API Configurations
        self.api_keys = {}
        if config_path and Path(config_path).exists():
            with open(config_path, 'r') as f:
                self.api_keys = json.load(f)
        
        gemini_key = self.api_keys.get('gemini_api_key')
        
        # Instantiate Processors with the Keys
        self.medgemma = MedGemmaProcessor(api_key=gemini_key)
        self.monai = MonaiProcessor()
        self.medgemma_vision = MedGemmaVisionProcessor(api_key=gemini_key)
        
        # Instantiate Standardization Engine (Local mapping)
        data_dir = self.profile_path.parent
        self.standardizer = StandardizationEngine(str(data_dir))
        self.standardizer._create_seed_databases() # Ensure seed DBs exist
        
        # Instantiate Security Manager (AES Encryption)
        self.security = SecurityManager(data_dir)
        
        # Ensure directories exist
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        
        self.patient_profile = self._load_profile()
        self.processed_hashes = self._load_processed_hashes()

    def _load_profile(self) -> Dict[str, Any]:
        """Load the patient profile securely, or create a blank one if it doesn't exist."""
        profile = self.security.load_profile(self.profile_path)
        if profile:
            return profile
        
        # Blank profile matching our schema
        return {
            "patient": {"id": "patient-1", "demographics": {}, "genetics": []},
            "clinical_timeline": {
                "medications": [],
                "labs": [],
                "imaging": [],
                "symptoms_and_diary": []
            },
            "ai_analysis": {"flags": [], "questions_for_doctor": []}
        }

    def _load_processed_hashes(self) -> set:
        """Load tracking data for files we've already processed to avoid duplicate work."""
        hash_file = self.processed_dir / ".processed_hashes.json"
        if hash_file.exists():
            with open(hash_file, 'r') as f:
                return set(json.load(f))
        return set()

    def _save_processed_hashes(self):
        hash_file = self.processed_dir / ".processed_hashes.json"
        with open(hash_file, 'w') as f:
            json.dump(list(self.processed_hashes), f)

    def _save_profile(self):
        self.security.save_profile(self.patient_profile, self.profile_path)

    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute an MD5 hash of a file to track if we've seen it before."""
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            buf = f.read(65536)
            while len(buf) > 0:
                hasher.update(buf)
                buf = f.read(65536)
        return hasher.hexdigest()

    def run_pipeline(self):
        """Main orchestrated method to process all files in the raw_uploads directory."""
        logger.info(f"Starting MedPrep Ingestion Pipeline. Looking in {self.raw_dir}")
        new_files_processed = 0

        for file_path in self.raw_dir.rglob("*"):
            if not file_path.is_file() or file_path.name.startswith('.'):
                continue
                
            file_hash = self._compute_file_hash(file_path)
            if file_hash in self.processed_hashes:
                logger.debug(f"Skipping already processed file: {file_path.name}")
                continue

            logger.info(f"Processing new file: {file_path.name}")
            extension = file_path.suffix.lower()

            try:
                if extension == '.pdf':
                    self._process_pdf(file_path)
                elif extension in ['.dcm', '.dicom']:
                    self._process_dicom(file_path)
                else:
                    logger.warning(f"Unsupported file type: {extension} ({file_path.name})")
                    continue

                # Only add to hash tracking if processing succeeds
                self.processed_hashes.add(file_hash)
                new_files_processed += 1

            except Exception as e:
                logger.error(f"Failed to process {file_path.name}: {str(e)}")

        if new_files_processed > 0:
            logger.info(f"Processed {new_files_processed} new files. Saving profile.")
            self._save_profile()
            self._save_processed_hashes()
        else:
            logger.info("No new files found to process.")

    def _process_pdf(self, file_path: Path):
        """Route to MedGemma 27B text extraction (Pass 1a), falling back to Gemini (Pass 2) if needed."""
        logger.info(f"[Pass 1a] Routing {file_path.name} to LOCAL MedGemma 27B for text extraction...")
        
        extracted_data = self.medgemma.extract_from_pdf(file_path)
        if extracted_data:
            logger.info(f"Successfully extracted data from {file_path.name} locally.")
            self._merge_text_into_profile(extracted_data)
        else:
            logger.warning(f"Local extraction failed for {file_path.name}. Initiating [Pass 2] Fallback...")
            self._fallback_process_pdf(file_path)

    def _fallback_process_pdf(self, file_path: Path):
        """Pass 2: Uses Gemini Pro for documents the local model couldn't parse (e.g., scanned handwriting)."""
        gemini_key = self.api_keys.get('gemini_api_key')
        if not gemini_key:
            logger.error("No Gemini API Key found for Pass 2 fallback. Skipping.")
            return

        logger.info(f"[Pass 2] Executing Cloud Fallback for {file_path.name} via Gemini 3.1 Pro API...")
        try:
            from google import genai
            from google.genai import types
            import json
            
            client = genai.Client(api_key=gemini_key)
            
            with open(file_path, "rb") as f:
                pdf_bytes = f.read()
            
            pdf_part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
            
            prompt = "Extract Medications, Labs, and Symptoms from this record into structured JSON matching the schema: {'medications': [], 'labs': [], 'symptoms_and_diary': []}"
            
            response = client.models.generate_content(
                model="gemini-1.5-pro",
                contents=[prompt, pdf_part],
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.0)
            )
            extracted_data = json.loads(response.text)
            self._merge_text_into_profile(extracted_data)
            logger.info(f"Successfully extracted data via Pass 2 Cloud Fallback.")
        except Exception as e:
            logger.error(f"[Pass 2] Cloud Fallback extraction also failed: {str(e)}")

    def _process_dicom(self, file_path: Path):
        """Route to MONAI and MedGemma 4B imaging analysis."""
        logger.info(f"[Pass 1b/1c] Routing {file_path.name} to MONAI/MedGemma 4B for image analysis...")
        
        # Pass 1c: Clinical grade measurement
        monai_data = self.monai.extract_from_dicom(file_path)
        
        # Convert DICOM to PNG for Gemini Vision
        png_path = self._convert_dicom_to_png(file_path)
        if not png_path:
            logger.warning(f"Could not convert {file_path.name} to PNG. Vision pass skipped.")
            return

        # Pass 1b: Natural language description
        vision_data = self.medgemma_vision.describe_image(png_path)
        
        if monai_data and vision_data:
            logger.info(f"Successfully processed imaging data from {file_path.name}")
            # Combine logic into JSON profile here
            image_record = {
                "date": monai_data.get("metadata", {}).get("study_date"),
                "modality": monai_data.get("metadata", {}).get("modality"),
                "body_part": monai_data.get("metadata", {}).get("body_part"),
                "description": vision_data.get("description"),
                "clinical_measurements": monai_data.get("monai_findings", [])
            }
            logger.info(f"Generated unified imaging record for: {image_record['body_part']}")
            
            # Ensure imaging array exists in Profile
            tl = self.patient_profile.setdefault('clinical_timeline', {})
            tl.setdefault('imaging', []).append(image_record)
        else:
            logger.warning(f"Failed to fully process imaging data from {file_path.name}")

    def _merge_text_into_profile(self, extracted_data: dict):
        """Merges loosely structured LLM JSON extraction into the strict profile schema."""
        if not extracted_data or not isinstance(extracted_data, dict):
            return
            
        tl = self.patient_profile.setdefault('clinical_timeline', {})
        tl.setdefault('medications', [])
        tl.setdefault('labs', [])
        tl.setdefault('symptoms_and_diary', [])
        
        # Merge Medications (Account for various casing outputs from LLM)
        meds = extracted_data.get('Medications', []) or extracted_data.get('medications', [])
        if isinstance(meds, list):
            for m in meds:
                if isinstance(m, dict):
                    name = m.get('name')
                    rxnorm = self.standardizer.standardize_medication(name)
                    if rxnorm: m['rxnorm_cui'] = rxnorm
                    tl['medications'].append(m)
                elif isinstance(m, str):
                    rxnorm = self.standardizer.standardize_medication(m)
                    tl['medications'].append({"name": m, "status": "active", "rxnorm_cui": rxnorm})
                    
        # Merge Labs
        labs = extracted_data.get('Labs', []) or extracted_data.get('labs', [])
        if isinstance(labs, list):
            for l in labs:
                if isinstance(l, dict):
                    name = l.get('name')
                    loinc = self.standardizer.standardize_lab(name)
                    if loinc: l['loinc'] = loinc
                    tl['labs'].append(l)
                elif isinstance(l, str):
                    loinc = self.standardizer.standardize_lab(l)
                    tl['labs'].append({"name": l, "value": "Unknown", "loinc": loinc})
                    
        # Merge Symptoms
        symp = extracted_data.get('Symptoms/Diagnoses', []) or extracted_data.get('symptoms', []) or extracted_data.get('Symptoms', []) or extracted_data.get('diagnoses', [])
        if isinstance(symp, list):
            for s in symp:
                if isinstance(s, dict):
                    desc = s.get('description', '') or s.get('symptom', '') or s.get('diagnosis', '')
                    snomed = self.standardizer.standardize_diagnosis(desc)
                    if snomed: s['snomed_ct'] = snomed
                    tl['symptoms_and_diary'].append(s)
                elif isinstance(s, str):
                    snomed = self.standardizer.standardize_diagnosis(s)
                    tl['symptoms_and_diary'].append({"description": s, "snomed_ct": snomed})

    def _convert_dicom_to_png(self, dicom_path: Path) -> Path:
        """Extracts the pixel array from a DICOM and saves as a visual PNG for Gemini."""
        try:
            ds = pydicom.dcmread(dicom_path)
            # Normalize pixel values to 0-255
            pixels = ds.pixel_array
            
            # Simple windowing/normalization to ensure the image is viewable
            pixels = pixels - np.min(pixels)
            if np.max(pixels) != 0:
                pixels = pixels / np.max(pixels)
            pixels = (pixels * 255).astype(np.uint8)
            
            # If it's a 3D scan, just take the middle slice
            if len(pixels.shape) == 3:
                pixels = pixels[pixels.shape[0] // 2]
                
            img = Image.fromarray(pixels)
            png_name = f"{dicom_path.stem}.png"
            png_path = self.processed_dir / png_name
            img.save(png_path)
            
            return png_path
        except Exception as e:
            logger.error(f"DICOM to PNG conversion failed: {str(e)}")
            return None

if __name__ == "__main__":
    # Define absolute paths based on project structure
    BASE_DIR = Path(__file__).resolve().parent.parent
    RAW_DIR = BASE_DIR / "data" / "raw_uploads"
    PROCESSED_DIR = BASE_DIR / "data" / "processed"
    PROFILE_PATH = BASE_DIR / "data" / "patient_profile.json"
    CONFIG_PATH = BASE_DIR / "data" / "config.json"
    
    pipeline = IngestionPipeline(
        raw_dir=str(RAW_DIR), 
        processed_dir=str(PROCESSED_DIR), 
        profile_path=str(PROFILE_PATH),
        config_path=str(CONFIG_PATH)
    )
    pipeline.run_pipeline()
