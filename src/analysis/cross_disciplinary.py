"""
Clinical Intelligence Hub — Cross-Disciplinary Analysis Engine

The brain of the tool. For EVERY condition, symptom, medication, and
genetic variant in the profile, systematically searches across ALL
29 medical specialties + 7 adjacent domains.

Why this matters:
  Doctors are siloed by specialty. A cardiologist won't check your
  vitamin D. An endocrinologist won't review cardiac imaging. A
  gastroenterologist won't consider microbiome disruption from 3 years
  of antibiotics. This tool reads EVERYTHING and connects across
  ALL specialties.

Real-world example:
  Patient reports anxiety → psychiatrist treats as mental health →
  but cross-referencing finds: vitamin D=18 ng/mL (deficient),
  endocrinology links vitamin D deficiency to anxiety, 12 published
  studies support the connection → flags for doctor.
"""

import logging
from typing import Optional

logger = logging.getLogger("CIH-CrossDisciplinary")

# ── 29 Medical Specialties ──────────────────────────────────

MEDICAL_SPECIALTIES = [
    "Allergy/Immunology",
    "Cardiology",
    "Dermatology",
    "Endocrinology",
    "Gastroenterology",
    "Genetics/Genomics",
    "Geriatrics",
    "Hematology",
    "Infectious Disease",
    "Integrative Medicine",
    "Nephrology",
    "Neurology",
    "Nutrition/Metabolic Medicine",
    "Obstetrics/Gynecology",
    "Oncology",
    "Ophthalmology",
    "Orthopedics",
    "Otolaryngology",
    "Pain Medicine",
    "Pathology",
    "Pharmacology/Pharmacogenomics",
    "Psychiatry",
    "Pulmonology",
    "Radiology",
    "Rheumatology",
    "Sleep Medicine",
    "Surgery",
    "Urology",
    "Vascular Medicine",
]

# ── 7 Adjacent Domains ─────────────────────────────────────
# Where traditional medicine has blind spots

ADJACENT_DOMAINS = {
    "Nutrition Science / Dietetics": {
        "focus": [
            "dietary interactions with medications",
            "nutritional deficiencies causing symptoms",
            "food sensitivities",
            "anti-inflammatory diets for chronic conditions",
        ],
        "examples": [
            "grapefruit + statins",
            "vitamin K + warfarin",
            "B12 deficiency → neuropathy",
            "vitamin D deficiency → anxiety/fatigue",
            "magnesium → muscle cramps",
        ],
    },
    "Environmental / Occupational Health": {
        "focus": [
            "toxic exposures (lead, mold, pesticides)",
            "geographic risk factors",
            "occupational hazards",
            "water quality and air pollution correlations",
        ],
        "examples": [
            "lead exposure → cognitive decline",
            "mold → respiratory symptoms",
            "air pollution → cardiac/respiratory conditions",
        ],
    },
    "Microbiome Science": {
        "focus": [
            "gut-brain axis connections",
            "antibiotic impact on gut flora",
            "probiotics for medication side effects",
            "microbiome disruption from long-term medication",
        ],
        "examples": [
            "IBS ↔ anxiety via gut-brain axis",
            "3 years of antibiotics → dysbiosis",
            "PPI long-term use → nutrient malabsorption",
        ],
    },
    "Exercise Physiology": {
        "focus": [
            "physical activity impacts on conditions",
            "exercise as treatment (depression, diabetes)",
            "contraindicated exercises for specific conditions",
            "deconditioning patterns",
        ],
        "examples": [
            "exercise for depression (comparable to SSRIs in mild cases)",
            "exercise contraindications with certain cardiac conditions",
        ],
    },
    "Epigenetics": {
        "focus": [
            "lifestyle and environment affecting gene expression",
            "methylation patterns relevant to genetic results",
            "transgenerational risk factors",
        ],
        "examples": [
            "chronic stress → epigenetic changes → disease risk",
            "diet affecting cancer gene expression",
        ],
    },
    "Toxicology": {
        "focus": [
            "medication accumulation effects",
            "polypharmacy burden",
            "heavy metal exposure",
            "drug metabolite interactions",
        ],
        "examples": [
            "acetaminophen accumulation with multiple products",
            "polypharmacy: 5+ medications → exponential interaction risk",
        ],
    },
    "Psychoneuroimmunology": {
        "focus": [
            "mind-body connections",
            "chronic stress → immune suppression",
            "cortisol patterns",
            "trauma-health correlations",
            "vagus nerve function",
        ],
        "examples": [
            "chronic stress → increased autoimmune risk",
            "depression → inflammatory markers → cardiac risk",
        ],
    },
}


class CrossDisciplinaryEngine:
    """
    Builds cross-disciplinary analysis queries for Deep Research.

    Given a patient's complete profile, generates targeted queries that
    search across all 29 specialties + 7 adjacent domains for connections
    that individual specialists would miss.
    """

    def build_queries(self, profile_data: dict) -> list[dict]:
        """
        Build cross-disciplinary queries from a patient profile.

        Args:
            profile_data: Dict containing medications, labs, diagnoses,
                         genetics, etc. (PII-redacted)

        Returns:
            List of query dicts with:
              - query: the search prompt
              - specialties: which specialties to cross-reference
              - context: what patient data triggered this query
              - priority: "high", "medium", "low"
        """
        queries = []

        # Medication-based queries
        meds = profile_data.get("medications", [])
        queries.extend(self._medication_queries(meds))

        # Lab-based queries (abnormal values)
        labs = profile_data.get("labs", [])
        queries.extend(self._lab_queries(labs))

        # Diagnosis-based queries
        diagnoses = profile_data.get("diagnoses", [])
        queries.extend(self._diagnosis_queries(diagnoses))

        # Genetics-based queries
        genetics = profile_data.get("genetics", [])
        queries.extend(self._genetics_queries(genetics))

        # Cross-reference: medications × labs
        queries.extend(self._medication_lab_interactions(meds, labs))

        # Cross-reference: medications × diagnoses
        queries.extend(self._medication_diagnosis_gaps(meds, diagnoses))

        # Polypharmacy assessment
        if len(meds) >= 5:
            queries.extend(self._polypharmacy_queries(meds))

        # Adjacent domain queries
        queries.extend(self._adjacent_domain_queries(profile_data))

        logger.info(
            f"Generated {len(queries)} cross-disciplinary queries "
            f"from patient profile"
        )
        return queries

    def get_deep_research_prompt(self, queries: list[dict],
                                 profile_summary: str) -> str:
        """
        Build the comprehensive Deep Research prompt from queries.

        This is the prompt sent to gemini-deep-research-pro-preview-12-2025
        for Pass 3 (pattern detection) and Pass 4 (literature search).
        """
        query_sections = []
        for i, q in enumerate(queries, 1):
            specialties = ", ".join(q.get("specialties", []))
            query_sections.append(
                f"{i}. [{q['priority'].upper()}] {q['query']}\n"
                f"   Specialties: {specialties}\n"
                f"   Context: {q['context']}"
            )

        queries_text = "\n\n".join(query_sections)

        return f"""You are a cross-disciplinary medical analyst reviewing a patient's
complete medical profile. Your task is to find connections, patterns,
and insights that individual medical specialists might miss because
they only see their narrow domain.

PATIENT PROFILE SUMMARY (PII-redacted):
{profile_summary}

CROSS-DISCIPLINARY QUERIES TO INVESTIGATE:
{queries_text}

For each query:
1. Search across ALL relevant medical specialties
2. Check adjacent domains (nutrition, environmental health, microbiome,
   exercise physiology, epigenetics, toxicology, psychoneuroimmunology)
3. Find published literature supporting any connections
4. Assess clinical significance

For each finding, provide:
- **connection**: What two or more domains are linked
- **evidence**: What patient data supports this
- **literature**: Published studies (with DOIs when possible)
- **significance**: How clinically important is this
- **question_for_doctor**: A specific question the patient should ask

Output as JSON array of findings, each with:
  connection, specialties (array), evidence, literature (array),
  significance (critical/high/moderate/low), question_for_doctor

IMPORTANT: Only report connections with genuine clinical evidence.
Do NOT speculate without literature support."""

    # ── Query Builders ──────────────────────────────────────

    def _medication_queries(self, medications: list) -> list[dict]:
        """Generate queries from active medications."""
        queries = []
        med_names = []

        for med in medications:
            name = med.get("name", "") if isinstance(med, dict) else getattr(med, "name", "")
            status = med.get("status", "") if isinstance(med, dict) else getattr(med, "status", "")

            if not name:
                continue

            status_str = str(status).lower()
            if status_str in ("active", "prn", "unknown"):
                med_names.append(name)

                # Nutritional impacts
                queries.append({
                    "query": (
                        f"What nutritional deficiencies can {name} cause? "
                        f"What dietary interactions exist? What supplements "
                        f"should be monitored?"
                    ),
                    "specialties": [
                        "Pharmacology/Pharmacogenomics",
                        "Nutrition/Metabolic Medicine",
                        "Gastroenterology",
                    ],
                    "context": f"Patient is on {name}",
                    "priority": "medium",
                })

                # Long-term effects
                queries.append({
                    "query": (
                        f"What are the long-term effects of {name}? "
                        f"What monitoring should be done for patients "
                        f"on chronic {name} therapy?"
                    ),
                    "specialties": [
                        "Pharmacology/Pharmacogenomics",
                        "Nephrology",
                        "Hematology",
                    ],
                    "context": f"Patient is on chronic {name}",
                    "priority": "medium",
                })

        # Drug-drug interactions for all active meds
        if len(med_names) >= 2:
            queries.append({
                "query": (
                    f"Analyze drug-drug interactions between: "
                    f"{', '.join(med_names)}. Include pharmacokinetic and "
                    f"pharmacodynamic interactions, QT prolongation risk, "
                    f"and serotonin syndrome risk."
                ),
                "specialties": [
                    "Pharmacology/Pharmacogenomics",
                    "Cardiology",
                    "Psychiatry",
                ],
                "context": f"Patient is on {len(med_names)} active medications",
                "priority": "high",
            })

        return queries

    def _lab_queries(self, labs: list) -> list[dict]:
        """Generate queries from abnormal lab values."""
        queries = []

        for lab in labs:
            name = lab.get("name", "") if isinstance(lab, dict) else getattr(lab, "name", "")
            flag = lab.get("flag", "") if isinstance(lab, dict) else getattr(lab, "flag", "")
            value = lab.get("value", None) if isinstance(lab, dict) else getattr(lab, "value", None)
            unit = lab.get("unit", "") if isinstance(lab, dict) else getattr(lab, "unit", "")

            if not name or not flag:
                continue

            flag_str = str(flag).lower()
            if flag_str in ("high", "low", "critical"):
                value_str = f"{value} {unit}" if value else flag_str

                queries.append({
                    "query": (
                        f"Patient has {flag_str} {name} ({value_str}). "
                        f"What conditions across ALL medical specialties "
                        f"can cause this? What downstream effects should "
                        f"be monitored?"
                    ),
                    "specialties": self._specialties_for_lab(name),
                    "context": f"{name} is {flag_str} ({value_str})",
                    "priority": "high" if flag_str == "critical" else "medium",
                })

        return queries

    def _diagnosis_queries(self, diagnoses: list) -> list[dict]:
        """Generate queries from active diagnoses."""
        queries = []

        for dx in diagnoses:
            name = dx.get("name", "") if isinstance(dx, dict) else getattr(dx, "name", "")
            status = dx.get("status", "") if isinstance(dx, dict) else getattr(dx, "status", "")

            if not name:
                continue

            status_str = str(status).lower()
            if status_str in ("active", "chronic", ""):
                queries.append({
                    "query": (
                        f"For a patient with {name}, what cross-specialty "
                        f"connections should be evaluated? What screening "
                        f"tests from OTHER specialties are recommended? "
                        f"What adjacent domain factors (nutrition, environment, "
                        f"microbiome, exercise) affect {name}?"
                    ),
                    "specialties": MEDICAL_SPECIALTIES[:10],  # Top 10 for breadth
                    "context": f"Active diagnosis: {name}",
                    "priority": "medium",
                })

        return queries

    def _genetics_queries(self, genetics: list) -> list[dict]:
        """Generate queries from genetic variants."""
        queries = []

        for variant in genetics:
            gene = variant.get("gene", "") if isinstance(variant, dict) else getattr(variant, "gene", "")
            var = variant.get("variant", "") if isinstance(variant, dict) else getattr(variant, "variant", "")
            significance = variant.get("clinical_significance", "") if isinstance(variant, dict) else getattr(variant, "clinical_significance", "")

            if not gene:
                continue

            queries.append({
                "query": (
                    f"Patient has {gene} {var or ''} variant "
                    f"(significance: {significance or 'unknown'}). "
                    f"What are the pharmacogenomic implications? "
                    f"Which medications should be adjusted? "
                    f"What screening is recommended across specialties?"
                ),
                "specialties": [
                    "Genetics/Genomics",
                    "Pharmacology/Pharmacogenomics",
                    "Oncology",
                ],
                "context": f"Genetic variant: {gene} {var or ''}",
                "priority": "high" if significance and "pathogenic" in str(significance).lower() else "medium",
            })

        return queries

    def _medication_lab_interactions(self, medications: list,
                                     labs: list) -> list[dict]:
        """Cross-reference medications with lab values."""
        queries = []

        abnormal_labs = []
        for lab in labs:
            flag = lab.get("flag", "") if isinstance(lab, dict) else getattr(lab, "flag", "")
            if str(flag).lower() in ("high", "low", "critical"):
                name = lab.get("name", "") if isinstance(lab, dict) else getattr(lab, "name", "")
                abnormal_labs.append(name)

        active_meds = []
        for med in medications:
            status = med.get("status", "") if isinstance(med, dict) else getattr(med, "status", "")
            if str(status).lower() in ("active", "prn", "unknown"):
                name = med.get("name", "") if isinstance(med, dict) else getattr(med, "name", "")
                active_meds.append(name)

        if abnormal_labs and active_meds:
            queries.append({
                "query": (
                    f"Patient has abnormal labs ({', '.join(abnormal_labs[:5])}) "
                    f"while on medications ({', '.join(active_meds[:5])}). "
                    f"Could any of these medications be CAUSING the lab "
                    f"abnormalities? Check for known drug-induced lab changes."
                ),
                "specialties": [
                    "Pharmacology/Pharmacogenomics",
                    "Hematology",
                    "Nephrology",
                    "Endocrinology",
                ],
                "context": "Cross-referencing meds with abnormal labs",
                "priority": "high",
            })

        return queries

    def _medication_diagnosis_gaps(self, medications: list,
                                    diagnoses: list) -> list[dict]:
        """Look for missing medications (screening gaps)."""
        queries = []

        dx_names = []
        for dx in diagnoses:
            name = dx.get("name", "") if isinstance(dx, dict) else getattr(dx, "name", "")
            status = dx.get("status", "") if isinstance(dx, dict) else getattr(dx, "status", "")
            if str(status).lower() in ("active", "chronic", ""):
                dx_names.append(name)

        med_names = []
        for med in medications:
            name = med.get("name", "") if isinstance(med, dict) else getattr(med, "name", "")
            med_names.append(name)

        if dx_names:
            queries.append({
                "query": (
                    f"Patient has: {', '.join(dx_names[:5])}. "
                    f"Current medications: {', '.join(med_names[:5]) or 'none listed'}. "
                    f"Per current clinical guidelines, are any recommended "
                    f"medications MISSING? Check AHA, ADA, USPSTF guidelines."
                ),
                "specialties": [
                    "Cardiology", "Endocrinology",
                    "Pharmacology/Pharmacogenomics",
                ],
                "context": "Checking for guideline-based medication gaps",
                "priority": "medium",
            })

        return queries

    def _polypharmacy_queries(self, medications: list) -> list[dict]:
        """Assess polypharmacy risk for patients on 5+ medications."""
        med_names = []
        for med in medications:
            name = med.get("name", "") if isinstance(med, dict) else getattr(med, "name", "")
            if name:
                med_names.append(name)

        return [{
            "query": (
                f"Patient is on {len(med_names)} medications: "
                f"{', '.join(med_names[:10])}. Assess polypharmacy risk: "
                f"cumulative anticholinergic burden, QT prolongation risk, "
                f"fall risk from combined sedation, renal clearance "
                f"interactions, and deprescribing opportunities."
            ),
            "specialties": [
                "Pharmacology/Pharmacogenomics",
                "Geriatrics",
                "Toxicology",
            ],
            "context": f"Polypharmacy: {len(med_names)} active medications",
            "priority": "high",
        }]

    def _adjacent_domain_queries(self, profile_data: dict) -> list[dict]:
        """Generate queries for the 7 adjacent domains."""
        queries = []

        # Nutrition: check for medication-nutrient interactions
        meds = profile_data.get("medications", [])
        if meds:
            med_names = [
                (m.get("name", "") if isinstance(m, dict) else getattr(m, "name", ""))
                for m in meds[:5]
            ]
            queries.append({
                "query": (
                    f"Nutrition/dietetics assessment: Patient medications "
                    f"({', '.join(med_names)}). What nutritional deficiencies "
                    f"do these medications cause? What dietary modifications "
                    f"are recommended? What supplements should be monitored?"
                ),
                "specialties": ["Nutrition/Metabolic Medicine"],
                "context": "Adjacent domain: Nutrition Science",
                "priority": "medium",
            })

        # Microbiome: check if long-term antibiotics or PPIs
        for med in meds:
            name = (med.get("name", "") if isinstance(med, dict)
                    else getattr(med, "name", "")).lower()
            if any(kw in name for kw in ["antibiotic", "amoxicillin", "azithromycin",
                                          "ciprofloxacin", "doxycycline", "omeprazole",
                                          "pantoprazole", "lansoprazole", "esomeprazole"]):
                queries.append({
                    "query": (
                        f"Microbiome impact: Patient is on {name}. "
                        f"What gut microbiome disruption is expected? "
                        f"What downstream effects (gut-brain axis, nutrient "
                        f"absorption, immune function)? Probiotic recommendations?"
                    ),
                    "specialties": [
                        "Gastroenterology",
                        "Nutrition/Metabolic Medicine",
                        "Psychiatry",
                    ],
                    "context": "Adjacent domain: Microbiome Science",
                    "priority": "medium",
                })
                break  # One query is enough

        return queries

    # ── Helpers ──────────────────────────────────────────────

    @staticmethod
    def _specialties_for_lab(lab_name: str) -> list[str]:
        """Map lab test names to relevant specialties."""
        lab_lower = lab_name.lower()

        specialty_map = {
            "a1c": ["Endocrinology", "Nutrition/Metabolic Medicine"],
            "glucose": ["Endocrinology", "Nutrition/Metabolic Medicine"],
            "tsh": ["Endocrinology"],
            "t3": ["Endocrinology"],
            "t4": ["Endocrinology"],
            "cholesterol": ["Cardiology", "Endocrinology"],
            "ldl": ["Cardiology"],
            "hdl": ["Cardiology"],
            "triglyceride": ["Cardiology", "Endocrinology"],
            "creatinine": ["Nephrology"],
            "egfr": ["Nephrology"],
            "bun": ["Nephrology"],
            "alt": ["Gastroenterology", "Hematology"],
            "ast": ["Gastroenterology", "Hematology"],
            "hemoglobin": ["Hematology"],
            "hematocrit": ["Hematology"],
            "platelet": ["Hematology"],
            "wbc": ["Hematology", "Infectious Disease"],
            "vitamin d": ["Endocrinology", "Rheumatology", "Psychiatry"],
            "b12": ["Hematology", "Neurology"],
            "ferritin": ["Hematology", "Gastroenterology"],
            "iron": ["Hematology", "Gastroenterology"],
            "psa": ["Urology", "Oncology"],
            "cortisol": ["Endocrinology", "Psychiatry"],
            "sodium": ["Nephrology", "Endocrinology"],
            "potassium": ["Nephrology", "Cardiology"],
            "calcium": ["Endocrinology", "Nephrology"],
            "magnesium": ["Cardiology", "Neurology"],
        }

        for key, specialties in specialty_map.items():
            if key in lab_lower:
                return specialties

        return ["Pathology"]
