"""
Clinical Intelligence Hub — Missing Negative Detection

Detects monitoring gaps: conditions diagnosed but expected tests missing or overdue.
Example: diabetes diagnosed but no HbA1c in 6 months → flag it.

Results feed into:
  - Flags view (severity "moderate")
  - Doctor Visit Prep "Questions to Ask" section
  - Snowball detail panel (already handled by Visit Prep printout)
"""

import logging
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger("CIH-MissingNegatives")


# ── Expected Monitoring Knowledge Base ──────────────────────
#
# Each condition maps to tests that should be performed at regular intervals.
# match_terms: strings to match against diagnoses (case-insensitive)
# expected_tests: list of {test, frequency, months} where months = max gap

EXPECTED_MONITORING = {
    "diabetes": {
        "match_terms": ["diabetes", "diabetic", "hba1c", "hyperglycemia", "dm type"],
        "expected_tests": [
            {"test": "HbA1c", "frequency": "every 3-6 months", "months": 6},
            {"test": "Lipid Panel", "frequency": "annually", "months": 12},
            {"test": "Urine Albumin", "frequency": "annually", "months": 12},
            {"test": "eGFR", "frequency": "annually", "months": 12},
            {"test": "Comprehensive Metabolic Panel", "frequency": "annually", "months": 12},
        ],
    },
    "hypothyroidism": {
        "match_terms": ["hypothyroid", "hashimoto", "thyroid", "levothyroxine"],
        "expected_tests": [
            {"test": "TSH", "frequency": "every 6-12 months", "months": 12},
            {"test": "Free T4", "frequency": "every 6-12 months", "months": 12},
        ],
    },
    "hyperthyroidism": {
        "match_terms": ["hyperthyroid", "graves", "thyrotoxicosis"],
        "expected_tests": [
            {"test": "TSH", "frequency": "every 3-6 months", "months": 6},
            {"test": "Free T4", "frequency": "every 3-6 months", "months": 6},
            {"test": "Free T3", "frequency": "every 6 months", "months": 6},
        ],
    },
    "hypertension": {
        "match_terms": ["hypertension", "high blood pressure", "htn"],
        "expected_tests": [
            {"test": "Basic Metabolic Panel", "frequency": "annually", "months": 12},
            {"test": "Lipid Panel", "frequency": "annually", "months": 12},
            {"test": "Urinalysis", "frequency": "annually", "months": 12},
        ],
    },
    "chronic_kidney_disease": {
        "match_terms": ["chronic kidney", "ckd", "renal insufficiency", "kidney disease"],
        "expected_tests": [
            {"test": "eGFR", "frequency": "every 3-6 months", "months": 6},
            {"test": "Urine Albumin", "frequency": "every 6-12 months", "months": 12},
            {"test": "Basic Metabolic Panel", "frequency": "every 3-6 months", "months": 6},
            {"test": "CBC", "frequency": "annually", "months": 12},
            {"test": "Phosphorus", "frequency": "annually", "months": 12},
            {"test": "Vitamin D", "frequency": "annually", "months": 12},
        ],
    },
    "heart_failure": {
        "match_terms": ["heart failure", "chf", "congestive", "cardiomyopathy"],
        "expected_tests": [
            {"test": "BNP", "frequency": "every 3-6 months", "months": 6},
            {"test": "Basic Metabolic Panel", "frequency": "every 3-6 months", "months": 6},
            {"test": "CBC", "frequency": "annually", "months": 12},
            {"test": "Echocardiogram", "frequency": "annually", "months": 12},
        ],
    },
    "atrial_fibrillation": {
        "match_terms": ["atrial fibrillation", "afib", "a-fib", "irregular rhythm"],
        "expected_tests": [
            {"test": "INR", "frequency": "monthly if on warfarin", "months": 3},
            {"test": "TSH", "frequency": "annually", "months": 12},
            {"test": "Echocardiogram", "frequency": "annually", "months": 18},
        ],
    },
    "copd": {
        "match_terms": ["copd", "chronic obstructive", "emphysema", "chronic bronchitis"],
        "expected_tests": [
            {"test": "Spirometry", "frequency": "annually", "months": 12},
            {"test": "CBC", "frequency": "annually", "months": 12},
            {"test": "Chest X-Ray", "frequency": "as needed", "months": 24},
        ],
    },
    "asthma": {
        "match_terms": ["asthma", "reactive airway"],
        "expected_tests": [
            {"test": "Spirometry", "frequency": "every 1-2 years", "months": 24},
            {"test": "Peak Flow", "frequency": "ongoing", "months": 12},
        ],
    },
    "rheumatoid_arthritis": {
        "match_terms": ["rheumatoid", "ra ", "rheumatoid arthritis"],
        "expected_tests": [
            {"test": "ESR", "frequency": "every 3-6 months", "months": 6},
            {"test": "CRP", "frequency": "every 3-6 months", "months": 6},
            {"test": "CBC", "frequency": "every 3-6 months", "months": 6},
            {"test": "Liver Function Tests", "frequency": "every 3-6 months", "months": 6},
        ],
    },
    "lupus": {
        "match_terms": ["lupus", "sle", "systemic lupus"],
        "expected_tests": [
            {"test": "ANA", "frequency": "at diagnosis", "months": 24},
            {"test": "CBC", "frequency": "every 3-6 months", "months": 6},
            {"test": "Urinalysis", "frequency": "every 3-6 months", "months": 6},
            {"test": "Complement C3/C4", "frequency": "every 6 months", "months": 6},
            {"test": "Anti-dsDNA", "frequency": "every 6-12 months", "months": 12},
        ],
    },
    "liver_disease": {
        "match_terms": ["liver disease", "hepatitis", "cirrhosis", "fatty liver", "nafld", "nash"],
        "expected_tests": [
            {"test": "Liver Function Tests", "frequency": "every 3-6 months", "months": 6},
            {"test": "Albumin", "frequency": "every 6 months", "months": 6},
            {"test": "INR", "frequency": "every 6 months", "months": 6},
            {"test": "Hepatitis Panel", "frequency": "at diagnosis", "months": 24},
        ],
    },
    "osteoporosis": {
        "match_terms": ["osteoporosis", "osteopenia", "bone density"],
        "expected_tests": [
            {"test": "DEXA Scan", "frequency": "every 1-2 years", "months": 24},
            {"test": "Vitamin D", "frequency": "annually", "months": 12},
            {"test": "Calcium", "frequency": "annually", "months": 12},
        ],
    },
    "anemia": {
        "match_terms": ["anemia", "iron deficiency", "b12 deficiency"],
        "expected_tests": [
            {"test": "CBC", "frequency": "every 3-6 months", "months": 6},
            {"test": "Iron Studies", "frequency": "every 6-12 months", "months": 12},
            {"test": "Vitamin B12", "frequency": "annually", "months": 12},
            {"test": "Folate", "frequency": "annually", "months": 12},
        ],
    },
    "hyperlipidemia": {
        "match_terms": ["hyperlipidemia", "high cholesterol", "dyslipidemia", "statin"],
        "expected_tests": [
            {"test": "Lipid Panel", "frequency": "every 6-12 months", "months": 12},
            {"test": "Liver Function Tests", "frequency": "annually if on statin", "months": 12},
        ],
    },
    "gout": {
        "match_terms": ["gout", "hyperuricemia", "uric acid"],
        "expected_tests": [
            {"test": "Uric Acid", "frequency": "every 6 months", "months": 6},
            {"test": "Basic Metabolic Panel", "frequency": "annually", "months": 12},
        ],
    },
    "celiac_disease": {
        "match_terms": ["celiac", "coeliac", "gluten"],
        "expected_tests": [
            {"test": "tTG-IgA", "frequency": "annually", "months": 12},
            {"test": "CBC", "frequency": "annually", "months": 12},
            {"test": "Iron Studies", "frequency": "annually", "months": 12},
            {"test": "Vitamin D", "frequency": "annually", "months": 12},
            {"test": "DEXA Scan", "frequency": "every 2 years", "months": 24},
        ],
    },
    "multiple_sclerosis": {
        "match_terms": ["multiple sclerosis", "ms ", "demyelinating"],
        "expected_tests": [
            {"test": "MRI Brain", "frequency": "annually", "months": 18},
            {"test": "Vitamin D", "frequency": "annually", "months": 12},
            {"test": "CBC", "frequency": "every 6 months", "months": 6},
            {"test": "Liver Function Tests", "frequency": "every 6 months", "months": 6},
        ],
    },
    "epilepsy": {
        "match_terms": ["epilepsy", "seizure disorder", "anticonvulsant"],
        "expected_tests": [
            {"test": "Drug Levels", "frequency": "every 6-12 months", "months": 12},
            {"test": "CBC", "frequency": "annually", "months": 12},
            {"test": "Liver Function Tests", "frequency": "annually", "months": 12},
        ],
    },
    "pcos": {
        "match_terms": ["pcos", "polycystic ovary", "polycystic ovarian"],
        "expected_tests": [
            {"test": "Fasting Glucose", "frequency": "annually", "months": 12},
            {"test": "HbA1c", "frequency": "annually", "months": 12},
            {"test": "Lipid Panel", "frequency": "annually", "months": 12},
            {"test": "Testosterone", "frequency": "annually", "months": 12},
        ],
    },
}


class MissingNegativeDetector:
    """Detects expected tests that are missing or overdue for diagnosed conditions."""

    def analyze(self, profile_data: dict) -> list:
        """
        Returns list of missing/overdue tests:
        [
            {
                "condition": "Diabetes",
                "missing_test": "HbA1c",
                "expected_frequency": "every 3-6 months",
                "status": "overdue" | "never_tested",
                "last_tested": "2025-06-15" | null,
                "months_overdue": 8 | null,
                "recommendation": "HbA1c is typically checked every 3-6 months for diabetes monitoring.",
                "severity": "moderate"
            },
            ...
        ]
        """
        timeline = profile_data.get("clinical_timeline", {})
        diagnoses = timeline.get("diagnoses", [])
        labs = timeline.get("labs", [])
        medications = timeline.get("medications", [])

        if not diagnoses:
            return []

        # Build lab history: test_name (lowered) → most recent date
        lab_history = self._build_lab_history(labs)

        # Also check medication list for condition hints
        # (e.g., "levothyroxine" implies hypothyroidism even if not in diagnoses)
        med_names = [
            m.get("name", "").lower()
            for m in medications
            if m.get("status", "").lower() not in ("discontinued", "stopped")
        ]

        # Find which conditions the patient has
        active_conditions = self._match_conditions(diagnoses, med_names)

        # Check each condition's expected tests
        results = []
        today = date.today()

        for cond_key, cond_config in active_conditions.items():
            cond_label = cond_key.replace("_", " ").title()

            for test_spec in cond_config["expected_tests"]:
                test_name = test_spec["test"]
                max_months = test_spec["months"]
                frequency = test_spec["frequency"]

                # Look up in lab history
                last_date = self._find_test_in_history(test_name, lab_history)

                if last_date is None:
                    # Never tested
                    results.append({
                        "condition": cond_label,
                        "missing_test": test_name,
                        "expected_frequency": frequency,
                        "status": "never_tested",
                        "last_tested": None,
                        "months_overdue": None,
                        "recommendation": (
                            f"{test_name} is typically checked {frequency} "
                            f"for {cond_label.lower()} monitoring. "
                            f"No record of this test was found."
                        ),
                        "severity": "moderate",
                    })
                else:
                    # Check if overdue
                    cutoff = today - timedelta(days=max_months * 30)
                    if last_date < cutoff:
                        months_since = (today - last_date).days // 30
                        months_over = months_since - max_months
                        results.append({
                            "condition": cond_label,
                            "missing_test": test_name,
                            "expected_frequency": frequency,
                            "status": "overdue",
                            "last_tested": last_date.isoformat(),
                            "months_overdue": months_over,
                            "recommendation": (
                                f"{test_name} was last done {months_since} months ago. "
                                f"For {cond_label.lower()}, it's typically checked "
                                f"{frequency}."
                            ),
                            "severity": "moderate",
                        })

        # Sort: never_tested first, then by months overdue
        results.sort(key=lambda r: (
            0 if r["status"] == "never_tested" else 1,
            -(r.get("months_overdue") or 999),
        ))

        logger.info(
            "Missing negative analysis: %d gaps found across %d conditions",
            len(results),
            len(active_conditions),
        )

        return results

    # ── Helpers ──────────────────────────────────────────

    def _build_lab_history(self, labs: list) -> dict:
        """Build lookup: lowered test name → most recent date."""
        history = {}
        for lab in labs:
            name = lab.get("name", "").lower().strip()
            date_str = lab.get("test_date") or lab.get("date", "")
            if not name or not date_str:
                continue
            try:
                if isinstance(date_str, str):
                    test_date = date.fromisoformat(date_str[:10])
                else:
                    test_date = date_str
            except (ValueError, TypeError):
                continue

            if name not in history or test_date > history[name]:
                history[name] = test_date

        return history

    def _match_conditions(self, diagnoses: list, med_names: list) -> dict:
        """Match patient diagnoses against EXPECTED_MONITORING conditions."""
        matched = {}

        # Build a search corpus from diagnoses + meds
        corpus = []
        for dx in diagnoses:
            name = dx.get("name", "").lower()
            status = dx.get("status", "").lower()
            if status not in ("resolved", "inactive", "historical"):
                corpus.append(name)

        corpus.extend(med_names)
        corpus_text = " ".join(corpus)

        for cond_key, cond_config in EXPECTED_MONITORING.items():
            for term in cond_config["match_terms"]:
                if term.lower() in corpus_text:
                    matched[cond_key] = cond_config
                    break

        return matched

    def _find_test_in_history(
        self, test_name: str, lab_history: dict
    ) -> Optional[date]:
        """
        Find a test in the lab history using flexible matching.
        E.g., "HbA1c" matches "hba1c", "hemoglobin a1c", "glycated hemoglobin".
        """
        test_lower = test_name.lower()

        # Direct match
        if test_lower in lab_history:
            return lab_history[test_lower]

        # Synonym matching for common tests
        synonyms = _TEST_SYNONYMS.get(test_lower, [])
        for syn in synonyms:
            if syn in lab_history:
                return lab_history[syn]

        # Partial match: if any lab name contains our test name
        for lab_name, lab_date in lab_history.items():
            if test_lower in lab_name or lab_name in test_lower:
                return lab_date

        return None


# ── Test Name Synonyms ──────────────────────────────────

_TEST_SYNONYMS = {
    "hba1c": [
        "hemoglobin a1c", "glycated hemoglobin", "a1c", "glycohemoglobin",
    ],
    "lipid panel": [
        "lipid profile", "cholesterol panel", "fasting lipids",
    ],
    "cbc": [
        "complete blood count", "blood count", "full blood count",
    ],
    "tsh": [
        "thyroid stimulating hormone", "thyrotropin",
    ],
    "free t4": [
        "ft4", "free thyroxine", "thyroxine free",
    ],
    "free t3": [
        "ft3", "free triiodothyronine",
    ],
    "egfr": [
        "estimated gfr", "glomerular filtration", "gfr",
    ],
    "urine albumin": [
        "microalbumin", "urine microalbumin", "albumin urine",
        "urine albumin/creatinine", "uacr",
    ],
    "liver function tests": [
        "lft", "hepatic panel", "hepatic function", "alt", "ast",
        "liver panel",
    ],
    "basic metabolic panel": [
        "bmp", "basic metabolic", "chem 7",
    ],
    "comprehensive metabolic panel": [
        "cmp", "comprehensive metabolic", "chem 14",
    ],
    "iron studies": [
        "iron panel", "ferritin", "serum iron", "tibc",
    ],
    "vitamin d": [
        "25-hydroxy vitamin d", "25-oh vitamin d", "vitamin d 25",
        "cholecalciferol",
    ],
    "vitamin b12": [
        "b12", "cobalamin", "cyanocobalamin",
    ],
    "bnp": [
        "brain natriuretic peptide", "nt-probnp", "pro-bnp",
    ],
    "inr": [
        "international normalized ratio", "prothrombin time", "pt/inr",
    ],
    "esr": [
        "erythrocyte sedimentation rate", "sed rate",
    ],
    "crp": [
        "c-reactive protein", "hs-crp", "high sensitivity crp",
    ],
    "uric acid": [
        "serum uric acid", "urate",
    ],
    "ana": [
        "antinuclear antibody", "antinuclear antibodies",
    ],
    "anti-dsdna": [
        "anti-double stranded dna", "dsdna", "double stranded dna",
    ],
    "complement c3/c4": [
        "complement", "c3", "c4", "complement levels",
    ],
    "ttg-iga": [
        "tissue transglutaminase", "ttg", "celiac panel",
    ],
    "dexa scan": [
        "bone density", "bone densitometry", "dxa",
    ],
    "spirometry": [
        "pulmonary function", "pft", "lung function",
    ],
    "echocardiogram": [
        "echo", "cardiac ultrasound", "transthoracic echo",
    ],
    "hepatitis panel": [
        "hep panel", "hepatitis b", "hepatitis c", "hbsag", "hcv",
    ],
    "fasting glucose": [
        "fasting blood sugar", "fbs", "fasting plasma glucose",
    ],
    "testosterone": [
        "total testosterone", "free testosterone", "serum testosterone",
    ],
    "drug levels": [
        "medication levels", "therapeutic drug monitoring",
    ],
    "urinalysis": [
        "ua", "urine analysis", "dipstick",
    ],
    "peak flow": [
        "pef", "peak expiratory flow",
    ],
    "mri brain": [
        "brain mri", "head mri", "cranial mri",
    ],
    "chest x-ray": [
        "cxr", "chest radiograph", "chest xr",
    ],
}
