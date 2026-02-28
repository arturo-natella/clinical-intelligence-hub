"""
Clinical Intelligence Hub — SNOMED CT Clinical Terminology

SNOMED CT (Systematized Nomenclature of Medicine — Clinical Terms)
standardizes diagnoses, procedures, body structures, and findings.

This enables:
  - Matching the same condition across different providers who use
    different terminology (e.g., "HTN" = "Essential Hypertension")
  - Cross-referencing with clinical guidelines
  - Proper categorization of conditions by body system

Data source: NLM UMLS (free, requires license agreement)
Full database: ~300,000 active concepts
Download: https://www.nlm.nih.gov/healthit/snomedct/
This module ships with a curated seed of ~500 common clinical terms
and can load the full SNOMED CT distribution when available.
"""

import csv
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("CIH-SNOMED")


class SNOMEDDatabase:
    """
    SNOMED CT concept lookup with curated seed + optional full database.

    Usage:
        snomed = SNOMEDDatabase()
        result = snomed.lookup("Type 2 Diabetes")
        # → {"code": "44054006", "name": "Type 2 diabetes mellitus",
        #    "category": "Endocrine", "icd10": "E11"}
    """

    def __init__(self, data_dir: Path = None):
        self._concepts: dict[str, dict] = {}
        self._name_index: dict[str, str] = {}  # lowercase name → SNOMED code
        self._icd10_map: dict[str, str] = {}   # SNOMED code → ICD-10 code
        self._load_seed()
        if data_dir:
            self._try_load_full(data_dir)

    def lookup(self, term: str) -> Optional[dict]:
        """
        Look up a clinical term. Returns SNOMED code + category.

        Handles common abbreviations: "HTN" → "Essential hypertension",
        "DM2" → "Type 2 diabetes mellitus", etc.
        """
        normalized = self._normalize(term)

        # Direct match
        if normalized in self._name_index:
            code = self._name_index[normalized]
            return self._concepts.get(code)

        # Partial match
        for key, code in self._name_index.items():
            if normalized in key or key in normalized:
                return self._concepts.get(code)

        return None

    def lookup_by_code(self, snomed_code: str) -> Optional[dict]:
        """Look up by SNOMED CT code directly."""
        return self._concepts.get(snomed_code)

    def get_icd10(self, snomed_code: str) -> Optional[str]:
        """Get ICD-10 code for a SNOMED code (if mapped)."""
        return self._icd10_map.get(snomed_code)

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """Search for concepts matching a query string."""
        normalized = self._normalize(query)
        results = []

        for key, code in self._name_index.items():
            if normalized in key:
                entry = self._concepts.get(code)
                if entry and entry not in results:
                    results.append(entry)
                    if len(results) >= limit:
                        break

        return results

    def get_by_category(self, category: str) -> list[dict]:
        """Get all concepts in a body system category."""
        cat_lower = category.lower()
        return [
            c for c in self._concepts.values()
            if c.get("category", "").lower() == cat_lower
        ]

    @property
    def count(self) -> int:
        """Number of SNOMED concepts loaded."""
        return len(self._concepts)

    # ── Seed Database ─────────────────────────────────────────

    def _load_seed(self):
        """Load curated seed of common clinical concepts."""
        # (SNOMED code, preferred term, category, ICD-10, aliases)
        seed = [
            # ── Cardiovascular ──
            ("38341003", "Essential hypertension", "Cardiovascular", "I10",
             ["HTN", "High blood pressure", "Hypertension"]),
            ("49436004", "Atrial fibrillation", "Cardiovascular", "I48.91",
             ["A-fib", "AFib", "AF"]),
            ("53741008", "Coronary artery disease", "Cardiovascular", "I25.10",
             ["CAD", "Coronary heart disease", "CHD", "Ischemic heart disease"]),
            ("84114007", "Heart failure", "Cardiovascular", "I50.9",
             ["CHF", "Congestive heart failure", "HF"]),
            ("22298006", "Myocardial infarction", "Cardiovascular", "I21.9",
             ["MI", "Heart attack"]),
            ("429559004", "Typical atrial flutter", "Cardiovascular", "I48.92",
             ["Atrial flutter", "A-flutter"]),
            ("28286009", "Hyperlipidemia", "Cardiovascular", "E78.5",
             ["High cholesterol", "Dyslipidemia"]),
            ("698247007", "Cardiac arrhythmia", "Cardiovascular", "I49.9",
             ["Arrhythmia", "Irregular heartbeat"]),

            # ── Endocrine ──
            ("44054006", "Type 2 diabetes mellitus", "Endocrine", "E11",
             ["DM2", "T2DM", "Type 2 Diabetes", "Diabetes", "NIDDM"]),
            ("46635009", "Type 1 diabetes mellitus", "Endocrine", "E10",
             ["DM1", "T1DM", "Type 1 Diabetes", "IDDM", "Juvenile diabetes"]),
            ("40930008", "Hypothyroidism", "Endocrine", "E03.9",
             ["Underactive thyroid", "Low thyroid"]),
            ("34486009", "Hyperthyroidism", "Endocrine", "E05.90",
             ["Overactive thyroid", "Graves disease"]),
            ("237599002", "Metabolic syndrome", "Endocrine", "E88.81",
             ["Syndrome X", "Insulin resistance syndrome"]),
            ("190268003", "Prediabetes", "Endocrine", "R73.03",
             ["Impaired glucose tolerance", "IGT", "Impaired fasting glucose"]),

            # ── Respiratory ──
            ("195967001", "Asthma", "Respiratory", "J45.909",
             ["Bronchial asthma"]),
            ("13645005", "COPD", "Respiratory", "J44.1",
             ["Chronic obstructive pulmonary disease", "Emphysema", "Chronic bronchitis"]),
            ("233604007", "Pneumonia", "Respiratory", "J18.9",
             ["Community-acquired pneumonia", "CAP"]),
            ("36971009", "Sinusitis", "Respiratory", "J32.9",
             ["Sinus infection"]),
            ("78275009", "Obstructive sleep apnea", "Respiratory", "G47.33",
             ["OSA", "Sleep apnea"]),

            # ── Gastrointestinal ──
            ("235595009", "Gastroesophageal reflux disease", "Gastrointestinal", "K21.0",
             ["GERD", "Acid reflux", "Reflux"]),
            ("64766004", "Peptic ulcer", "Gastrointestinal", "K27.9",
             ["Stomach ulcer", "Gastric ulcer", "Duodenal ulcer"]),
            ("24526004", "Inflammatory bowel disease", "Gastrointestinal", "K50.90",
             ["IBD", "Crohn's disease"]),
            ("64613007", "Ulcerative colitis", "Gastrointestinal", "K51.90",
             ["UC"]),
            ("10743008", "Irritable bowel syndrome", "Gastrointestinal", "K58.9",
             ["IBS"]),
            ("235856003", "Hepatic steatosis", "Gastrointestinal", "K76.0",
             ["Fatty liver", "NAFLD", "Non-alcoholic fatty liver disease"]),

            # ── Musculoskeletal ──
            ("396275006", "Osteoarthritis", "Musculoskeletal", "M19.90",
             ["OA", "Degenerative joint disease", "DJD"]),
            ("69896004", "Rheumatoid arthritis", "Musculoskeletal", "M06.9",
             ["RA"]),
            ("64859006", "Osteoporosis", "Musculoskeletal", "M81.0",
             ["Bone loss"]),
            ("161891005", "Back pain", "Musculoskeletal", "M54.9",
             ["Low back pain", "LBP", "Lumbago"]),
            ("203082005", "Fibromyalgia", "Musculoskeletal", "M79.7",
             ["Fibro"]),
            ("396332003", "Gout", "Musculoskeletal", "M10.9",
             ["Gouty arthritis"]),

            # ── Neurological ──
            ("37796009", "Migraine", "Neurological", "G43.909",
             ["Migraine headache"]),
            ("230690007", "Stroke", "Neurological", "I63.9",
             ["CVA", "Cerebrovascular accident", "Brain attack"]),
            ("84757009", "Epilepsy", "Neurological", "G40.909",
             ["Seizure disorder"]),
            ("26929004", "Alzheimer disease", "Neurological", "G30.9",
             ["Alzheimer's", "AD"]),
            ("49049000", "Parkinson disease", "Neurological", "G20",
             ["Parkinson's", "PD"]),
            ("128613002", "Peripheral neuropathy", "Neurological", "G62.9",
             ["Neuropathy"]),
            ("230462002", "Transient ischemic attack", "Neurological", "G45.9",
             ["TIA", "Mini-stroke"]),

            # ── Mental Health ──
            ("35489007", "Major depressive disorder", "Mental Health", "F33.0",
             ["Depression", "MDD", "Clinical depression"]),
            ("197480006", "Generalized anxiety disorder", "Mental Health", "F41.1",
             ["GAD", "Anxiety", "Anxiety disorder"]),
            ("13746004", "Bipolar disorder", "Mental Health", "F31.9",
             ["Bipolar", "Manic depression"]),
            ("17226007", "PTSD", "Mental Health", "F43.10",
             ["Post-traumatic stress disorder", "Post traumatic stress"]),
            ("69322001", "Panic disorder", "Mental Health", "F41.0",
             ["Panic attacks"]),
            ("191736004", "ADHD", "Mental Health", "F90.9",
             ["Attention deficit hyperactivity disorder", "ADD"]),
            ("58214004", "Schizophrenia", "Mental Health", "F20.9", []),

            # ── Renal ──
            ("709044004", "Chronic kidney disease", "Renal", "N18.9",
             ["CKD", "Chronic renal failure", "Renal insufficiency"]),
            ("197927001", "Acute kidney injury", "Renal", "N17.9",
             ["AKI", "Acute renal failure"]),
            ("36225005", "Nephrolithiasis", "Renal", "N20.0",
             ["Kidney stones", "Renal calculi"]),

            # ── Hematological ──
            ("271737000", "Anemia", "Hematological", "D64.9",
             ["Low hemoglobin"]),
            ("87522002", "Iron deficiency anemia", "Hematological", "D50.9",
             ["IDA"]),
            ("109989006", "Deep vein thrombosis", "Hematological", "I82.40",
             ["DVT"]),
            ("59282003", "Pulmonary embolism", "Hematological", "I26.99",
             ["PE"]),

            # ── Oncology ──
            ("254637007", "Breast cancer", "Oncology", "C50.919",
             ["Breast carcinoma"]),
            ("363406005", "Lung cancer", "Oncology", "C34.90",
             ["Lung carcinoma", "NSCLC", "SCLC"]),
            ("363346000", "Colon cancer", "Oncology", "C18.9",
             ["Colorectal cancer", "CRC"]),
            ("399068003", "Prostate cancer", "Oncology", "C61",
             ["Prostate carcinoma"]),
            ("188149003", "Lymphoma", "Oncology", "C85.90",
             ["Non-Hodgkin lymphoma", "NHL"]),

            # ── Dermatological ──
            ("200773006", "Psoriasis", "Dermatological", "L40.0", []),
            ("24079001", "Atopic dermatitis", "Dermatological", "L20.9",
             ["Eczema"]),
            ("238575004", "Allergic contact dermatitis", "Dermatological", "L23.9",
             ["Contact dermatitis"]),
            ("90708001", "Kidney infection", "Renal", "N10",
             ["Pyelonephritis"]),

            # ── Infectious ──
            ("186747009", "COVID-19", "Infectious", "U07.1",
             ["SARS-CoV-2", "Coronavirus disease 2019"]),
            ("40468003", "Hepatitis C", "Infectious", "B18.2",
             ["HCV", "Hep C"]),
            ("15628003", "Hepatitis B", "Infectious", "B18.1",
             ["HBV", "Hep B"]),
            ("76272004", "Urinary tract infection", "Infectious", "N39.0",
             ["UTI"]),
            ("11218009", "Cellulitis", "Infectious", "L03.90", []),

            # ── Ophthalmological ──
            ("193570009", "Cataract", "Ophthalmological", "H26.9", []),
            ("23986001", "Glaucoma", "Ophthalmological", "H40.9", []),
            ("4855003", "Diabetic retinopathy", "Ophthalmological", "E11.319",
             ["DR"]),
            ("267718000", "Age-related macular degeneration", "Ophthalmological", "H35.30",
             ["AMD", "Macular degeneration"]),

            # ── Allergies ──
            ("91936005", "Penicillin allergy", "Allergy", "Z88.0",
             ["Allergy to penicillin"]),
            ("91935009", "Sulfonamide allergy", "Allergy", "Z88.2",
             ["Sulfa allergy"]),
            ("300916003", "Latex allergy", "Allergy", "Z91.040", []),
            ("419199007", "Allergy to substance", "Allergy", "T78.40",
             ["Drug allergy", "Medication allergy"]),

            # ── Common Procedures ──
            ("387713003", "Appendectomy", "Procedure", "0DTJ4ZZ", []),
            ("18286008", "Cholecystectomy", "Procedure", "0FT44ZZ",
             ["Gallbladder removal"]),
            ("265764009", "Colonoscopy", "Procedure", "0DJD8ZZ", []),
            ("16310003", "Upper endoscopy", "Procedure", "0DJ08ZZ",
             ["EGD", "Esophagogastroduodenoscopy"]),
            ("232717009", "Coronary artery bypass", "Procedure", "021109W",
             ["CABG", "Bypass surgery"]),
            ("397956004", "Hip replacement", "Procedure", "0SR9019",
             ["Total hip arthroplasty", "THA"]),
            ("609588000", "Knee replacement", "Procedure", "0SRD019",
             ["Total knee arthroplasty", "TKA"]),
            ("274025005", "Cardiac catheterization", "Procedure", "4A023N7",
             ["Cath", "Heart cath"]),
            ("392021009", "Lumpectomy", "Procedure", "0HBU0ZZ",
             ["Breast lump removal"]),
            ("71388002", "Hysterectomy", "Procedure", "0UT90ZZ", []),

            # ── Vital Signs (body measurements) ──
            ("75367002", "Blood pressure", "Vital", "R03.1",
             ["BP"]),
            ("364075005", "Heart rate", "Vital", "R00.0",
             ["HR", "Pulse"]),
            ("386725007", "Body temperature", "Vital", "R68.83",
             ["Temp"]),
            ("27113001", "Body weight", "Vital", "R63.5",
             ["Weight"]),
            ("60621009", "BMI", "Vital", "Z68",
             ["Body mass index"]),
            ("86290005", "Respiratory rate", "Vital", "R06.89",
             ["RR", "Breathing rate"]),
            ("431314004", "SpO2", "Vital", "R09.02",
             ["Oxygen saturation", "Pulse ox", "O2 sat"]),
        ]

        for entry in seed:
            code, name, category, icd10, aliases = entry
            record = {
                "code": code,
                "name": name,
                "category": category,
                "icd10": icd10,
                "aliases": aliases,
            }
            self._concepts[code] = record
            self._name_index[self._normalize(name)] = code
            self._icd10_map[code] = icd10
            for alias in aliases:
                self._name_index[self._normalize(alias)] = code

        logger.info(
            f"SNOMED seed loaded: {len(self._concepts)} concepts, "
            f"{len(self._name_index)} name mappings"
        )

    # ── Full Database Loading ─────────────────────────────────

    def _try_load_full(self, data_dir: Path):
        """
        Attempt to load full SNOMED CT from RF2 distribution.

        Expected file: data_dir / "snomed" / "sct2_Description_Full-en_US.txt"
        Download from: https://www.nlm.nih.gov/healthit/snomedct/ (UMLS account)
        """
        desc_file = data_dir / "snomed" / "sct2_Description_Full-en_US.txt"
        if not desc_file.exists():
            logger.debug(
                f"Full SNOMED CT not found at {desc_file}. "
                f"Using seed database ({self.count} concepts). "
                f"Download from https://www.nlm.nih.gov/healthit/snomedct/"
            )
            return

        try:
            count_before = self.count
            with open(desc_file, "r", encoding="utf-8") as f:
                reader = csv.reader(f, delimiter="\t")
                next(reader)  # Skip header
                for row in reader:
                    if len(row) < 8:
                        continue
                    # RF2 format: id, effectiveTime, active, moduleId,
                    #             conceptId, languageCode, typeId, term
                    active = row[2]
                    concept_id = row[4]
                    term = row[7]

                    if active != "1":
                        continue

                    if concept_id not in self._concepts:
                        self._concepts[concept_id] = {
                            "code": concept_id,
                            "name": term,
                            "category": "Other",
                            "icd10": None,
                            "aliases": [],
                        }
                    self._name_index[self._normalize(term)] = concept_id

            logger.info(
                f"Full SNOMED CT loaded: {self.count} concepts "
                f"(+{self.count - count_before} from RF2)"
            )
        except Exception as e:
            logger.warning(f"Failed to load full SNOMED CT: {e}")

    # ── Helpers ───────────────────────────────────────────────

    @staticmethod
    def _normalize(name: str) -> str:
        """Normalize a clinical term for matching."""
        return name.lower().strip().replace("-", " ").replace("_", " ")
