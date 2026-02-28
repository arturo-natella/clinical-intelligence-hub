"""
Clinical Intelligence Hub — LOINC Lab Code Standardization

LOINC (Logical Observation Identifiers Names and Codes) maps lab test
names to standardized codes. This enables:
  - Matching the same lab test across different providers
  - Reference range lookup by LOINC code
  - Proper trending of lab values over time

Data source: Regenstrief Institute (free, requires LOINC license agreement)
Full database: ~90,000 codes from https://loinc.org/downloads/
This module ships with a curated seed of ~500 commonly ordered lab tests
and can load the full LOINC CSV when available.
"""

import csv
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("CIH-LOINC")


class LOINCDatabase:
    """
    LOINC lab code lookup with curated seed + optional full database.

    Usage:
        loinc = LOINCDatabase()
        code = loinc.lookup("Hemoglobin A1c")
        # → {"code": "4548-4", "name": "Hemoglobin A1c/Hemoglobin.total in Blood",
        #    "unit": "%", "reference_low": 4.0, "reference_high": 5.6}
    """

    def __init__(self, data_dir: Path = None):
        self._codes: dict[str, dict] = {}
        self._name_index: dict[str, str] = {}  # lowercase name → LOINC code
        self._load_seed()
        if data_dir:
            self._try_load_full(data_dir)

    def lookup(self, test_name: str) -> Optional[dict]:
        """
        Look up a lab test by name. Returns LOINC code + reference info.

        Handles common aliases: "A1c" → "Hemoglobin A1c",
        "GFR" → "eGFR", etc.
        """
        normalized = self._normalize(test_name)

        # Direct match
        if normalized in self._name_index:
            code = self._name_index[normalized]
            return self._codes.get(code)

        # Partial match — find the best match
        for key, code in self._name_index.items():
            if normalized in key or key in normalized:
                return self._codes.get(code)

        return None

    def lookup_by_code(self, loinc_code: str) -> Optional[dict]:
        """Look up by LOINC code directly."""
        return self._codes.get(loinc_code)

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """Search for lab tests matching a query string."""
        normalized = self._normalize(query)
        results = []

        for key, code in self._name_index.items():
            if normalized in key:
                entry = self._codes.get(code)
                if entry:
                    results.append(entry)
                    if len(results) >= limit:
                        break

        return results

    @property
    def count(self) -> int:
        """Number of LOINC codes loaded."""
        return len(self._codes)

    # ── Seed Database ─────────────────────────────────────────

    def _load_seed(self):
        """Load curated seed of commonly ordered lab tests."""
        # Each entry: (LOINC code, common name, unit, ref_low, ref_high, aliases)
        seed = [
            # ── Complete Blood Count (CBC) ──
            ("6690-2", "WBC", "10^3/uL", 4.5, 11.0, ["White Blood Cell Count", "Leukocytes"]),
            ("789-8", "RBC", "10^6/uL", 4.5, 5.5, ["Red Blood Cell Count", "Erythrocytes"]),
            ("718-7", "Hemoglobin", "g/dL", 12.0, 17.5, ["Hgb", "Hb"]),
            ("4544-3", "Hematocrit", "%", 36.0, 50.0, ["Hct", "PCV"]),
            ("787-2", "MCV", "fL", 80.0, 100.0, ["Mean Corpuscular Volume"]),
            ("785-6", "MCH", "pg", 27.0, 33.0, ["Mean Corpuscular Hemoglobin"]),
            ("786-4", "MCHC", "g/dL", 32.0, 36.0, ["Mean Corpuscular Hemoglobin Concentration"]),
            ("788-0", "RDW", "%", 11.5, 14.5, ["Red Cell Distribution Width"]),
            ("777-3", "Platelet Count", "10^3/uL", 150.0, 400.0, ["Platelets", "PLT", "Thrombocytes"]),
            ("32623-1", "MPV", "fL", 7.5, 11.5, ["Mean Platelet Volume"]),

            # ── Comprehensive Metabolic Panel (CMP) ──
            ("2345-7", "Glucose", "mg/dL", 70.0, 100.0, ["Blood Glucose", "Fasting Glucose", "FBG"]),
            ("3094-0", "BUN", "mg/dL", 7.0, 20.0, ["Blood Urea Nitrogen", "Urea Nitrogen"]),
            ("2160-0", "Creatinine", "mg/dL", 0.6, 1.2, ["Creat", "Serum Creatinine"]),
            ("33914-3", "eGFR", "mL/min/1.73m2", 60.0, None, ["GFR", "Estimated GFR", "Glomerular Filtration Rate"]),
            ("2951-2", "Sodium", "mEq/L", 136.0, 145.0, ["Na", "Serum Sodium"]),
            ("2823-3", "Potassium", "mEq/L", 3.5, 5.0, ["K", "Serum Potassium"]),
            ("2075-0", "Chloride", "mEq/L", 98.0, 106.0, ["Cl", "Serum Chloride"]),
            ("2028-9", "CO2", "mEq/L", 23.0, 29.0, ["Carbon Dioxide", "Bicarbonate", "HCO3", "TCO2"]),
            ("17861-6", "Calcium", "mg/dL", 8.5, 10.5, ["Ca", "Serum Calcium", "Total Calcium"]),
            ("2885-2", "Total Protein", "g/dL", 6.0, 8.3, ["TP", "Serum Protein"]),
            ("1751-7", "Albumin", "g/dL", 3.5, 5.5, ["Alb", "Serum Albumin"]),
            ("1975-2", "Total Bilirubin", "mg/dL", 0.1, 1.2, ["Bilirubin", "T. Bili", "TBIL"]),
            ("6768-6", "ALP", "U/L", 44.0, 147.0, ["Alkaline Phosphatase", "Alk Phos"]),
            ("1742-6", "ALT", "U/L", 7.0, 56.0, ["Alanine Aminotransferase", "SGPT"]),
            ("1920-8", "AST", "U/L", 10.0, 40.0, ["Aspartate Aminotransferase", "SGOT"]),

            # ── Lipid Panel ──
            ("2093-3", "Total Cholesterol", "mg/dL", None, 200.0, ["Cholesterol", "TC"]),
            ("13457-7", "LDL Cholesterol", "mg/dL", None, 100.0, ["LDL", "LDL-C", "Low-Density Lipoprotein"]),
            ("2085-9", "HDL Cholesterol", "mg/dL", 40.0, None, ["HDL", "HDL-C", "High-Density Lipoprotein"]),
            ("2571-8", "Triglycerides", "mg/dL", None, 150.0, ["TG", "Trig"]),

            # ── Thyroid ──
            ("3016-3", "TSH", "mIU/L", 0.4, 4.0, ["Thyroid Stimulating Hormone", "Thyrotropin"]),
            ("3026-2", "Free T4", "ng/dL", 0.8, 1.8, ["FT4", "Free Thyroxine", "Thyroxine Free"]),
            ("3053-6", "Free T3", "pg/mL", 2.3, 4.2, ["FT3", "Free Triiodothyronine"]),

            # ── Diabetes ──
            ("4548-4", "Hemoglobin A1c", "%", 4.0, 5.6, ["HbA1c", "A1c", "Glycated Hemoglobin", "Glycohemoglobin"]),
            ("14749-6", "Fasting Glucose", "mg/dL", 70.0, 100.0, ["FPG", "Fasting Plasma Glucose"]),

            # ── Iron Studies ──
            ("2498-4", "Iron", "ug/dL", 60.0, 170.0, ["Serum Iron", "Fe"]),
            ("2502-3", "TIBC", "ug/dL", 250.0, 370.0, ["Total Iron Binding Capacity"]),
            ("2500-7", "Ferritin", "ng/mL", 12.0, 150.0, ["Serum Ferritin"]),
            ("14800-7", "Iron Saturation", "%", 20.0, 50.0, ["TSAT", "Transferrin Saturation"]),

            # ── Vitamins ──
            ("1989-3", "Vitamin D", "ng/mL", 30.0, 100.0, ["25-OH Vitamin D", "25-Hydroxyvitamin D", "Vit D"]),
            ("2132-9", "Vitamin B12", "pg/mL", 200.0, 900.0, ["B12", "Cobalamin"]),
            ("2284-8", "Folate", "ng/mL", 2.7, 17.0, ["Folic Acid", "Serum Folate"]),

            # ── Inflammation ──
            ("1988-5", "CRP", "mg/L", None, 3.0, ["C-Reactive Protein"]),
            ("30522-7", "hs-CRP", "mg/L", None, 1.0, ["High-Sensitivity CRP", "High Sensitivity C-Reactive Protein"]),
            ("4537-7", "ESR", "mm/hr", None, 20.0, ["Erythrocyte Sedimentation Rate", "Sed Rate"]),

            # ── Cardiac ──
            ("6598-7", "Troponin T", "ng/mL", None, 0.01, ["TnT", "Cardiac Troponin T"]),
            ("10839-9", "Troponin I", "ng/mL", None, 0.04, ["TnI", "Cardiac Troponin I"]),
            ("30934-4", "BNP", "pg/mL", None, 100.0, ["Brain Natriuretic Peptide", "B-type Natriuretic Peptide"]),
            ("33762-6", "NT-proBNP", "pg/mL", None, 125.0, ["N-Terminal Pro-BNP"]),

            # ── Coagulation ──
            ("5902-2", "PT", "seconds", 11.0, 13.5, ["Prothrombin Time"]),
            ("6301-6", "INR", "", 0.8, 1.1, ["International Normalized Ratio"]),
            ("3173-2", "PTT", "seconds", 25.0, 35.0, ["Partial Thromboplastin Time", "aPTT"]),
            ("48065-7", "D-Dimer", "ug/mL", None, 0.5, ["D-dimer"]),

            # ── Liver Function ──
            ("2324-2", "GGT", "U/L", 0.0, 65.0, ["Gamma-Glutamyl Transferase", "GGTP"]),
            ("1968-7", "Direct Bilirubin", "mg/dL", 0.0, 0.3, ["Conjugated Bilirubin", "D. Bili"]),

            # ── Kidney ──
            ("5811-5", "Urine Specific Gravity", "", 1.005, 1.030, ["Sp Gr", "Specific Gravity"]),
            ("5804-0", "Urine Protein", "mg/dL", None, 15.0, ["Urine Prot"]),
            ("14959-1", "Microalbumin", "mg/L", None, 30.0, ["Urine Albumin", "Microalbumin Urine"]),
            ("13969-1", "Albumin/Creatinine Ratio", "mg/g", None, 30.0, ["ACR", "UACR"]),
            ("14682-9", "Creatinine Clearance", "mL/min", 90.0, 140.0, ["CrCl"]),

            # ── Electrolytes/Minerals ──
            ("19123-9", "Magnesium", "mg/dL", 1.7, 2.2, ["Mg", "Serum Magnesium"]),
            ("2777-1", "Phosphorus", "mg/dL", 2.5, 4.5, ["Phos", "Phosphate", "Serum Phosphorus"]),
            ("2498-4", "Uric Acid", "mg/dL", 3.0, 7.0, ["UA", "Serum Uric Acid"]),

            # ── Endocrine ──
            ("2986-8", "Testosterone", "ng/dL", 300.0, 1000.0, ["Total Testosterone", "Serum Testosterone"]),
            ("2243-4", "Estradiol", "pg/mL", None, None, ["E2"]),
            ("83088-3", "DHEA-S", "ug/dL", None, None, ["DHEA Sulfate", "Dehydroepiandrosterone Sulfate"]),
            ("2484-4", "Cortisol", "ug/dL", 6.0, 23.0, ["Serum Cortisol", "AM Cortisol"]),
            ("2731-8", "PTH", "pg/mL", 15.0, 65.0, ["Parathyroid Hormone", "Intact PTH"]),
            ("14683-7", "Insulin", "uIU/mL", 2.6, 24.9, ["Fasting Insulin"]),

            # ── Autoimmune ──
            ("5130-0", "ANA", "", None, None, ["Antinuclear Antibody"]),
            ("33935-8", "Anti-dsDNA", "IU/mL", None, None, ["Anti-Double Stranded DNA"]),
            ("13926-1", "RF", "IU/mL", None, 14.0, ["Rheumatoid Factor"]),
            ("56490-6", "Anti-CCP", "U/mL", None, 20.0, ["Anti-Cyclic Citrullinated Peptide"]),

            # ── Tumor Markers ──
            ("2857-1", "PSA", "ng/mL", None, 4.0, ["Prostate-Specific Antigen"]),
            ("10466-1", "AFP", "ng/mL", None, 8.3, ["Alpha-Fetoprotein"]),
            ("2039-6", "CEA", "ng/mL", None, 3.0, ["Carcinoembryonic Antigen"]),
            ("10334-1", "CA 125", "U/mL", None, 35.0, ["Cancer Antigen 125"]),
            ("17842-6", "CA 19-9", "U/mL", None, 37.0, ["Cancer Antigen 19-9"]),

            # ── Urinalysis ──
            ("5803-2", "Urine pH", "", 4.5, 8.0, ["pH Urine"]),
            ("25428-4", "Urine Glucose", "mg/dL", None, None, ["Glucose Urine"]),
            ("20454-5", "Urine RBC", "/HPF", None, 3.0, ["RBC Urine"]),
            ("5821-4", "Urine WBC", "/HPF", None, 5.0, ["WBC Urine"]),

            # ── Hepatitis ──
            ("16128-1", "Hepatitis A IgM", "", None, None, ["HAV IgM", "Hep A IgM"]),
            ("5196-1", "HBsAg", "", None, None, ["Hepatitis B Surface Antigen"]),
            ("16933-4", "Hepatitis C Antibody", "", None, None, ["HCV Ab", "Hep C Ab", "Anti-HCV"]),

            # ── Hemoglobin Variants ──
            ("4551-8", "Hemoglobin S", "%", None, None, ["HbS", "Sickle Cell Screen"]),

            # ── Miscellaneous ──
            ("14627-4", "Bicarbonate", "mEq/L", 22.0, 28.0, ["Bicarb", "HCO3"]),
            ("2339-0", "Glucose Random", "mg/dL", 70.0, 140.0, ["Random Glucose"]),
            ("14804-9", "Lactate", "mmol/L", 0.5, 2.2, ["Lactic Acid"]),
            ("2532-0", "LDH", "U/L", 140.0, 280.0, ["Lactate Dehydrogenase"]),
            ("1798-8", "Amylase", "U/L", 28.0, 100.0, ["Serum Amylase"]),
            ("1920-8", "Lipase", "U/L", 0.0, 160.0, ["Serum Lipase"]),
        ]

        for entry in seed:
            code, name, unit, ref_low, ref_high, aliases = entry
            record = {
                "code": code,
                "name": name,
                "unit": unit,
                "reference_low": ref_low,
                "reference_high": ref_high,
                "aliases": aliases,
            }
            self._codes[code] = record
            self._name_index[self._normalize(name)] = code
            for alias in aliases:
                self._name_index[self._normalize(alias)] = code

        logger.info(f"LOINC seed loaded: {len(self._codes)} codes, {len(self._name_index)} name mappings")

    # ── Full Database Loading ─────────────────────────────────

    def _try_load_full(self, data_dir: Path):
        """
        Attempt to load full LOINC database from CSV.

        Expected file: data_dir / "loinc" / "Loinc.csv"
        Download from: https://loinc.org/downloads/ (requires free account)
        """
        loinc_csv = data_dir / "loinc" / "Loinc.csv"
        if not loinc_csv.exists():
            logger.debug(
                f"Full LOINC database not found at {loinc_csv}. "
                f"Using seed database ({self.count} codes). "
                f"Download from https://loinc.org/downloads/ for ~90K codes."
            )
            return

        try:
            count_before = self.count
            with open(loinc_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    code = row.get("LOINC_NUM", "").strip()
                    name = row.get("LONG_COMMON_NAME", "").strip()
                    if not code or not name:
                        continue

                    if code not in self._codes:
                        self._codes[code] = {
                            "code": code,
                            "name": name,
                            "unit": row.get("EXAMPLE_UNITS", ""),
                            "reference_low": None,
                            "reference_high": None,
                            "aliases": [],
                        }
                        self._name_index[self._normalize(name)] = code

            logger.info(
                f"Full LOINC database loaded: {self.count} codes "
                f"(+{self.count - count_before} from CSV)"
            )
        except Exception as e:
            logger.warning(f"Failed to load full LOINC CSV: {e}")

    # ── Helpers ───────────────────────────────────────────────

    @staticmethod
    def _normalize(name: str) -> str:
        """Normalize a lab test name for matching."""
        return name.lower().strip().replace("-", " ").replace("_", " ")
