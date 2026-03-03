"""
Clinical Intelligence Hub — AI-Enhanced Clinical Matcher

Provides semantic matching for clinical findings, resolving synonyms
and abbreviations that substring matching misses.

Cascade: Gemini (cloud) -> Ollama/Qwen (local) -> built-in synonym table

Examples of what this catches that substring matching misses:
  - "SOB" matches "dyspnea" / "shortness of breath"
  - "heart failure" matches "cardiac decompensation"
  - "elevated glucose" matches "hyperglycemia"
  - "low platelets" matches "thrombocytopenia"
"""

import json
import logging
from typing import Optional

logger = logging.getLogger("CIH-AIMatcher")


# ── Built-in Synonym Table (Tier 3 fallback) ─────────────────
# Covers the most common clinical abbreviations and synonyms.
# This runs when no LLM is available and catches ~80% of synonym
# mismatches without any API calls.

CLINICAL_SYNONYMS = {
    # Cardiac
    "heart failure": ["chf", "congestive heart failure", "cardiac decompensation", "hf", "hfref", "hfpef", "ventricular failure"],
    "cardiomegaly": ["enlarged heart", "cardiac enlargement"],
    "atrial fibrillation": ["afib", "a-fib", "af", "irregular heartbeat", "irregular rhythm"],
    "coronary artery disease": ["cad", "ischemic heart disease", "ihd", "coronary heart disease", "chd"],
    "myocardial infarction": ["mi", "heart attack", "stemi", "nstemi", "acute coronary syndrome", "acs"],
    "hypertension": ["htn", "high blood pressure", "elevated bp", "elevated blood pressure"],
    "hypotension": ["low blood pressure", "low bp"],
    "tachycardia": ["rapid heart rate", "fast heart rate", "elevated heart rate", "elevated hr"],
    "bradycardia": ["slow heart rate", "low heart rate"],
    "murmur": ["heart murmur", "cardiac murmur", "systolic murmur", "diastolic murmur"],
    "edema": ["swelling", "fluid retention", "peripheral edema", "pitting edema", "leg swelling", "ankle swelling"],

    # Pulmonary
    "dyspnea": ["shortness of breath", "sob", "difficulty breathing", "breathlessness", "air hunger"],
    "copd": ["chronic obstructive pulmonary disease", "emphysema", "chronic bronchitis"],
    "pneumonia": ["lung infection", "pulmonary infection", "community acquired pneumonia", "cap"],
    "pulmonary embolism": ["pe", "lung clot", "pulmonary thromboembolism"],
    "wheezing": ["wheeze", "bronchospasm"],
    "cough": ["chronic cough", "productive cough", "dry cough"],
    "hemoptysis": ["coughing blood", "coughing up blood", "blood in sputum"],
    "hypoxia": ["low oxygen", "low o2", "oxygen desaturation", "desaturation", "hypoxemia"],
    "pleural effusion": ["fluid around lung", "fluid on lung", "lung fluid"],

    # Endocrine
    "diabetes": ["dm", "diabetes mellitus", "dm2", "type 2 diabetes", "t2dm", "hyperglycemia", "elevated glucose", "high blood sugar"],
    "hypothyroidism": ["underactive thyroid", "low thyroid", "hashimoto", "hashimotos", "elevated tsh"],
    "hyperthyroidism": ["overactive thyroid", "high thyroid", "graves", "graves disease", "low tsh", "suppressed tsh"],
    "thyroid nodule": ["thyroid mass", "thyroid lump"],

    # Renal
    "renal insufficiency": ["kidney disease", "ckd", "chronic kidney disease", "renal failure", "decreased gfr", "low gfr", "elevated creatinine", "high creatinine"],
    "proteinuria": ["protein in urine", "urine protein", "albuminuria", "microalbuminuria"],
    "hematuria": ["blood in urine", "urine blood"],

    # Hepatic
    "cirrhosis": ["liver disease", "chronic liver disease", "hepatic cirrhosis", "liver fibrosis"],
    "hepatitis": ["liver inflammation", "elevated liver enzymes", "elevated alt", "elevated ast", "transaminitis"],
    "jaundice": ["icterus", "yellowing", "elevated bilirubin", "high bilirubin"],
    "ascites": ["abdominal fluid", "peritoneal fluid"],

    # Hematologic
    "anemia": ["low hemoglobin", "low hgb", "low hb", "low red blood cells", "low rbc", "low hematocrit"],
    "thrombocytopenia": ["low platelets", "low platelet count"],
    "leukocytosis": ["elevated wbc", "high wbc", "high white blood cells", "elevated white count"],
    "leukopenia": ["low wbc", "low white blood cells", "low white count"],
    "pancytopenia": ["low blood counts", "low all counts"],
    "coagulopathy": ["bleeding disorder", "elevated inr", "elevated pt", "prolonged ptt"],
    "dvt": ["deep vein thrombosis", "deep venous thrombosis", "leg clot", "venous thromboembolism", "vte"],

    # Autoimmune
    "lupus": ["sle", "systemic lupus erythematosus", "systemic lupus"],
    "rheumatoid arthritis": ["ra", "inflammatory arthritis"],
    "sjogren": ["sjogrens", "sjogren syndrome", "sjogrens syndrome", "dry eyes dry mouth"],
    "vasculitis": ["vessel inflammation", "blood vessel inflammation"],
    "malar rash": ["butterfly rash", "facial rash"],
    "raynaud": ["raynauds", "raynaud phenomenon", "cold fingers", "color changes fingers"],

    # Neurologic
    "stroke": ["cva", "cerebrovascular accident", "cerebral infarction", "ischemic stroke", "hemorrhagic stroke", "tia", "transient ischemic attack"],
    "neuropathy": ["peripheral neuropathy", "nerve damage", "nerve pain", "numbness tingling", "paresthesia", "paresthesias"],
    "seizure": ["epilepsy", "convulsion", "seizure disorder"],
    "headache": ["migraine", "tension headache", "cluster headache", "cephalalgia"],

    # GI
    "pancreatitis": ["pancreatic inflammation", "elevated lipase", "elevated amylase"],
    "gerd": ["acid reflux", "heartburn", "gastroesophageal reflux", "reflux disease"],
    "ibs": ["irritable bowel syndrome", "irritable bowel"],
    "ibd": ["inflammatory bowel disease", "crohns", "crohn disease", "ulcerative colitis"],
    "celiac": ["celiac disease", "coeliac", "gluten sensitivity", "gluten intolerance"],

    # Musculoskeletal
    "osteoporosis": ["low bone density", "bone loss", "osteopenia"],
    "fibromyalgia": ["widespread pain", "chronic widespread pain", "fibro"],
    "gout": ["gouty arthritis", "elevated uric acid", "hyperuricemia"],

    # Infectious
    "sepsis": ["septicemia", "systemic infection", "bacteremia", "septic"],
    "uti": ["urinary tract infection", "bladder infection", "cystitis", "pyelonephritis"],

    # Metabolic
    "metabolic syndrome": ["insulin resistance", "syndrome x"],
    "hyperkalemia": ["high potassium", "elevated potassium", "elevated k"],
    "hypokalemia": ["low potassium", "low k"],
    "hypernatremia": ["high sodium", "elevated sodium", "elevated na"],
    "hyponatremia": ["low sodium", "low na"],
    "hypercalcemia": ["high calcium", "elevated calcium"],
    "hypocalcemia": ["low calcium"],

    # Other
    "obesity": ["obese", "bmi over 30", "elevated bmi", "overweight"],
    "fatigue": ["tiredness", "exhaustion", "malaise", "lethargy"],
    "weight loss": ["unintentional weight loss", "unexplained weight loss"],
    "fever": ["febrile", "elevated temperature", "pyrexia"],
    "lymphadenopathy": ["swollen lymph nodes", "enlarged lymph nodes", "swollen glands"],
}

# Build reverse lookup: synonym_text -> canonical_term
_REVERSE_SYNONYMS = {}
for canonical, synonyms in CLINICAL_SYNONYMS.items():
    for syn in synonyms:
        _REVERSE_SYNONYMS[syn] = canonical
    _REVERSE_SYNONYMS[canonical] = canonical


# ── Demographic Risk Adjustments ──────────────────────────────
# Multipliers for conditions that are significantly more/less common
# in certain demographics. Applied post-scoring to shift confidence.

DEMOGRAPHIC_WEIGHTS = {
    "lupus": {"female": 9.0, "male": 0.11, "age_peak": (20, 45)},
    "rheumatoid_arthritis": {"female": 3.0, "male": 0.33, "age_peak": (30, 60)},
    "osteoporosis": {"female": 4.0, "male": 0.25, "age_peak": (50, 999)},
    "gout": {"female": 0.25, "male": 4.0, "age_peak": (30, 70)},
    "coronary_artery_disease": {"female": 0.5, "male": 2.0, "age_peak": (45, 999)},
    "heart_failure": {"male": 1.5, "female": 0.7, "age_peak": (55, 999)},
    "atrial_fibrillation": {"age_peak": (60, 999)},
    "hypothyroidism": {"female": 5.0, "male": 0.2, "age_peak": (30, 999)},
    "hyperthyroidism": {"female": 5.0, "male": 0.2, "age_peak": (20, 50)},
    "fibromyalgia": {"female": 7.0, "male": 0.14, "age_peak": (30, 60)},
    "dvt": {"age_peak": (40, 999)},
    "pulmonary_embolism": {"age_peak": (40, 999)},
    "type_2_diabetes": {"age_peak": (40, 999)},
    "celiac_disease": {"female": 2.0, "male": 0.5},
    "sjogren_syndrome": {"female": 9.0, "male": 0.11, "age_peak": (40, 60)},
    "ankylosing_spondylitis": {"female": 0.33, "male": 3.0, "age_peak": (17, 45)},
    "multiple_sclerosis": {"female": 3.0, "male": 0.33, "age_peak": (20, 50)},
}


class AIMatcher:
    """AI-enhanced clinical matching with LLM cascade.

    Cascade order:
      1. Built-in synonym table (instant, always available)
      2. Gemini cloud API (best quality, needs API key)
      3. Ollama/Qwen local (good quality, needs local setup)

    The synonym table handles ~80% of cases. LLM calls only fire
    for unmatched patterns where semantic understanding is needed.
    """

    def __init__(self, api_key: str = None):
        self._api_key = api_key
        self._cache = {}  # cache LLM synonym resolutions

    def semantic_match(
        self, finding_text: str, patterns: list, corpus: list
    ) -> list:
        """Match a finding against patterns using semantic understanding.

        Returns list of matched pattern strings.
        """
        finding_lower = finding_text.lower().strip()
        matched = []

        for pattern in patterns:
            pattern_lower = pattern.lower().strip()

            # 1. Direct substring (already done by Snowball, but included for completeness)
            if pattern_lower in finding_lower or finding_lower in pattern_lower:
                matched.append(pattern)
                continue

            # 2. Synonym table lookup
            if self._synonym_match(finding_lower, pattern_lower):
                matched.append(pattern)
                continue

        return matched

    def resolve_synonyms(self, term: str) -> list:
        """Return known synonyms for a clinical term."""
        term_lower = term.lower().strip()

        # Check cache
        if term_lower in self._cache:
            return self._cache[term_lower]

        # Check synonym table
        result = []
        if term_lower in CLINICAL_SYNONYMS:
            result = list(CLINICAL_SYNONYMS[term_lower])
        elif term_lower in _REVERSE_SYNONYMS:
            canonical = _REVERSE_SYNONYMS[term_lower]
            result = [canonical] + [
                s for s in CLINICAL_SYNONYMS.get(canonical, [])
                if s != term_lower
            ]

        # LLM expansion for terms not in our table
        if not result and self._api_key:
            result = self._llm_synonyms(term_lower)

        self._cache[term_lower] = result
        return result

    def assess_demographic_weight(
        self, condition_id: str, age: int = None, sex: str = None
    ) -> float:
        """Return a multiplier based on demographic fit.

        Returns 1.0 (no adjustment) if no demographic data or no
        known demographic pattern for this condition.
        """
        # Normalize condition ID to match our table keys
        key = condition_id.lower().replace(" ", "_").replace("-", "_")

        weights = DEMOGRAPHIC_WEIGHTS.get(key)
        if not weights:
            return 1.0

        multiplier = 1.0

        # Sex-based adjustment
        if sex:
            sex_lower = sex.lower().strip()
            if sex_lower in ("f", "female"):
                multiplier *= weights.get("female", 1.0)
            elif sex_lower in ("m", "male"):
                multiplier *= weights.get("male", 1.0)

        # Age-based adjustment
        if age is not None and "age_peak" in weights:
            lo, hi = weights["age_peak"]
            if lo <= age <= hi:
                multiplier *= 1.3  # boost when in peak age range
            elif age < lo - 10 or age > hi + 10:
                multiplier *= 0.5  # reduce when far outside range

        # Clamp to reasonable bounds (0.1x to 10x)
        return max(0.1, min(10.0, multiplier))

    # ── Internal Methods ──────────────────────────────────────

    def _synonym_match(self, text: str, pattern: str) -> bool:
        """Check if text and pattern are synonyms via the lookup table."""
        # Get canonical form of both
        canonical_text = _REVERSE_SYNONYMS.get(text)
        canonical_pattern = _REVERSE_SYNONYMS.get(pattern)

        if canonical_text and canonical_pattern:
            return canonical_text == canonical_pattern

        # Check if either text appears in the other's synonym list
        if canonical_text and canonical_text in CLINICAL_SYNONYMS:
            for syn in CLINICAL_SYNONYMS[canonical_text]:
                if syn in pattern or pattern in syn:
                    return True

        if canonical_pattern and canonical_pattern in CLINICAL_SYNONYMS:
            for syn in CLINICAL_SYNONYMS[canonical_pattern]:
                if syn in text or text in syn:
                    return True

        # Partial synonym matching: check if pattern or text is a substring
        # of any synonym in the same group
        for canonical, synonyms in CLINICAL_SYNONYMS.items():
            all_forms = [canonical] + synonyms
            text_in_group = any(text in form or form in text for form in all_forms)
            pattern_in_group = any(pattern in form or form in pattern for form in all_forms)
            if text_in_group and pattern_in_group:
                return True

        return False

    def _llm_synonyms(self, term: str) -> list:
        """Resolve synonyms via LLM cascade: Gemini -> Ollama/Qwen."""
        # Try Gemini
        if self._api_key:
            result = self._gemini_synonyms(term)
            if result:
                return result

        # Try Ollama (Qwen 2.5)
        result = self._ollama_synonyms(term)
        if result:
            return result

        return []

    def _gemini_synonyms(self, term: str) -> list:
        """Resolve clinical synonyms via Gemini."""
        try:
            import google.generativeai as genai

            genai.configure(api_key=self._api_key)
            model = genai.GenerativeModel("gemini-2.0-flash")

            prompt = (
                f"List clinical synonyms, abbreviations, and alternate names "
                f"for the medical term: \"{term}\". "
                f"Return ONLY a JSON array of strings, no explanation. "
                f"Include common abbreviations, ICD names, and patient-facing terms. "
                f"Maximum 10 synonyms."
            )

            response = model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )

            result = json.loads(response.text)
            if isinstance(result, list):
                return [s.lower().strip() for s in result if isinstance(s, str)]

        except Exception as e:
            logger.debug("Gemini synonym resolution failed: %s", e)

        return []

    def _ollama_synonyms(self, term: str) -> list:
        """Resolve clinical synonyms via Ollama (Qwen 2.5 32B)."""
        try:
            import urllib.request

            payload = json.dumps({
                "model": "qwen2.5:32b",
                "prompt": (
                    f"List clinical synonyms for: \"{term}\". "
                    f"Return ONLY a JSON array of strings. Max 10."
                ),
                "stream": False,
                "format": "json",
            }).encode()

            req = urllib.request.Request(
                "http://127.0.0.1:11434/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
            )

            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
                result = json.loads(data.get("response", "[]"))
                if isinstance(result, list):
                    return [s.lower().strip() for s in result if isinstance(s, str)]

        except Exception as e:
            logger.debug("Ollama synonym resolution failed: %s", e)

        return []

    def corpus_match(self, pattern: str, corpus: list) -> dict:
        """Check if a pattern matches anything in the corpus using synonym awareness.

        Returns the matched corpus item dict, or None if no match.
        This is the main method called by SnowballEngine._score_condition().
        """
        pattern_lower = pattern.lower().strip()

        # 1. Direct substring match (fast path)
        for item in corpus:
            if pattern_lower in item["text"]:
                return item

        # 2. Synonym-aware match
        # Get all forms of the pattern
        pattern_synonyms = self.resolve_synonyms(pattern_lower)
        all_forms = [pattern_lower] + pattern_synonyms

        for item in corpus:
            text = item["text"]
            for form in all_forms:
                if form in text:
                    return item

        # 3. Check if corpus items are synonyms of the pattern
        for item in corpus:
            if self._synonym_match(item["text"], pattern_lower):
                return item

        return None
