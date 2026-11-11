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
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger("CIH-LOINC")

# Curated seed: (LOINC code, common name, unit, ref_low, ref_high, aliases).
# A row whose normal range depends on sex or age (testosterone, ferritin, RBC,
# iron, uric acid, ESR) has none: no single range holds for every adult, and
# a range shown beside a value reads as that patient's own.
LOINC_SEED = [
    # ── Complete Blood Count (CBC) ──
    ("6690-2", "WBC", "10^3/uL", 4.5, 11.0, ["White Blood Cell Count", "Leukocytes"]),
    ("789-8", "RBC", "10^6/uL", None, None, ["Red Blood Cell Count", "Erythrocytes"]),
    ("718-7", "Hemoglobin", "g/dL", 12.0, 17.5, ["Hgb", "Hb"]),
    ("4544-3", "Hematocrit", "%", 36.0, 50.0, ["Hct", "PCV"]),
    ("787-2", "MCV", "fL", 80.0, 100.0, ["Mean Corpuscular Volume"]),
    ("785-6", "MCH", "pg", 27.0, 33.0, ["Mean Corpuscular Hemoglobin"]),
    ("786-4", "MCHC", "g/dL", 32.0, 36.0, ["Mean Corpuscular Hemoglobin Concentration"]),
    ("788-0", "RDW", "%", 11.5, 14.5, ["Red Cell Distribution Width", "Erythrocyte distribution width", "RDW-CV"]),
    ("777-3", "Platelet Count", "10^3/uL", 150.0, 400.0, ["Platelets", "PLT", "Thrombocytes"]),
    ("32623-1", "MPV", "fL", 7.5, 11.5, ["Mean Platelet Volume"]),

    # ── Comprehensive Metabolic Panel (CMP) ──
    ("2345-7", "Glucose", "mg/dL", 70.0, 100.0, ["Blood Glucose", "Fasting Glucose", "FBG"]),
    ("3094-0", "BUN", "mg/dL", 7.0, 20.0, ["Blood Urea Nitrogen", "Urea Nitrogen"]),
    ("2160-0", "Creatinine", "mg/dL", 0.6, 1.2, ["Creat", "Serum Creatinine"]),
    ("33914-3", "eGFR", "mL/min/1.73m2", 60.0, None, ["GFR", "Estimated GFR", "Glomerular Filtration Rate",
                                                  "Glomerular filtration rate/1.73 sq M.predicted [Volume Rate/Area] in Serum or Plasma by Creatinine-based formula (MDRD)"]),
    ("2951-2", "Sodium", "mEq/L", 136.0, 145.0, ["Na", "Serum Sodium"]),
    ("2823-3", "Potassium", "mEq/L", 3.5, 5.0, ["K", "Serum Potassium"]),
    ("2075-0", "Chloride", "mEq/L", 98.0, 106.0, ["Cl", "Serum Chloride"]),
    ("2028-9", "CO2", "mEq/L", 23.0, 29.0, ["Carbon Dioxide", "Bicarbonate", "HCO3", "TCO2", "CO2 Content"]),
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
    ("2571-8", "Triglycerides", "mg/dL", None, 150.0, ["TG", "Trig", "Triglyceride"]),

    # ── Thyroid ──
    ("3016-3", "TSH", "mIU/L", 0.4, 4.0, ["Thyroid Stimulating Hormone", "Thyrotropin"]),
    ("3024-7", "Free T4", "ng/dL", 0.8, 1.8, ["FT4", "Free Thyroxine", "Thyroxine Free"]),
    ("3051-0", "Free T3", "pg/mL", 2.3, 4.2, ["FT3", "Free Triiodothyronine"]),

    # ── Diabetes ──
    ("4548-4", "Hemoglobin A1c", "%", 4.0, 5.6, ["HbA1c", "A1c", "Glycated Hemoglobin", "Glycohemoglobin", "Hgb A1c", "Hb A1c",
                                               "Hemoglobin A1c/Hemoglobin.total in Blood"]),
    ("1558-6", "Fasting Glucose", "mg/dL", 70.0, 100.0, ["FPG", "Fasting Plasma Glucose"]),

    # ── Iron Studies ──
    ("2498-4", "Iron", "ug/dL", None, None, ["Serum Iron", "Fe"]),
    ("2500-7", "TIBC", "ug/dL", 250.0, 370.0, ["Total Iron Binding Capacity", "Iron Binding Capacity"]),
    ("2276-4", "Ferritin", "ng/mL", None, None, ["Serum Ferritin"]),
    ("2502-3", "Iron Saturation", "%", 20.0, 50.0, ["TSAT", "Transferrin Saturation"]),

    # ── Vitamins ──
    ("62292-8", "Vitamin D", "ng/mL", 30.0, 100.0, ["25-OH Vitamin D", "25-Hydroxyvitamin D", "Vit D", "Vitamin D 25 Hydroxy"]),
    ("2132-9", "Vitamin B12", "pg/mL", 200.0, 900.0, ["B12", "Cobalamin"]),
    ("2284-8", "Folate", "ng/mL", 2.7, 17.0, ["Folic Acid", "Serum Folate"]),

    # ── Inflammation ──
    ("1988-5", "CRP", "mg/L", None, 3.0, ["C-Reactive Protein"]),
    ("30522-7", "hs-CRP", "mg/L", None, 1.0, ["High-Sensitivity CRP", "High Sensitivity C-Reactive Protein"]),
    ("4537-7", "ESR", "mm/hr", None, None, ["Erythrocyte Sedimentation Rate", "Sed Rate", "Sedimentation Rate"]),

    # ── Cardiac ──
    ("6598-7", "Troponin T", "ng/mL", None, 0.01, ["TnT", "Cardiac Troponin T"]),
    ("10839-9", "Troponin I", "ng/mL", None, 0.04, ["TnI", "Cardiac Troponin I"]),
    ("30934-4", "BNP", "pg/mL", None, 100.0, ["Brain Natriuretic Peptide", "B-type Natriuretic Peptide"]),
    ("33762-6", "NT-proBNP", "pg/mL", None, 125.0, ["N-Terminal Pro-BNP", "Pro-BNP", "proBNP", "NT-Pro BNP"]),

    # ── Coagulation ──
    ("5902-2", "PT", "seconds", 11.0, 13.5, ["Prothrombin Time"]),
    ("6301-6", "INR", "", 0.8, 1.1, ["International Normalized Ratio"]),
    ("14979-9", "PTT", "seconds", 25.0, 35.0, ["Partial Thromboplastin Time", "aPTT"]),
    ("48065-7", "D-Dimer", "ug/mL", None, 0.5, ["D-dimer"]),

    # ── Liver Function ──
    ("2324-2", "GGT", "U/L", 0.0, 65.0, ["Gamma-Glutamyl Transferase", "GGTP"]),
    ("1968-7", "Direct Bilirubin", "mg/dL", 0.0, 0.3, ["Conjugated Bilirubin", "D. Bili"]),

    # ── Kidney ──
    ("5811-5", "Urine Specific Gravity", "", 1.005, 1.030, ["Sp Gr", "Specific Gravity"]),
    ("5804-0", "Urine Protein", "mg/dL", None, 15.0, ["Urine Prot"]),
    ("14957-5", "Microalbumin", "mg/L", None, 30.0, ["Urine Albumin", "Microalbumin Urine"]),
    ("9318-7", "Albumin/Creatinine Ratio", "mg/g", None, 30.0, ["ACR", "UACR"]),
    ("2164-2", "Creatinine Clearance", "mL/min", 90.0, 140.0, ["CrCl"]),

    # ── Electrolytes/Minerals ──
    ("19123-9", "Magnesium", "mg/dL", 1.7, 2.2, ["Mg", "Serum Magnesium"]),
    ("2777-1", "Phosphorus", "mg/dL", 2.5, 4.5, ["Phos", "Phosphate", "Serum Phosphorus"]),
    ("3084-1", "Uric Acid", "mg/dL", None, None, ["Serum Uric Acid"]),

    # ── Endocrine ──
    ("2986-8", "Testosterone", "ng/dL", None, None, ["Total Testosterone", "Serum Testosterone", "Testosterone, Total, MS"]),
    ("2243-4", "Estradiol", "pg/mL", None, None, ["E2"]),
    ("2191-5", "DHEA-S", "ug/dL", None, None, ["DHEA Sulfate", "Dehydroepiandrosterone Sulfate"]),
    ("2143-6", "Cortisol", "ug/dL", 6.0, 23.0, ["Serum Cortisol", "AM Cortisol"]),
    ("2731-8", "PTH", "pg/mL", 15.0, 65.0, ["Parathyroid Hormone", "Intact PTH"]),
    ("20448-7", "Insulin", "uIU/mL", 2.6, 24.9, ["Fasting Insulin"]),

    # ── Autoimmune ──
    ("8061-4", "ANA", "", None, None, ["Antinuclear Antibody"]),
    ("5130-0", "Anti-dsDNA", "IU/mL", None, None, ["Anti-Double Stranded DNA"]),
    ("11572-5", "RF", "IU/mL", None, 14.0, ["Rheumatoid Factor"]),
    ("33935-8", "Anti-CCP", "U/mL", None, 20.0, ["Anti-Cyclic Citrullinated Peptide"]),

    # ── Tumor Markers ──
    ("2857-1", "PSA", "ng/mL", None, 4.0, ["Prostate-Specific Antigen"]),
    ("1834-1", "AFP", "ng/mL", None, 8.3, ["Alpha-Fetoprotein"]),
    ("2039-6", "CEA", "ng/mL", None, 3.0, ["Carcinoembryonic Antigen"]),
    ("10334-1", "CA 125", "U/mL", None, 35.0, ["Cancer Antigen 125"]),
    ("24108-3", "CA 19-9", "U/mL", None, 37.0, ["Cancer Antigen 19-9"]),

    # ── Urinalysis ──
    ("5803-2", "Urine pH", "", 4.5, 8.0, ["pH Urine"]),
    ("25428-4", "Urine Glucose", "mg/dL", None, None, ["Glucose Urine"]),
    ("13945-1", "Urine RBC", "/HPF", None, 3.0, ["RBC Urine"]),
    ("5821-4", "Urine WBC", "/HPF", None, 5.0, ["WBC Urine"]),

    # ── Hepatitis ──
    ("13950-1", "Hepatitis A IgM", "", None, None, ["HAV IgM", "Hep A IgM"]),
    ("5196-1", "HBsAg", "", None, None, ["Hepatitis B Surface Antigen"]),
    ("16128-1", "Hepatitis C Antibody", "", None, None, ["HCV Ab", "Hep C Ab", "Anti-HCV"]),

    # ── Hemoglobin Variants ──
    ("4625-0", "Hemoglobin S", "%", None, None, ["HbS", "Sickle Cell Screen"]),

    # ── Miscellaneous ──
    ("1963-8", "Bicarbonate", "mEq/L", 22.0, 28.0, ["Bicarb", "HCO3"]),
    ("2339-0", "Glucose Random", "mg/dL", 70.0, 140.0, ["Random Glucose"]),
    ("2524-7", "Lactate", "mmol/L", 0.5, 2.2, ["Lactic Acid"]),
    ("2532-0", "LDH", "U/L", 140.0, 280.0, ["Lactate Dehydrogenase"]),
    ("1798-8", "Amylase", "U/L", 28.0, 100.0, ["Serum Amylase"]),
    ("3040-3", "Lipase", "U/L", 0.0, 160.0, ["Serum Lipase"]),

]

# Words that never change which test a name refers to: the usual blood
# specimens, report filler, and method or edition words. Another specimen
# (urine, CSF, stool) and any qualifier (free, ionized, direct, ratio) are
# absent on purpose, so "Creatinine, urine" or "Free testosterone" never
# borrow the serum test.
_NEUTRAL_WORDS = frozenset({
    "serum", "plasma", "blood", "venous", "total", "level", "levels", "test",
    "result", "results", "value", "count", "quantitative", "quant", "qn",
    "in", "of", "calc", "calculated", "ngsp", "3rd", "generation", "poc",
    "poct", "ia", "inorganic", "lcms", "msms", "westergren",
})
# "Total" contradicts a test that is one fraction of the total.
_FRACTION_WORDS = frozenset({
    "free", "direct", "indirect", "ionized", "hdl", "ldl", "vldl", "unbound",
    "bioavailable", "conjugated", "unconjugated",
})
# A name joining tests ("Cholesterol/HDL", "Total & Direct") is a ratio or a
# combined row, so it matches only a name or alias written exactly that way.
_JOINED = re.compile(r"\w\s*[/:&+]\s*\w")
_SPECIMEN_PAIR = re.compile(r"\b(?:serum|plasma|ser|plas|blood)\s*/\s*(?:serum|plasma|ser|plas|blood)\b", re.I)
# "Component [Property] in System by Method", as health-record exports name
# tests. Blood-count indices leave out the system ("MCV [Entitic volume] by
# Automated count"), and some write "of Blood".
_LONG_NAME = re.compile(
    r"^\s*([^\[\]]+?)\s*\[([^\]]*)\]\s*(?:(?:in|of)\s+(.+?))?(?:\s+by\s+(.+?))?\s*$", re.I)
_BLOOD_SYSTEMS = frozenset({"serum", "plasma", "blood", "or", "venous", "ser", "plas", "bld"})
# "... by Westergren method" on a name written without a property.
_METHOD = re.compile(r"^(.+?)\s+by\s+(.+?)\s*$", re.I)
# Methods that only say how a test was run. Any other method word ("High
# sensitivity", "HPLC", "CKD-EPI") is matched as part of the name, so it
# finds the test it names, or none.
_NEUTRAL_METHOD_WORDS = frozenset({
    "automated", "manual", "count", "method", "calculation", "calculated", "calc",
    "test", "strip", "immunoassay", "ia", "assay", "coagulation", "westergren",
    # with or without P-5'-P, BCG or BCP dye binding, LDH by lactate to pyruvate
    "with", "without", "no", "addition", "of", "p", "5", "phosphate", "pyridoxal",
    "bromocresol", "green", "purple", "bcg", "bcp", "dye", "binding", "lactate",
    "pyruvate", "to", "reaction", "oximetry",
})
# "by Detection limit <= 0.005 mIU/L" is the third-generation TSH assay.
_NEUTRAL_METHOD = re.compile(r"^\s*detection\s+limit\b", re.I)
# A bracket is a LOINC property only when it names one; "Creatinine [Urine]" or
# "Calcium [Ionized]" carries a qualifier, and every word of it counts.
_PROPERTIES = frozenset({
    "mass/volume", "moles/volume", "#/volume", "#/area", "entitic volume", "entitic mass",
    "volume fraction", "mass fraction", "number fraction", "ratio", "mass ratio", "units/volume",
    "enzymatic activity/volume", "catalytic activity/volume", "presence", "titer", "time",
    "relative time", "velocity", "volume rate/area", "volume rate", "relative density",
    "partial pressure", "substance concentration", "mass concentration", "osmolality",
})
# What a long name's [Property] measures, against what a seed unit measures:
# "Glucose [Moles/volume]" is not the mg/dL glucose row.
_PROPERTY_KINDS = {
    "mass/volume": "mass", "moles/volume": "moles", "substance concentration": "moles",
    "entitic volume": "volume", "ratio": "fraction", "volume fraction": "fraction",
    "mass fraction": "fraction", "number fraction": "fraction",
}

# A record's unit, written another way, still names the same unit.
_UNIT_SYNONYMS = {
    "meq/l": "mmol/l",
    "k/ul": "10^3/ul", "x10^3/ul": "10^3/ul", "10e3/ul": "10^3/ul", "x10e3/ul": "10^3/ul",
    "10*3/ul": "10^3/ul", "thou/ul": "10^3/ul", "10^9/l": "10^3/ul", "x10^9/l": "10^3/ul",
    "10*9/l": "10^3/ul", "x10e9/l": "10^3/ul",
    "m/ul": "10^6/ul", "x10^6/ul": "10^6/ul", "10e6/ul": "10^6/ul", "x10e6/ul": "10^6/ul",
    "10*6/ul": "10^6/ul", "mil/ul": "10^6/ul", "10^12/l": "10^6/ul", "x10^12/l": "10^6/ul",
    "10*12/l": "10^6/ul", "x10e12/l": "10^6/ul",
    "ug/l": "ng/ml", "ng/l": "pg/ml", "iu/l": "u/l", "uiu/ml": "miu/l", "mu/l": "miu/l",
    "sec": "seconds", "s": "seconds", "mm/h": "mm/hr",
    "ml/min/1.73m^2": "ml/min/1.73m2", "ml/min/{1.73_m2}": "ml/min/1.73m2",
}
_UNITLESS = frozenset({"", "ratio", "{ratio}", "inr", "ph", "index"})

# Raised when the matcher, the seed codes, or the repair below change, so a
# profile saved before is repaired once more when it next loads.
CODES_VERSION = 2

# Until 2026-11-03 names were matched by raw substring ("na" inside
# "urinalysis" gave Sodium), and many rows held another test's code. These
# deltas rebuild that matcher and its codes, so values it saved can be
# recognized and redone. Each key is a row's code now; each value, its old one.
_LEGACY_CODES = {
    "3040-3": "1920-8", "3084-1": "2498-4", "3024-7": "3026-2", "3051-0": "3053-6",
    "1558-6": "14749-6", "2500-7": "2502-3", "2276-4": "2500-7", "2502-3": "14800-7",
    "62292-8": "1989-3", "14979-9": "3173-2", "14957-5": "14959-1", "9318-7": "13969-1",
    "2164-2": "14682-9", "2191-5": "83088-3", "2143-6": "2484-4", "20448-7": "14683-7",
    "8061-4": "5130-0", "5130-0": "33935-8", "11572-5": "13926-1", "33935-8": "56490-6",
    "1834-1": "10466-1", "24108-3": "17842-6", "13945-1": "20454-5", "13950-1": "16128-1",
    "16128-1": "16933-4", "4625-0": "4551-8", "1963-8": "14627-4", "2524-7": "14804-9",
}
_LEGACY_ALIASES = {"3084-1": ["UA", "Serum Uric Acid"]}
# Ranges the old seed held for rows that now have none, by each row's code now.
_LEGACY_RANGES = {
    "789-8": (4.5, 5.5), "2498-4": (60.0, 170.0), "2276-4": (12.0, 150.0), "4537-7": (None, 20.0),
    "3084-1": (3.0, 7.0), "2986-8": (300.0, 1000.0),
}
_ADDED_ALIASES = {
    "Hgb A1c", "Hb A1c", "Vitamin D 25 Hydroxy", "Iron Binding Capacity", "Triglyceride",
    "Erythrocyte distribution width", "RDW-CV", "CO2 Content", "Pro-BNP", "proBNP",
    "Hemoglobin A1c/Hemoglobin.total in Blood", "Sedimentation Rate", "NT-Pro BNP",
    "Testosterone, Total, MS",
    "Glomerular filtration rate/1.73 sq M.predicted [Volume Rate/Area] in Serum or Plasma by Creatinine-based formula (MDRD)",
}


def _unit_key(unit) -> str:
    key = str(unit or "").strip().lower().replace(" ", "").replace("µ", "u").replace("μ", "u")
    key = key.replace("mcg", "ug")
    return _UNIT_SYNONYMS.get(key, key)


def units_agree(record_unit, seed_unit) -> bool:
    """Whether a record's unit allows the seed's test; a missing unit does."""
    record = _unit_key(record_unit)
    if not record:
        return True
    seed = _unit_key(seed_unit)
    return record in _UNITLESS if seed in _UNITLESS else record == seed


def units_confirm(record_unit, seed_unit) -> bool:
    """Whether the seed's range applies: the record states the seed's unit, or
    the test has none. A value with no unit could be in another unit system."""
    seed = _unit_key(seed_unit)
    record = _unit_key(record_unit)
    if seed in _UNITLESS:
        return record in _UNITLESS
    return bool(record) and record == seed


def _unit_kind(unit) -> str:
    key = _unit_key(unit)
    if re.fullmatch(r"[mupnf]?mol/(?:l|dl|ml)", key):
        return "moles"
    if re.fullmatch(r"[kmunp]?g/(?:l|dl|ml)", key):
        return "mass"
    if key == "fl":
        return "volume"
    return "fraction" if key == "%" else ""


def _contradicts(prop, seed_unit) -> bool:
    """Whether a long name's [Property] measures another kind of quantity than the seed unit."""
    stated = _PROPERTY_KINDS.get(" ".join(str(prop or "").lower().split()), "")
    seed = _unit_kind(seed_unit)
    return bool(stated and seed and stated != seed)


def repair_saved_lab_codes(profile: dict, db: "LOINCDatabase") -> dict:
    """Redo, in place and once, the lab codes an older matcher saved in a profile.

    Only a field whose value changes is written, so each record keeps the keys
    it had. An empty profile is returned as it is.
    """
    if not isinstance(profile, dict) or not profile:
        return profile
    if (profile.get("lab_codes_version") or 0) >= CODES_VERSION:
        return profile
    for lab in (profile.get("clinical_timeline") or {}).get("labs") or []:
        if not isinstance(lab, dict):
            continue
        repaired = db.standardize(
            lab.get("name"),
            code=lab.get("loinc_code"),
            unit=lab.get("unit"),
            reference_low=lab.get("reference_low"),
            reference_high=lab.get("reference_high"),
            saved_by_old_matcher=True,
        )
        for key, value in zip(("loinc_code", "reference_low", "reference_high"), repaired):
            if lab.get(key) != value:
                lab[key] = value
    profile["lab_codes_version"] = CODES_VERSION
    return profile


def code_uncoded_labs(profile: dict, db: "LOINCDatabase") -> dict:
    """Give, in place, each lab without a code the one its name finds, as a new
    extraction would; a test moved out of procedures arrives without one.
    Only fields whose value changes are written."""
    for lab in (profile.get("clinical_timeline") or {}).get("labs") or []:
        if not isinstance(lab, dict) or lab.get("loinc_code"):
            continue
        coded = db.standardize(
            lab.get("name"),
            unit=lab.get("unit"),
            reference_low=lab.get("reference_low"),
            reference_high=lab.get("reference_high"),
        )
        for key, value in zip(("loinc_code", "reference_low", "reference_high"), coded):
            if lab.get(key) != value:
                lab[key] = value
    return profile


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
        self._name_index: dict[str, str] = {}  # normalized name → LOINC code
        self._joined_names: set[str] = set()  # normalized names written with "/", ":", "&" or "+"
        self._legacy_index: dict[str, str] = {}
        self._legacy_ranges: dict[str, tuple] = {}
        self._load_seed()
        if data_dir:
            self._try_load_full(data_dir)

    def lookup(self, test_name: str) -> Optional[dict]:
        """
        Look up a lab test by name. Returns LOINC code + reference info.

        Matches a known name or alias exactly, in any word order ("Creatinine,
        Serum"), or when every word of the name belongs to one test's names
        apart from neutral words ("AST (SGOT)", "Ferritin level"). A LOINC long
        name is read by its component, specimen and property; a method that
        names the test ("High sensitivity") stays part of the name, and one
        that only says how it was run ("Automated count") is dropped. Anything
        else, including a name that fits two tests or joins several, returns None.
        """
        name = str(test_name or "")
        exact = self._exact(name)
        if exact:
            return exact
        prop = method = None
        long_name = _LONG_NAME.match(name)
        if long_name and " ".join(long_name.group(2).lower().split()) not in _PROPERTIES:
            long_name = None
        if long_name:
            component, prop, system, method = long_name.groups()
            system_words = set(self._normalize(system).split()) if system else set()
            if system_words <= _BLOOD_SYSTEMS:
                name = component
            elif system_words == {"urine"}:
                name = f"Urine {component}"
            else:
                return None
        else:
            by_method = _METHOD.match(name)
            if by_method:
                name, method = by_method.groups()
        if method and not _NEUTRAL_METHOD.match(method):
            extra = [w for w in self._normalize(method).split() if w not in _NEUTRAL_METHOD_WORDS]
            if extra:
                if _JOINED.search(name):
                    return None
                name = f"{name} {' '.join(extra)}"
        match = self._match_name(name)
        if match and prop and _contradicts(prop, match["unit"]):
            return None
        return match

    def _exact(self, name: str) -> Optional[dict]:
        """A name or alias written exactly so; a joined name only as written joined."""
        normalized = self._normalize(name)
        if not normalized or (_JOINED.search(name) and normalized not in self._joined_names):
            return None
        code = self._name_index.get(normalized)
        return self._codes.get(code) if code else None

    def _match_name(self, name: str) -> Optional[dict]:
        name = _SPECIMEN_PAIR.sub(" serum ", name)
        normalized = self._normalize(name)
        if not normalized:
            return None
        if _JOINED.search(name):
            # Only a name written joined the same way, like "Albumin/Creatinine Ratio".
            code = self._name_index.get(normalized) if normalized in self._joined_names else None
            return self._codes.get(code) if code else None
        if normalized in self._name_index:
            return self._codes.get(self._name_index[normalized])

        words = set(normalized.split())
        covered: dict[str, set] = {}
        for key, code in self._name_index.items():
            key_words = set(key.split())
            if key_words <= words:
                covered.setdefault(code, set()).update(key_words)
        candidates = [
            code for code, known in covered.items()
            if words - known <= _NEUTRAL_WORDS
            and not ("total" in words and known & _FRACTION_WORDS)
        ]
        if len(candidates) != 1:
            return None
        return self._codes.get(candidates[0])

    def standardize(self, name, code=None, unit=None, reference_low=None,
                    reference_high=None, saved_by_old_matcher=False) -> tuple:
        """(code, reference_low, reference_high) to store for a lab entry.

        A code the record supplied is kept; one in the seed brings its range
        when the units agree. Without a code, a name this matcher knows gets
        the seed code, unless the unit shows another kind of test. A range is
        filled only when the entry has none and states the seed's unit, or the
        test has no unit. With saved_by_old_matcher, a code
        the pre-2026-11-03 matcher could have given this name, and a range its
        seed attached to the stored code, are redone first.
        """
        if saved_by_old_matcher and code:
            if (reference_low, reference_high) == self._legacy_ranges.get(code):
                reference_low = reference_high = None
            legacy = self.legacy_match(name) if name else None
            if legacy and legacy[0] == code:
                code = None

        if code:
            match = self.lookup_by_code(code)
            if match is None:
                return code, reference_low, reference_high
        else:
            match = self.lookup(name) if name else None
            if match is None or not units_agree(unit, match["unit"]):
                return None, reference_low, reference_high
            code = match["code"]

        if reference_low is None and reference_high is None and units_confirm(unit, match["unit"]):
            reference_low, reference_high = match["reference_low"], match["reference_high"]
        return code, reference_low, reference_high

    def legacy_match(self, test_name: str) -> Optional[tuple]:
        """(code, ref_low, ref_high) the pre-2026-11-03 matcher gave this name."""
        normalized = self._legacy_normalize(test_name)
        code = self._legacy_index.get(normalized)
        if code is None:
            normalized_tokens = set(normalized.split())
            matches = []
            for key, key_code in self._legacy_index.items():
                key_tokens = set(key.split())
                if (
                    normalized in key
                    or key in normalized
                    or (key_tokens and key_tokens.issubset(normalized_tokens))
                ):
                    matches.append((len(key_tokens), len(key), key_code))
            if not matches:
                return None
            _, _, code = max(matches, key=lambda match: (match[0], match[1]))
        return (code, *self._legacy_ranges[code])

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
        for entry in LOINC_SEED:
            code, name, unit, ref_low, ref_high, aliases = entry
            legacy_code = _LEGACY_CODES.get(code, code)
            legacy_names = [name] + _LEGACY_ALIASES.get(
                code, [alias for alias in aliases if alias not in _ADDED_ALIASES]
            )
            for legacy_name in legacy_names:
                self._legacy_index[self._legacy_normalize(legacy_name)] = legacy_code
            self._legacy_ranges[legacy_code] = _LEGACY_RANGES.get(code, (ref_low, ref_high))
            record = {
                "code": code,
                "name": name,
                "unit": unit,
                "reference_low": ref_low,
                "reference_high": ref_high,
                "aliases": aliases,
            }
            self._codes[code] = record
            for known in [name] + aliases:
                self._name_index[self._normalize(known)] = code
                if _JOINED.search(known):
                    self._joined_names.add(self._normalize(known))

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
            logger.warning("Failed to load full LOINC CSV (error_type=%s)", type(e).__name__)

    # ── Helpers ───────────────────────────────────────────────

    @staticmethod
    def _normalize(name: str) -> str:
        """Normalize a lab test name for matching: lowercase words, no punctuation."""
        return " ".join(re.sub(r"[^a-z0-9]+", " ", str(name or "").lower()).split())

    @staticmethod
    def _legacy_normalize(name: str) -> str:
        return str(name or "").lower().strip().replace("-", " ").replace("_", " ")
