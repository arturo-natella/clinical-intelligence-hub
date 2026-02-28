import json
import logging
from pathlib import Path

logger = logging.getLogger("MedPrep-Standardize")

class StandardizationEngine:
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.loinc_path = self.data_dir / "loinc_map.json"
        self.snomed_path = self.data_dir / "snomed_map.json"
        self.rxnorm_path = self.data_dir / "rxnorm_map.json"
        
        # Load local databases into memory
        self.loinc_db = self._load_db(self.loinc_path, "LOINC")
        self.snomed_db = self._load_db(self.snomed_path, "SNOMED CT")
        self.rxnorm_db = self._load_db(self.rxnorm_path, "RxNorm")

    def _load_db(self, path: Path, name: str) -> dict:
        """Loads a local JSON lookup database into memory."""
        if path.exists():
            try:
                with open(path, 'r') as f:
                    db = json.load(f)
                logger.info(f"Loaded {len(db)} {name} concepts from local database.")
                return db
            except Exception as e:
                logger.error(f"Failed to load {name} database at {path}: {str(e)}")
        else:
            logger.warning(f"Local {name} database not found at {path}. Standardization will fallback to raw strings.")
        return {}
        
    def _create_seed_databases(self):
        """Creates small seed databases if they don't exist yet so the app can function gracefully."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Tiny seed of LOINC (Labs)
        if not self.loinc_path.exists():
            seed = {
                "hba1c": "4548-4", "a1c": "4548-4", "glycated hemoglobin": "4548-4",
                "tsh": "11579-0", "thyroid stimulating hormone": "11579-0",
                "ldl": "13457-7", "low density lipoprotein": "13457-7", "bad cholesterol": "13457-7",
                "hdl": "2085-9", "high density lipoprotein": "2085-9", "good cholesterol": "2085-9"
            }
            with open(self.loinc_path, 'w') as f:
                json.dump(seed, f, indent=2)
                
        # Tiny seed of SNOMED (Diagnoses/Symptoms)
        if not self.snomed_path.exists():
            seed = {
                "type 2 diabetes": "44054006", "t2d": "44054006", "diabetes mellitus type 2": "44054006",
                "hypertension": "38341003", "high blood pressure": "38341003", "htn": "38341003",
                "dry cough": "49727002", "cough": "49727002",
                "myocardial infarction": "22298006", "heart attack": "22298006", "mi": "22298006"
            }
            with open(self.snomed_path, 'w') as f:
                json.dump(seed, f, indent=2)
                
        # Tiny seed of RxNorm (Medications)
        if not self.rxnorm_path.exists():
            seed = {
                "lisinopril": "29046", "prinivil": "29046", "zestril": "29046",
                "metformin": "6809", "glucophage": "6809", "fortamet": "6809",
                "atorvastatin": "83367", "lipitor": "83367"
            }
            with open(self.rxnorm_path, 'w') as f:
                json.dump(seed, f, indent=2)

    def standardize_lab(self, lab_name: str) -> str:
        """Takes a raw lab name from the text extractor and maps to an exact LOINC code if possible."""
        if not lab_name: return None
        normalized = lab_name.lower().strip()
        # Direct lookup
        if normalized in self.loinc_db:
            return self.loinc_db[normalized]
        # Partial match fallback (e.g., "A1C (flagged high)" -> finds "a1c")
        for key, code in self.loinc_db.items():
            if key in normalized:
                return code
        return None
        
    def standardize_diagnosis(self, diagnosis_name: str) -> str:
        """Takes a raw diagnosis/symptom and maps to an exact SNOMED CT code if possible."""
        if not diagnosis_name: return None
        normalized = diagnosis_name.lower().strip()
        if normalized in self.snomed_db:
            return self.snomed_db[normalized]
        for key, code in self.snomed_db.items():
            if key in normalized:
                return code
        return None
        
    def standardize_medication(self, med_name: str) -> str:
        """Takes a raw medication name (brand or generic) and maps to its exact RxNorm CUI."""
        if not med_name: return None
        normalized = med_name.lower().strip()
        if normalized in self.rxnorm_db:
            return self.rxnorm_db[normalized]
        for key, code in self.rxnorm_db.items():
            if key in normalized:
                return code
        return None

if __name__ == "__main__":
    # Test script to seed databases
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    DATA_DIR = BASE_DIR / "data"
    engine = StandardizationEngine(str(DATA_DIR))
    engine._create_seed_databases()
    
    # Reload now that they are seeded
    engine = StandardizationEngine(str(DATA_DIR))
    print(f"Lisinopril RxNorm test: {engine.standardize_medication('Lisinopril')} (Expected: 29046)")
    print(f"A1C LOINC test: {engine.standardize_lab('A1C')} (Expected: 4548-4)")
    print(f"High Blood Pressure SNOMED test: {engine.standardize_diagnosis('High Blood Pressure')} (Expected: 38341003)")
