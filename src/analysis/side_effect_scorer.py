"""
Clinical Intelligence Hub — Side Effect Scorer

5-factor scoring engine for medication side effect likelihood assessment.
Adapted from the Naranjo Adverse Drug Reaction Probability Scale.

Factors:
  1. Known side effect — matches symptom against known side effects for the medication
  2. Temporal relationship — symptom started after medication started / dose changed
  3. Dose-response — severity increased with dose increase
  4. Genetic factors — PGx profile flags increased risk (known gene-drug pairs)
  5. Alternative explanations — other concurrent medications can explain the symptom

Likelihood thresholds (matched factor count):
  0-1 = low, 2 = moderate, 3 = high, 4-5 = very_high

All clinical data is framed as "Discuss with your doctor" — never diagnostic.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional

logger = logging.getLogger("CIH-SideEffectScorer")


# ── Static Side Effect Lookup ──────────────────────────────
#
# Maps lowercase medication names to known side effects with
# relative frequency (common / uncommon / rare).
# Covers the same medications as med_lab_mapping.py.

COMMON_SIDE_EFFECTS: dict[str, dict[str, str]] = {
    # ── Diabetes ──────────────────────────────────────────
    "metformin": {
        "nausea": "common",
        "diarrhea": "common",
        "abdominal pain": "common",
        "bloating": "common",
        "gas": "common",
        "metallic taste": "common",
        "vitamin b12 deficiency": "uncommon",
        "lactic acidosis": "rare",
        "fatigue": "uncommon",
        "headache": "uncommon",
    },
    "glipizide": {
        "hypoglycemia": "common",
        "weight gain": "common",
        "dizziness": "uncommon",
        "nausea": "uncommon",
        "headache": "uncommon",
    },
    "glyburide": {
        "hypoglycemia": "common",
        "weight gain": "common",
        "nausea": "uncommon",
        "dizziness": "uncommon",
    },
    "glimepiride": {
        "hypoglycemia": "common",
        "weight gain": "common",
        "dizziness": "uncommon",
        "nausea": "uncommon",
    },
    "insulin glargine": {
        "hypoglycemia": "common",
        "injection site reaction": "common",
        "weight gain": "common",
        "edema": "uncommon",
    },
    "insulin lispro": {
        "hypoglycemia": "common",
        "injection site reaction": "common",
        "weight gain": "common",
    },
    "insulin aspart": {
        "hypoglycemia": "common",
        "injection site reaction": "common",
        "weight gain": "common",
    },
    "insulin detemir": {
        "hypoglycemia": "common",
        "injection site reaction": "common",
        "weight gain": "common",
    },
    "insulin nph": {
        "hypoglycemia": "common",
        "injection site reaction": "common",
        "weight gain": "common",
    },
    "semaglutide": {
        "nausea": "common",
        "vomiting": "common",
        "diarrhea": "common",
        "abdominal pain": "common",
        "constipation": "common",
        "headache": "uncommon",
        "fatigue": "uncommon",
        "pancreatitis": "rare",
    },
    "liraglutide": {
        "nausea": "common",
        "diarrhea": "common",
        "vomiting": "common",
        "headache": "uncommon",
        "pancreatitis": "rare",
    },
    "dulaglutide": {
        "nausea": "common",
        "diarrhea": "common",
        "vomiting": "common",
        "abdominal pain": "common",
        "fatigue": "uncommon",
    },
    "tirzepatide": {
        "nausea": "common",
        "diarrhea": "common",
        "vomiting": "common",
        "constipation": "common",
        "abdominal pain": "common",
        "heartburn": "uncommon",
    },
    "empagliflozin": {
        "urinary tract infection": "common",
        "genital yeast infection": "common",
        "increased urination": "common",
        "dehydration": "uncommon",
        "dizziness": "uncommon",
        "hypotension": "uncommon",
    },
    "dapagliflozin": {
        "urinary tract infection": "common",
        "genital yeast infection": "common",
        "increased urination": "common",
        "back pain": "uncommon",
    },
    "canagliflozin": {
        "urinary tract infection": "common",
        "genital yeast infection": "common",
        "increased urination": "common",
        "dizziness": "uncommon",
    },
    "pioglitazone": {
        "weight gain": "common",
        "edema": "common",
        "headache": "uncommon",
        "fractures": "uncommon",
        "heart failure": "rare",
    },
    "sitagliptin": {
        "headache": "uncommon",
        "upper respiratory infection": "uncommon",
        "joint pain": "uncommon",
        "pancreatitis": "rare",
    },

    # ── Cardiovascular: Statins ──────────────────────────
    "atorvastatin": {
        "muscle pain": "common",
        "muscle weakness": "uncommon",
        "joint pain": "uncommon",
        "nausea": "uncommon",
        "diarrhea": "uncommon",
        "headache": "uncommon",
        "insomnia": "uncommon",
        "rhabdomyolysis": "rare",
        "liver damage": "rare",
        "memory problems": "uncommon",
    },
    "rosuvastatin": {
        "muscle pain": "common",
        "headache": "uncommon",
        "nausea": "uncommon",
        "abdominal pain": "uncommon",
        "muscle weakness": "uncommon",
        "rhabdomyolysis": "rare",
    },
    "simvastatin": {
        "muscle pain": "common",
        "nausea": "uncommon",
        "headache": "uncommon",
        "constipation": "uncommon",
        "rhabdomyolysis": "rare",
    },
    "pravastatin": {
        "muscle pain": "common",
        "headache": "uncommon",
        "nausea": "uncommon",
        "rhabdomyolysis": "rare",
    },
    "lovastatin": {
        "muscle pain": "common",
        "headache": "uncommon",
        "constipation": "uncommon",
        "rhabdomyolysis": "rare",
    },

    # ── Cardiovascular: ACE Inhibitors / ARBs ────────────
    "lisinopril": {
        "dry cough": "common",
        "dizziness": "common",
        "headache": "uncommon",
        "fatigue": "uncommon",
        "hyperkalemia": "uncommon",
        "angioedema": "rare",
    },
    "enalapril": {
        "dry cough": "common",
        "dizziness": "common",
        "fatigue": "uncommon",
        "headache": "uncommon",
        "angioedema": "rare",
    },
    "ramipril": {
        "dry cough": "common",
        "dizziness": "common",
        "fatigue": "uncommon",
        "angioedema": "rare",
    },
    "losartan": {
        "dizziness": "common",
        "fatigue": "uncommon",
        "nasal congestion": "uncommon",
        "back pain": "uncommon",
        "diarrhea": "uncommon",
    },
    "valsartan": {
        "dizziness": "common",
        "fatigue": "uncommon",
        "headache": "uncommon",
        "abdominal pain": "uncommon",
    },
    "irbesartan": {
        "dizziness": "common",
        "fatigue": "uncommon",
        "diarrhea": "uncommon",
    },
    "olmesartan": {
        "dizziness": "common",
        "diarrhea": "uncommon",
        "sprue-like enteropathy": "rare",
    },

    # ── Cardiovascular: Beta Blockers ────────────────────
    "metoprolol succinate": {
        "fatigue": "common",
        "dizziness": "common",
        "bradycardia": "common",
        "cold extremities": "uncommon",
        "depression": "uncommon",
        "insomnia": "uncommon",
        "weight gain": "uncommon",
        "erectile dysfunction": "uncommon",
    },
    "metoprolol tartrate": {
        "fatigue": "common",
        "dizziness": "common",
        "bradycardia": "common",
        "cold extremities": "uncommon",
        "depression": "uncommon",
    },
    "atenolol": {
        "fatigue": "common",
        "dizziness": "common",
        "cold extremities": "common",
        "bradycardia": "uncommon",
        "depression": "uncommon",
    },
    "carvedilol": {
        "dizziness": "common",
        "fatigue": "common",
        "weight gain": "uncommon",
        "hypotension": "uncommon",
        "diarrhea": "uncommon",
    },
    "propranolol": {
        "fatigue": "common",
        "dizziness": "common",
        "cold extremities": "common",
        "bradycardia": "uncommon",
        "depression": "uncommon",
        "insomnia": "uncommon",
    },

    # ── Cardiovascular: Other ────────────────────────────
    "amlodipine": {
        "edema": "common",
        "dizziness": "common",
        "flushing": "common",
        "headache": "uncommon",
        "fatigue": "uncommon",
        "palpitations": "uncommon",
    },
    "hydrochlorothiazide": {
        "increased urination": "common",
        "dizziness": "common",
        "electrolyte imbalance": "common",
        "muscle cramps": "uncommon",
        "photosensitivity": "uncommon",
        "gout": "uncommon",
    },
    "furosemide": {
        "increased urination": "common",
        "dizziness": "common",
        "electrolyte imbalance": "common",
        "dehydration": "common",
        "muscle cramps": "uncommon",
        "hearing loss": "rare",
    },
    "spironolactone": {
        "hyperkalemia": "common",
        "gynecomastia": "uncommon",
        "dizziness": "uncommon",
        "nausea": "uncommon",
        "menstrual irregularity": "uncommon",
    },
    "warfarin": {
        "bleeding": "common",
        "bruising": "common",
        "nausea": "uncommon",
        "hair loss": "uncommon",
    },
    "apixaban": {
        "bleeding": "common",
        "bruising": "common",
        "nausea": "uncommon",
    },
    "rivaroxaban": {
        "bleeding": "common",
        "bruising": "common",
        "dizziness": "uncommon",
    },
    "clopidogrel": {
        "bleeding": "common",
        "bruising": "common",
        "rash": "uncommon",
        "diarrhea": "uncommon",
    },
    "aspirin": {
        "gi bleeding": "common",
        "heartburn": "common",
        "nausea": "uncommon",
        "bruising": "uncommon",
        "tinnitus": "uncommon",
    },

    # ── Thyroid ──────────────────────────────────────────
    "levothyroxine": {
        "palpitations": "uncommon",
        "tremor": "uncommon",
        "insomnia": "uncommon",
        "weight loss": "uncommon",
        "anxiety": "uncommon",
        "headache": "uncommon",
        "hair loss": "uncommon",
    },
    "methimazole": {
        "rash": "common",
        "joint pain": "uncommon",
        "nausea": "uncommon",
        "headache": "uncommon",
        "agranulocytosis": "rare",
    },
    "propylthiouracil": {
        "rash": "common",
        "joint pain": "uncommon",
        "nausea": "uncommon",
        "liver toxicity": "rare",
        "agranulocytosis": "rare",
    },

    # ── GI / Acid Suppression ────────────────────────────
    "omeprazole": {
        "headache": "common",
        "nausea": "uncommon",
        "diarrhea": "uncommon",
        "abdominal pain": "uncommon",
        "vitamin b12 deficiency": "uncommon",
        "bone fractures": "uncommon",
        "magnesium deficiency": "uncommon",
    },
    "pantoprazole": {
        "headache": "common",
        "diarrhea": "uncommon",
        "nausea": "uncommon",
        "abdominal pain": "uncommon",
    },
    "esomeprazole": {
        "headache": "common",
        "diarrhea": "uncommon",
        "nausea": "uncommon",
        "abdominal pain": "uncommon",
    },
    "lansoprazole": {
        "headache": "common",
        "diarrhea": "uncommon",
        "nausea": "uncommon",
        "abdominal pain": "uncommon",
    },

    # ── Neurological / Pain ──────────────────────────────
    "gabapentin": {
        "dizziness": "common",
        "drowsiness": "common",
        "fatigue": "common",
        "ataxia": "common",
        "peripheral edema": "uncommon",
        "weight gain": "uncommon",
        "blurred vision": "uncommon",
        "nausea": "uncommon",
        "tremor": "uncommon",
        "memory problems": "uncommon",
    },
    "pregabalin": {
        "dizziness": "common",
        "drowsiness": "common",
        "weight gain": "common",
        "peripheral edema": "uncommon",
        "blurred vision": "uncommon",
        "dry mouth": "uncommon",
    },
    "carbamazepine": {
        "dizziness": "common",
        "drowsiness": "common",
        "nausea": "common",
        "ataxia": "uncommon",
        "blurred vision": "uncommon",
        "rash": "uncommon",
        "hyponatremia": "uncommon",
        "aplastic anemia": "rare",
    },
    "valproic acid": {
        "nausea": "common",
        "weight gain": "common",
        "tremor": "common",
        "hair loss": "uncommon",
        "drowsiness": "uncommon",
        "liver toxicity": "rare",
        "pancreatitis": "rare",
    },
    "phenytoin": {
        "dizziness": "common",
        "drowsiness": "common",
        "nausea": "common",
        "gum overgrowth": "common",
        "rash": "uncommon",
        "ataxia": "uncommon",
        "nystagmus": "uncommon",
    },

    # ── Supplements ──────────────────────────────────────
    "vitamin d3": {
        "nausea": "rare",
        "constipation": "rare",
        "hypercalcemia": "rare",
    },
    "cholecalciferol": {
        "nausea": "rare",
        "constipation": "rare",
        "hypercalcemia": "rare",
    },
    "iron supplement": {
        "constipation": "common",
        "nausea": "common",
        "abdominal pain": "common",
        "dark stools": "common",
        "diarrhea": "uncommon",
    },
    "ferrous sulfate": {
        "constipation": "common",
        "nausea": "common",
        "abdominal pain": "common",
        "dark stools": "common",
        "diarrhea": "uncommon",
    },

    # ── Immunosuppressants / Rheumatology ────────────────
    "methotrexate": {
        "nausea": "common",
        "fatigue": "common",
        "mouth sores": "common",
        "hair loss": "uncommon",
        "liver toxicity": "uncommon",
        "bone marrow suppression": "uncommon",
        "pneumonitis": "rare",
    },
    "prednisone": {
        "weight gain": "common",
        "mood changes": "common",
        "insomnia": "common",
        "increased appetite": "common",
        "elevated blood sugar": "common",
        "edema": "uncommon",
        "osteoporosis": "uncommon",
        "cataracts": "uncommon",
        "adrenal suppression": "uncommon",
    },
    "hydroxychloroquine": {
        "nausea": "common",
        "diarrhea": "uncommon",
        "headache": "uncommon",
        "rash": "uncommon",
        "retinal toxicity": "rare",
    },

    # ── Gout ─────────────────────────────────────────────
    "allopurinol": {
        "rash": "common",
        "gout flare": "common",
        "nausea": "uncommon",
        "diarrhea": "uncommon",
        "hypersensitivity syndrome": "rare",
    },
    "febuxostat": {
        "gout flare": "common",
        "nausea": "uncommon",
        "liver enzyme elevation": "uncommon",
        "rash": "uncommon",
    },
    "colchicine": {
        "diarrhea": "common",
        "nausea": "common",
        "abdominal pain": "common",
        "vomiting": "uncommon",
        "bone marrow suppression": "rare",
    },
}


# ── Known Gene-Drug Pairs for PGx Side Effect Risk ────────
#
# Maps (gene, medication_class_or_name) → risk description.
# Used by factor 4 (genetic factors).

GENE_DRUG_RISK: dict[tuple[str, str], str] = {
    # Statins + SLCO1B1
    ("SLCO1B1", "atorvastatin"): "SLCO1B1 variants increase risk of statin-related myopathy",
    ("SLCO1B1", "rosuvastatin"): "SLCO1B1 variants increase risk of statin-related myopathy",
    ("SLCO1B1", "simvastatin"): "SLCO1B1 variants increase risk of statin-related myopathy (FDA warning for simvastatin)",
    ("SLCO1B1", "pravastatin"): "SLCO1B1 variants increase risk of statin-related myopathy",
    ("SLCO1B1", "lovastatin"): "SLCO1B1 variants increase risk of statin-related myopathy",

    # Codeine + CYP2D6
    ("CYP2D6", "codeine"): "CYP2D6 poor metabolizers get reduced pain relief; ultra-rapid metabolizers risk respiratory depression",
    ("CYP2D6", "tramadol"): "CYP2D6 variants affect tramadol activation and toxicity risk",

    # Clopidogrel + CYP2C19
    ("CYP2C19", "clopidogrel"): "CYP2C19 poor metabolizers have reduced clopidogrel activation (FDA boxed warning)",

    # Warfarin + CYP2C9 / VKORC1
    ("CYP2C9", "warfarin"): "CYP2C9 variants reduce warfarin metabolism — increased bleeding risk",
    ("VKORC1", "warfarin"): "VKORC1 variants increase warfarin sensitivity — lower dose needed",

    # HLA-B + Carbamazepine / Allopurinol
    ("HLA-B", "carbamazepine"): "HLA-B*15:02 increases risk of Stevens-Johnson syndrome with carbamazepine (FDA warning)",
    ("HLA-B", "allopurinol"): "HLA-B*58:01 increases risk of severe hypersensitivity reaction with allopurinol",

    # Metoprolol + CYP2D6
    ("CYP2D6", "metoprolol succinate"): "CYP2D6 poor metabolizers may experience exaggerated beta-blocker effects",
    ("CYP2D6", "metoprolol tartrate"): "CYP2D6 poor metabolizers may experience exaggerated beta-blocker effects",

    # PPIs + CYP2C19
    ("CYP2C19", "omeprazole"): "CYP2C19 ultra-rapid metabolizers may have reduced PPI efficacy",
    ("CYP2C19", "pantoprazole"): "CYP2C19 ultra-rapid metabolizers may have reduced PPI efficacy",
    ("CYP2C19", "esomeprazole"): "CYP2C19 ultra-rapid metabolizers may have reduced PPI efficacy",
    ("CYP2C19", "lansoprazole"): "CYP2C19 ultra-rapid metabolizers may have reduced PPI efficacy",

    # Fluoropyrimidines + DPYD
    ("DPYD", "fluorouracil"): "DPYD deficiency increases risk of severe/fatal toxicity with fluoropyrimidines",
    ("DPYD", "capecitabine"): "DPYD deficiency increases risk of severe/fatal toxicity with fluoropyrimidines",
}


def _normalize_name(name: str) -> str:
    """Lowercase, strip whitespace for matching."""
    return (name or "").strip().lower()


def _find_side_effect_key(medication_name: str) -> Optional[str]:
    """
    Find the COMMON_SIDE_EFFECTS key matching a medication name.
    Tries exact match first, then substring containment.
    """
    norm = _normalize_name(medication_name)
    if not norm:
        return None

    if norm in COMMON_SIDE_EFFECTS:
        return norm

    for key in COMMON_SIDE_EFFECTS:
        if key in norm or norm in key:
            return key

    return None


def _parse_date(d) -> Optional[date]:
    """Parse a date from string or date object."""
    if isinstance(d, date) and not isinstance(d, datetime):
        return d
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, str):
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
            try:
                return datetime.strptime(d.strip(), fmt).date()
            except (ValueError, TypeError):
                continue
    return None


def _extract_dose_number(dose_str: str) -> Optional[float]:
    """Extract the numeric portion from a dosage string like '500mg' or '24 units'."""
    if not dose_str:
        return None
    import re
    match = re.search(r"([\d.]+)", dose_str)
    if match:
        try:
            return float(match.group(1))
        except (ValueError, TypeError):
            return None
    return None


def _symptom_matches(symptom_name: str, known_effect: str) -> bool:
    """
    Fuzzy check whether a symptom name matches a known side effect.
    Uses substring containment in both directions.
    """
    s = _normalize_name(symptom_name)
    k = _normalize_name(known_effect)
    if not s or not k:
        return False
    return s in k or k in s


class SideEffectScorer:
    """
    5-factor scoring engine for medication side effect likelihood.

    Each factor contributes 0 or 1 to the total matched count.
    Thresholds:
      0-1 matched = low
      2   matched = moderate
      3   matched = high
      4-5 matched = very_high
    """

    # ── Factor thresholds ────────────────────────────────
    LIKELIHOOD_THRESHOLDS = {
        0: "low",
        1: "low",
        2: "moderate",
        3: "high",
        4: "very_high",
        5: "very_high",
    }

    def score_episode(
        self,
        symptom_name: str,
        episode: dict,
        medication: dict,
        all_medications: list,
        genetics: list,
    ) -> dict:
        """
        Score a single symptom episode against a medication.

        Args:
            symptom_name: Name of the symptom (e.g., "Dizziness")
            episode: Dict with episode_date, severity, linked_medication_id, etc.
            medication: Dict with name, start_date, end_date, dosage, dose_changes, etc.
            all_medications: All medications for alternative explanation check
            genetics: List of genetic variant dicts (gene, variant, phenotype, etc.)

        Returns:
            {
                likelihood: 'very_high' | 'high' | 'moderate' | 'low',
                factors: [{name, matched: bool, text: str, source: str}],
                matched_count: int,
                total_factors: 5,
                episode_id: str,
                episode_date: str,
                severity: str,
                symptom_name: str,
            }
        """
        factors = []

        # Factor 1: Known side effect
        f1 = self._check_known_side_effect(symptom_name, medication)
        factors.append(f1)

        # Factor 2: Temporal relationship
        f2 = self._check_temporal_relationship(episode, medication)
        factors.append(f2)

        # Factor 3: Dose-response
        f3 = self._check_dose_response(episode, medication)
        factors.append(f3)

        # Factor 4: Genetic factors
        f4 = self._check_genetic_factors(medication, genetics)
        factors.append(f4)

        # Factor 5: Alternative explanations
        f5 = self._check_alternative_explanations(
            symptom_name, medication, all_medications
        )
        factors.append(f5)

        matched_count = sum(1 for f in factors if f["matched"])
        likelihood = self.LIKELIHOOD_THRESHOLDS.get(matched_count, "low")

        return {
            "likelihood": likelihood,
            "factors": factors,
            "matched_count": matched_count,
            "total_factors": 5,
            "episode_id": episode.get("episode_id", ""),
            "episode_date": episode.get("episode_date"),
            "intensity": episode.get("intensity", "mid"),
            "symptom_name": symptom_name,
        }

    def score_all_linked_episodes(
        self,
        symptoms: list,
        medications: list,
        genetics: list,
    ) -> dict:
        """
        Batch scoring: find all symptom episodes with linked_medication_id
        and score them against their linked medication.

        Args:
            symptoms: List of symptom dicts (each with episodes list)
            medications: List of medication dicts
            genetics: List of genetic variant dicts

        Returns:
            {medication_name: [scored_episodes]}
        """
        result: dict[str, list] = {}

        # Build medication lookup by name (lowercase)
        med_lookup: dict[str, dict] = {}
        for med in (medications or []):
            med_name = _normalize_name(med.get("name", ""))
            if med_name:
                med_lookup[med_name] = med

        for symptom in (symptoms or []):
            symptom_name = symptom.get("symptom_name", "")
            for episode in symptom.get("episodes", []):
                linked_med = episode.get("linked_medication_id")
                if not linked_med:
                    continue

                linked_key = _normalize_name(linked_med)
                med = med_lookup.get(linked_key)
                if not med:
                    # Try substring match
                    for mk, mv in med_lookup.items():
                        if mk in linked_key or linked_key in mk:
                            med = mv
                            break

                if not med:
                    logger.warning(
                        "Linked medication '%s' not found in medication list for "
                        "symptom '%s' episode %s — skipping scoring",
                        linked_med,
                        symptom_name,
                        episode.get("episode_id", "?"),
                    )
                    continue

                scored = self.score_episode(
                    symptom_name, episode, med, medications, genetics
                )

                med_display_name = med.get("name", linked_med)
                result.setdefault(med_display_name, []).append(scored)

        return result

    # ── Factor Implementations ───────────────────────────

    def _check_known_side_effect(
        self, symptom_name: str, medication: dict
    ) -> dict:
        """Factor 1: Is this symptom a known side effect of the medication?"""
        med_name = medication.get("name", "")
        generic_name = medication.get("generic_name", "")

        se_key = _find_side_effect_key(med_name) or _find_side_effect_key(generic_name)

        if se_key is None:
            return {
                "name": "Known Side Effect",
                "matched": False,
                "text": "No side effect data available for " + med_name,
                "source": "static_lookup",
            }

        known_effects = COMMON_SIDE_EFFECTS[se_key]

        for effect_name, frequency in known_effects.items():
            if _symptom_matches(symptom_name, effect_name):
                return {
                    "name": "Known Side Effect",
                    "matched": True,
                    "text": (
                        symptom_name + " is a " + frequency
                        + " side effect of " + med_name
                    ),
                    "source": "static_lookup",
                }

        return {
            "name": "Known Side Effect",
            "matched": False,
            "text": symptom_name + " is not a commonly listed side effect of " + med_name,
            "source": "static_lookup",
        }

    def _check_temporal_relationship(
        self, episode: dict, medication: dict
    ) -> dict:
        """Factor 2: Did the symptom start after the medication started or dose changed?"""
        ep_date = _parse_date(episode.get("episode_date"))
        med_start = _parse_date(medication.get("start_date"))

        if not ep_date or not med_start:
            return {
                "name": "Temporal Relationship",
                "matched": False,
                "text": "Insufficient date information to assess timing",
                "source": "date_comparison",
            }

        if ep_date < med_start:
            return {
                "name": "Temporal Relationship",
                "matched": False,
                "text": "Symptom occurred before medication was started",
                "source": "date_comparison",
            }

        # Check if symptom happened shortly after a dose change
        dose_changes = medication.get("dose_changes", [])
        for dc in dose_changes:
            dc_date = _parse_date(dc.get("date"))
            if dc_date and ep_date >= dc_date and (ep_date - dc_date).days <= 90:
                return {
                    "name": "Temporal Relationship",
                    "matched": True,
                    "text": (
                        "Symptom occurred "
                        + str((ep_date - dc_date).days)
                        + " days after a dose change"
                    ),
                    "source": "date_comparison",
                }

        # Symptom after medication start
        days_after = (ep_date - med_start).days
        if days_after >= 0:
            return {
                "name": "Temporal Relationship",
                "matched": True,
                "text": (
                    "Symptom occurred "
                    + str(days_after)
                    + " days after starting " + medication.get("name", "medication")
                ),
                "source": "date_comparison",
            }

        return {
            "name": "Temporal Relationship",
            "matched": False,
            "text": "No clear temporal relationship found",
            "source": "date_comparison",
        }

    def _check_dose_response(self, episode: dict, medication: dict) -> dict:
        """Factor 3: Did intensity increase with a dose increase?"""
        ep_date = _parse_date(episode.get("episode_date"))
        ep_severity = _normalize_name(episode.get("intensity", ""))
        dose_changes = medication.get("dose_changes", [])

        if not ep_date or not dose_changes:
            return {
                "name": "Dose-Response",
                "matched": False,
                "text": "No dose changes recorded to assess dose-response relationship",
                "source": "dose_analysis",
            }

        # Check if a dose INCREASE preceded this episode within 90 days
        for dc in dose_changes:
            dc_date = _parse_date(dc.get("date"))
            if not dc_date:
                continue

            days_diff = (ep_date - dc_date).days
            if 0 <= days_diff <= 90:
                from_dose = _extract_dose_number(dc.get("from_dose", ""))
                to_dose = _extract_dose_number(dc.get("to_dose", ""))

                if from_dose is not None and to_dose is not None and to_dose > from_dose:
                    severity_label = ep_severity or "unknown"
                    if severity_label in ("high", "mid"):
                        return {
                            "name": "Dose-Response",
                            "matched": True,
                            "text": (
                                "Dose increased from "
                                + dc.get("from_dose", "?") + " to "
                                + dc.get("to_dose", "?")
                                + " and symptom severity is " + severity_label
                            ),
                            "source": "dose_analysis",
                        }

        return {
            "name": "Dose-Response",
            "matched": False,
            "text": "No dose increase correlates with this symptom episode",
            "source": "dose_analysis",
        }

    def _check_genetic_factors(
        self, medication: dict, genetics: list
    ) -> dict:
        """Factor 4: Does the patient's PGx profile increase risk?"""
        med_name = medication.get("name", "")
        generic_name = medication.get("generic_name", "")

        if not genetics:
            return {
                "name": "Genetic Factors",
                "matched": False,
                "text": "No genetic/pharmacogenomic data available",
                "source": "pgx_lookup",
            }

        med_norm = _normalize_name(med_name)
        generic_norm = _normalize_name(generic_name)

        for variant in genetics:
            gene = (variant.get("gene") or "").upper()
            if not gene:
                continue

            # Check direct gene-drug pair
            for (pair_gene, pair_med), risk_text in GENE_DRUG_RISK.items():
                if gene == pair_gene and (
                    pair_med == med_norm or pair_med == generic_norm
                    or pair_med in med_norm or med_norm in pair_med
                ):
                    phenotype = variant.get("phenotype", "")
                    return {
                        "name": "Genetic Factors",
                        "matched": True,
                        "text": risk_text + (
                            " (patient phenotype: " + phenotype + ")"
                            if phenotype else ""
                        ),
                        "source": "pgx_lookup",
                    }

        return {
            "name": "Genetic Factors",
            "matched": False,
            "text": "No known pharmacogenomic risk factors found for " + med_name,
            "source": "pgx_lookup",
        }

    def _check_alternative_explanations(
        self,
        symptom_name: str,
        medication: dict,
        all_medications: list,
    ) -> dict:
        """
        Factor 5: Can other concurrent medications explain this symptom?

        If NO other medication can explain it, this factor MATCHES
        (supports attribution to the linked medication).
        If YES other medications could explain it, this factor does NOT match
        (alternative explanations exist).
        """
        med_name = _normalize_name(medication.get("name", ""))
        alternatives_found = []

        for other_med in (all_medications or []):
            other_name = _normalize_name(other_med.get("name", ""))
            other_generic = _normalize_name(other_med.get("generic_name", ""))

            # Skip the medication itself
            if other_name == med_name:
                continue

            # Check if the other medication has this symptom as a known side effect
            other_key = _find_side_effect_key(other_name) or _find_side_effect_key(other_generic)
            if other_key is None:
                continue

            other_effects = COMMON_SIDE_EFFECTS[other_key]
            for effect_name in other_effects:
                if _symptom_matches(symptom_name, effect_name):
                    alternatives_found.append(other_med.get("name", other_name))
                    break

        if alternatives_found:
            return {
                "name": "No Alternative Explanations",
                "matched": False,
                "text": (
                    "Other medications could also cause "
                    + symptom_name + ": "
                    + ", ".join(alternatives_found[:3])
                ),
                "source": "medication_cross_check",
            }

        return {
            "name": "No Alternative Explanations",
            "matched": True,
            "text": "No other current medications are known to cause " + symptom_name,
            "source": "medication_cross_check",
        }
