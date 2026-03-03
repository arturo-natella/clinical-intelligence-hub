"""
Clinical Intelligence Hub — Environmental/Geographic Risk Analysis

Knowledge base of 25+ geographic and environmental health risks.
Maps patient location to relevant regional conditions, then cross-
references against their clinical data (diagnoses, symptoms, labs).

Location matching: state-level + region grouping (e.g., "Southwest"
matches AZ, NM, NV, UT, CO).
"""

import logging
from typing import Optional

logger = logging.getLogger("CIH-Environmental")


# ── Region → State Mapping ────────────────────────────────

REGIONS = {
    "northeast": [
        "connecticut", "maine", "massachusetts", "new hampshire",
        "rhode island", "vermont", "new jersey", "new york",
        "pennsylvania",
    ],
    "southeast": [
        "alabama", "arkansas", "florida", "georgia", "kentucky",
        "louisiana", "mississippi", "north carolina", "south carolina",
        "tennessee", "virginia", "west virginia",
    ],
    "midwest": [
        "illinois", "indiana", "iowa", "kansas", "michigan",
        "minnesota", "missouri", "nebraska", "north dakota",
        "ohio", "south dakota", "wisconsin",
    ],
    "southwest": [
        "arizona", "new mexico", "nevada", "utah", "colorado",
        "texas", "oklahoma",
    ],
    "west": [
        "california", "oregon", "washington", "idaho", "montana",
        "wyoming", "alaska", "hawaii",
    ],
}

# Reverse lookup: state → region
STATE_TO_REGION = {}
for region, states in REGIONS.items():
    for state in states:
        STATE_TO_REGION[state] = region


# ── Geographic Risk Knowledge Base ────────────────────────

GEOGRAPHIC_RISKS = [
    # ── Infectious / Fungal ──────────────────────────────
    {
        "name": "Valley Fever (Coccidioidomycosis)",
        "regions": ["southwest"],
        "states": ["arizona", "california", "new mexico", "nevada", "texas", "utah"],
        "category": "Fungal Infection",
        "severity": "moderate",
        "description": (
            "Coccidioides fungus lives in desert soil. Dust exposure "
            "during construction, farming, or windstorms increases risk."
        ),
        "symptoms_to_watch": [
            "cough", "fever", "fatigue", "chest pain",
            "joint pain", "rash", "night sweats",
        ],
        "relevant_conditions": ["immunocompromised", "hiv", "transplant"],
        "relevant_labs": ["eosinophils"],
        "action": (
            "If you experience persistent cough or fever after dust exposure, "
            "mention Valley Fever testing to your doctor."
        ),
    },
    {
        "name": "Histoplasmosis",
        "regions": ["midwest", "southeast"],
        "states": [
            "ohio", "indiana", "illinois", "missouri", "kentucky",
            "tennessee", "arkansas", "mississippi",
        ],
        "category": "Fungal Infection",
        "severity": "moderate",
        "description": (
            "Histoplasma capsulatum thrives in soil enriched by bird "
            "and bat droppings. Ohio and Mississippi River valleys are "
            "primary endemic zones."
        ),
        "symptoms_to_watch": ["cough", "fever", "fatigue", "chest pain"],
        "relevant_conditions": ["immunocompromised", "hiv", "copd"],
        "relevant_labs": [],
        "action": (
            "Persistent respiratory symptoms in endemic areas should "
            "prompt discussion about histoplasmosis testing."
        ),
    },
    {
        "name": "Lyme Disease",
        "regions": ["northeast"],
        "states": [
            "connecticut", "maine", "massachusetts", "new hampshire",
            "rhode island", "vermont", "new jersey", "new york",
            "pennsylvania", "maryland", "delaware", "virginia",
            "minnesota", "wisconsin",
        ],
        "category": "Tick-borne Illness",
        "severity": "moderate",
        "description": (
            "Borrelia burgdorferi transmitted by black-legged ticks. "
            "Highest risk May through October in wooded/grassy areas."
        ),
        "symptoms_to_watch": [
            "rash", "joint pain", "fatigue", "headache",
            "fever", "muscle pain", "neck stiffness",
        ],
        "relevant_conditions": [],
        "relevant_labs": [],
        "action": (
            "Report any bull's-eye rash or unexplained joint pain to "
            "your doctor. Early Lyme treatment is highly effective."
        ),
    },
    {
        "name": "Rocky Mountain Spotted Fever",
        "regions": ["southeast", "southwest"],
        "states": [
            "north carolina", "oklahoma", "arkansas", "tennessee",
            "missouri", "arizona",
        ],
        "category": "Tick-borne Illness",
        "severity": "high",
        "description": (
            "Rickettsia rickettsii transmitted by dog ticks and wood "
            "ticks. Can be fatal if untreated. Most common April–September."
        ),
        "symptoms_to_watch": [
            "fever", "headache", "rash", "muscle pain", "nausea",
        ],
        "relevant_conditions": [],
        "relevant_labs": ["platelets"],
        "action": (
            "Sudden fever with headache and rash after tick exposure is "
            "a medical urgency — seek care immediately."
        ),
    },
    {
        "name": "West Nile Virus",
        "regions": ["southwest", "midwest", "southeast"],
        "states": [
            "texas", "california", "colorado", "arizona",
            "louisiana", "mississippi", "illinois",
        ],
        "category": "Mosquito-borne Illness",
        "severity": "low",
        "description": (
            "Transmitted by Culex mosquitoes, especially in summer. "
            "Most infections are mild, but neuroinvasive disease can "
            "occur in older adults and immunocompromised patients."
        ),
        "symptoms_to_watch": ["fever", "headache", "fatigue", "muscle weakness"],
        "relevant_conditions": ["immunocompromised", "diabetes"],
        "relevant_labs": [],
        "action": (
            "Use insect repellent during mosquito season. Report sudden "
            "fever with severe headache or muscle weakness."
        ),
    },

    # ── Water / Contamination ────────────────────────────
    {
        "name": "Lead Exposure Risk",
        "regions": ["midwest", "northeast"],
        "states": [
            "michigan", "ohio", "pennsylvania", "illinois",
            "new york", "new jersey", "wisconsin", "indiana",
        ],
        "category": "Environmental Toxin",
        "severity": "moderate",
        "description": (
            "Older housing (pre-1978) and aging water infrastructure "
            "increase lead exposure risk. Flint, MI crisis highlighted "
            "widespread infrastructure concerns."
        ),
        "symptoms_to_watch": [
            "fatigue", "abdominal pain", "headache",
            "memory problems", "joint pain",
        ],
        "relevant_conditions": ["hypertension", "kidney disease", "anemia"],
        "relevant_labs": ["lead level", "hemoglobin", "creatinine"],
        "action": (
            "If living in a home built before 1978 or in an area with "
            "known water issues, ask about lead level testing."
        ),
    },
    {
        "name": "PFAS Contamination",
        "regions": ["northeast", "midwest", "southeast"],
        "states": [
            "michigan", "new jersey", "north carolina",
            "new hampshire", "pennsylvania", "new york",
        ],
        "category": "Environmental Toxin",
        "severity": "low",
        "description": (
            "Per- and polyfluoroalkyl substances (forever chemicals) "
            "found near military bases and industrial sites. Linked "
            "to thyroid disease, cancer risk, and immune suppression."
        ),
        "symptoms_to_watch": [],
        "relevant_conditions": [
            "thyroid", "cancer", "cholesterol", "ulcerative colitis",
        ],
        "relevant_labs": ["thyroid", "tsh", "cholesterol"],
        "action": (
            "If you live near a known PFAS contamination site, mention "
            "this to your doctor when discussing thyroid or cholesterol issues."
        ),
    },
    {
        "name": "Arsenic in Groundwater",
        "regions": ["southwest", "west"],
        "states": [
            "arizona", "nevada", "california", "new mexico",
            "utah", "idaho", "montana",
        ],
        "category": "Environmental Toxin",
        "severity": "low",
        "description": (
            "Naturally occurring arsenic in groundwater, especially "
            "in areas using private wells. Long-term exposure linked "
            "to skin changes, cancer risk, and cardiovascular disease."
        ),
        "symptoms_to_watch": ["skin changes", "numbness", "fatigue"],
        "relevant_conditions": ["cancer", "diabetes", "cardiovascular"],
        "relevant_labs": [],
        "action": (
            "If you use well water in the Southwest, consider having "
            "it tested for arsenic."
        ),
    },

    # ── Altitude ─────────────────────────────────────────
    {
        "name": "High Altitude Effects",
        "regions": [],
        "states": ["colorado", "wyoming", "montana", "utah", "new mexico"],
        "category": "Altitude",
        "severity": "moderate",
        "description": (
            "Living above 5,000 ft affects oxygen levels, medication "
            "metabolism, and cardiovascular workload. Particularly "
            "relevant for patients with heart or lung conditions."
        ),
        "symptoms_to_watch": [
            "shortness of breath", "headache", "fatigue",
            "dizziness", "sleep disturbance",
        ],
        "relevant_conditions": [
            "heart failure", "copd", "asthma", "pulmonary hypertension",
            "anemia", "sleep apnea",
        ],
        "relevant_labs": ["hemoglobin", "hematocrit", "oxygen saturation"],
        "action": (
            "Altitude can worsen heart and lung conditions. Discuss "
            "altitude-adjusted medication dosing with your doctor."
        ),
    },

    # ── Air Quality ──────────────────────────────────────
    {
        "name": "Wildfire Smoke Exposure",
        "regions": ["west"],
        "states": [
            "california", "oregon", "washington", "colorado",
            "montana", "idaho",
        ],
        "category": "Air Quality",
        "severity": "moderate",
        "description": (
            "Seasonal wildfire smoke contains fine particulates (PM2.5) "
            "that exacerbate respiratory and cardiovascular conditions."
        ),
        "symptoms_to_watch": [
            "cough", "wheezing", "shortness of breath",
            "chest tightness", "eye irritation",
        ],
        "relevant_conditions": [
            "asthma", "copd", "heart failure", "coronary artery disease",
        ],
        "relevant_labs": [],
        "action": (
            "During fire season, monitor AQI levels and stay indoors "
            "when air quality is poor. Discuss an action plan with your doctor."
        ),
    },
    {
        "name": "Industrial Air Pollution",
        "regions": ["midwest", "southeast"],
        "states": [
            "texas", "louisiana", "indiana", "ohio",
            "pennsylvania", "illinois",
        ],
        "category": "Air Quality",
        "severity": "low",
        "description": (
            "Petrochemical plants, refineries, and heavy industry "
            "corridors contribute to chronic air pollution exposure. "
            "Linked to respiratory disease and cancer risk."
        ),
        "symptoms_to_watch": ["cough", "shortness of breath", "fatigue"],
        "relevant_conditions": ["asthma", "copd", "cancer"],
        "relevant_labs": [],
        "action": (
            "If living near industrial areas, discuss lung function "
            "screening and cancer risk assessment with your doctor."
        ),
    },

    # ── Climate / Heat ───────────────────────────────────
    {
        "name": "Extreme Heat Risk",
        "regions": ["southwest", "southeast"],
        "states": [
            "arizona", "texas", "nevada", "florida",
            "louisiana", "mississippi", "georgia",
        ],
        "category": "Climate",
        "severity": "moderate",
        "description": (
            "Extreme heat affects medication efficacy (insulin, "
            "certain psych meds), dehydration risk, and cardiovascular "
            "strain, especially for older adults."
        ),
        "symptoms_to_watch": [
            "dizziness", "nausea", "confusion", "fatigue",
            "rapid heartbeat",
        ],
        "relevant_conditions": [
            "diabetes", "heart failure", "kidney disease",
            "hypertension",
        ],
        "relevant_labs": ["creatinine", "electrolytes", "sodium", "potassium"],
        "action": (
            "Some medications work differently in extreme heat. Ask "
            "your doctor about heat-season adjustments."
        ),
    },
    {
        "name": "Seasonal Affective Disorder Risk",
        "regions": ["northeast", "midwest"],
        "states": [
            "alaska", "washington", "oregon", "minnesota",
            "wisconsin", "michigan", "maine", "vermont",
            "new hampshire", "montana", "north dakota",
        ],
        "category": "Climate",
        "severity": "low",
        "description": (
            "Reduced sunlight during winter months increases risk "
            "of seasonal depression and vitamin D deficiency."
        ),
        "symptoms_to_watch": [
            "fatigue", "depression", "sleep changes",
            "weight changes", "mood changes",
        ],
        "relevant_conditions": [
            "depression", "anxiety", "bipolar",
            "vitamin d deficiency",
        ],
        "relevant_labs": ["vitamin d", "25-hydroxyvitamin d"],
        "action": (
            "Ask your doctor about vitamin D levels and light therapy "
            "options during winter months."
        ),
    },

    # ── Allergens / Biological ───────────────────────────
    {
        "name": "Pollen Allergy Hotspot",
        "regions": ["southeast"],
        "states": [
            "georgia", "south carolina", "north carolina",
            "tennessee", "texas", "florida",
        ],
        "category": "Allergen",
        "severity": "low",
        "description": (
            "High pollen counts from trees, grasses, and ragweed. "
            "Particularly intense spring through fall."
        ),
        "symptoms_to_watch": [
            "sneezing", "congestion", "eye irritation",
            "cough", "asthma exacerbation",
        ],
        "relevant_conditions": ["asthma", "allergies", "eczema", "sinusitis"],
        "relevant_labs": ["ige"],
        "action": (
            "If seasonal symptoms worsen, discuss allergy testing and "
            "management strategies with your doctor."
        ),
    },
    {
        "name": "Mold Exposure Risk",
        "regions": ["southeast"],
        "states": [
            "florida", "louisiana", "texas", "georgia",
            "south carolina", "alabama", "mississippi",
        ],
        "category": "Allergen",
        "severity": "low",
        "description": (
            "High humidity and flooding create ideal mold conditions. "
            "Indoor mold can trigger respiratory symptoms and worsen "
            "asthma."
        ),
        "symptoms_to_watch": [
            "cough", "wheezing", "congestion",
            "skin irritation", "eye irritation",
        ],
        "relevant_conditions": ["asthma", "copd", "allergies", "immunocompromised"],
        "relevant_labs": [],
        "action": (
            "If you experience chronic respiratory symptoms in humid "
            "environments, mention possible mold exposure to your doctor."
        ),
    },

    # ── Radon ────────────────────────────────────────────
    {
        "name": "Radon Exposure Risk",
        "regions": ["midwest", "northeast"],
        "states": [
            "iowa", "pennsylvania", "ohio", "indiana",
            "illinois", "nebraska", "colorado", "north dakota",
            "minnesota", "wisconsin",
        ],
        "category": "Environmental Toxin",
        "severity": "moderate",
        "description": (
            "Radon is the #2 cause of lung cancer. Natural radioactive "
            "gas seeps into basements from granite and shale bedrock."
        ),
        "symptoms_to_watch": ["cough", "chest pain", "shortness of breath"],
        "relevant_conditions": ["cancer", "lung cancer", "copd"],
        "relevant_labs": [],
        "action": (
            "Test your home for radon levels. Mention your location "
            "to your doctor if you have respiratory concerns."
        ),
    },

    # ── Parasitic ────────────────────────────────────────
    {
        "name": "Chagas Disease Risk",
        "regions": ["southwest"],
        "states": ["texas", "arizona", "new mexico", "louisiana"],
        "category": "Parasitic Infection",
        "severity": "low",
        "description": (
            "Trypanosoma cruzi transmitted by kissing bugs. Chronic "
            "infection can cause heart disease years later."
        ),
        "symptoms_to_watch": ["fatigue", "palpitations", "shortness of breath"],
        "relevant_conditions": ["cardiomyopathy", "heart failure"],
        "relevant_labs": [],
        "action": (
            "If you have unexplained cardiomyopathy and live in the "
            "Southwest, ask about Chagas screening."
        ),
    },

    # ── Hard Water / Mineral ─────────────────────────────
    {
        "name": "Hard Water / Mineral Content",
        "regions": ["midwest", "southwest"],
        "states": [
            "texas", "new mexico", "arizona", "kansas",
            "indiana", "wisconsin", "florida",
        ],
        "category": "Water Quality",
        "severity": "low",
        "description": (
            "Very hard water (>180 mg/L calcium carbonate) may "
            "contribute to kidney stone formation in susceptible "
            "individuals."
        ),
        "symptoms_to_watch": ["flank pain", "urinary symptoms"],
        "relevant_conditions": ["kidney stones", "nephrolithiasis", "gout"],
        "relevant_labs": ["calcium", "uric acid", "creatinine"],
        "action": (
            "If prone to kidney stones, discuss whether your local "
            "water mineral content may be a factor."
        ),
    },

    # ── Radiation / Nuclear ──────────────────────────────
    {
        "name": "Uranium Mining Legacy",
        "regions": ["southwest"],
        "states": ["new mexico", "arizona", "utah", "colorado"],
        "category": "Environmental Toxin",
        "severity": "low",
        "description": (
            "Legacy uranium mining and mill tailings near Navajo Nation "
            "and surrounding areas. Linked to kidney disease and cancer."
        ),
        "symptoms_to_watch": ["fatigue", "weight loss"],
        "relevant_conditions": ["kidney disease", "cancer"],
        "relevant_labs": ["creatinine", "bun", "egfr"],
        "action": (
            "If you live near former uranium mining sites, mention "
            "this to your doctor during health screenings."
        ),
    },

    # ── Unique Regional ──────────────────────────────────
    {
        "name": "Harmful Algal Blooms",
        "regions": [],
        "states": [
            "florida", "ohio", "california", "oregon",
            "michigan", "new york",
        ],
        "category": "Water Quality",
        "severity": "low",
        "description": (
            "Cyanobacterial blooms produce toxins in lakes and "
            "coastal waters. Can cause skin irritation, GI symptoms, "
            "and liver damage."
        ),
        "symptoms_to_watch": [
            "skin irritation", "nausea", "diarrhea", "abdominal pain",
        ],
        "relevant_conditions": ["liver disease"],
        "relevant_labs": ["liver enzymes", "alt", "ast"],
        "action": (
            "Avoid swimming in water with visible algal blooms. "
            "Report GI symptoms after lake exposure to your doctor."
        ),
    },
    {
        "name": "Hurricane/Flood Recovery Health Risks",
        "regions": ["southeast"],
        "states": [
            "florida", "louisiana", "texas", "mississippi",
            "north carolina", "south carolina",
        ],
        "category": "Disaster Recovery",
        "severity": "low",
        "description": (
            "Post-flood environments increase risk of mold, contaminated "
            "water, chemical spills, and vector-borne illness."
        ),
        "symptoms_to_watch": [
            "cough", "skin irritation", "diarrhea", "fever",
        ],
        "relevant_conditions": ["asthma", "copd", "immunocompromised"],
        "relevant_labs": [],
        "action": (
            "After flooding events, watch for respiratory and GI "
            "symptoms. Mention recent flooding to your doctor."
        ),
    },
]


# ── Environmental Risk Engine ─────────────────────────────

class EnvironmentalRiskEngine:
    """Analyzes geographic health risks for a patient's location."""

    def analyze(self, profile_data: dict) -> dict:
        """
        Identify environmental risks for the patient's location,
        cross-referenced against their clinical data.

        Args:
            profile_data: Vault profile dict

        Returns:
            {
                "location": str,
                "region": str,
                "risks": [{name, category, severity, description,
                           action, relevance_score, relevance_reasons}],
                "summary": {total_risks, high, moderate, low,
                            personalized_count}
            }
        """
        location = self._get_location(profile_data)
        if not location:
            return {
                "location": None,
                "region": None,
                "risks": [],
                "summary": {
                    "total_risks": 0, "high": 0, "moderate": 0,
                    "low": 0, "personalized_count": 0,
                },
            }

        state = self._normalize_state(location)
        region = STATE_TO_REGION.get(state, "")

        # Find matching risks
        matching_risks = []
        for risk in GEOGRAPHIC_RISKS:
            if self._location_matches(state, region, risk):
                matching_risks.append(risk)

        # Score relevance against patient data
        clinical_corpus = self._build_clinical_corpus(profile_data)
        scored_risks = []
        personalized_count = 0

        for risk in matching_risks:
            score, reasons = self._score_relevance(risk, clinical_corpus)
            if score > 0:
                personalized_count += 1

            scored_risks.append({
                "name": risk["name"],
                "category": risk["category"],
                "severity": risk["severity"],
                "description": risk["description"],
                "action": risk["action"],
                "symptoms_to_watch": risk["symptoms_to_watch"],
                "relevance_score": score,
                "relevance_reasons": reasons,
            })

        # Sort: personalized first, then by severity
        severity_order = {"high": 0, "moderate": 1, "low": 2}
        scored_risks.sort(key=lambda r: (
            0 if r["relevance_score"] > 0 else 1,
            severity_order.get(r["severity"], 3),
            -r["relevance_score"],
        ))

        # Summary counts
        summary = {
            "total_risks": len(scored_risks),
            "high": sum(1 for r in scored_risks if r["severity"] == "high"),
            "moderate": sum(1 for r in scored_risks if r["severity"] == "moderate"),
            "low": sum(1 for r in scored_risks if r["severity"] == "low"),
            "personalized_count": personalized_count,
        }

        logger.info(
            "Environmental analysis for %s (%s): %d risks, %d personalized",
            location, region, len(scored_risks), personalized_count,
        )

        return {
            "location": location,
            "region": region,
            "risks": scored_risks,
            "summary": summary,
        }

    # ── Location Handling ─────────────────────────────────

    def _get_location(self, profile_data: dict) -> Optional[str]:
        """Extract location from profile demographics."""
        demographics = profile_data.get("demographics", {})
        return demographics.get("location", "")

    def _normalize_state(self, location: str) -> str:
        """Normalize location input to a lowercase state name."""
        loc = location.lower().strip()

        # State abbreviation lookup
        abbrev_map = {
            "al": "alabama", "ak": "alaska", "az": "arizona",
            "ar": "arkansas", "ca": "california", "co": "colorado",
            "ct": "connecticut", "de": "delaware", "fl": "florida",
            "ga": "georgia", "hi": "hawaii", "id": "idaho",
            "il": "illinois", "in": "indiana", "ia": "iowa",
            "ks": "kansas", "ky": "kentucky", "la": "louisiana",
            "me": "maine", "md": "maryland", "ma": "massachusetts",
            "mi": "michigan", "mn": "minnesota", "ms": "mississippi",
            "mo": "missouri", "mt": "montana", "ne": "nebraska",
            "nv": "nevada", "nh": "new hampshire", "nj": "new jersey",
            "nm": "new mexico", "ny": "new york", "nc": "north carolina",
            "nd": "north dakota", "oh": "ohio", "ok": "oklahoma",
            "or": "oregon", "pa": "pennsylvania", "ri": "rhode island",
            "sc": "south carolina", "sd": "south dakota",
            "tn": "tennessee", "tx": "texas", "ut": "utah",
            "vt": "vermont", "va": "virginia", "wa": "washington",
            "wv": "west virginia", "wi": "wisconsin", "wy": "wyoming",
            "dc": "district of columbia",
        }

        # Try abbreviation first
        if loc in abbrev_map:
            return abbrev_map[loc]

        # Try full state name
        all_states = set()
        for states in REGIONS.values():
            all_states.update(states)

        if loc in all_states:
            return loc

        # Try partial match (e.g., "Phoenix, AZ" → "arizona")
        for abbr, full_name in abbrev_map.items():
            if abbr in loc.split(",")[-1].strip().split() or abbr == loc.split(",")[-1].strip():
                return full_name

        # Try state name anywhere in the string
        for state_name in sorted(all_states, key=len, reverse=True):
            if state_name in loc:
                return state_name

        return loc  # Return as-is; may not match but preserves input

    def _location_matches(self, state: str, region: str,
                          risk: dict) -> bool:
        """Check if patient location matches a geographic risk."""
        if state in risk.get("states", []):
            return True
        if region and region in risk.get("regions", []):
            return True
        return False

    # ── Clinical Corpus ───────────────────────────────────

    def _build_clinical_corpus(self, profile_data: dict) -> dict:
        """Build a lookup of patient's clinical data for relevance scoring."""
        timeline = profile_data.get("clinical_timeline", {})
        corpus = {
            "conditions": set(),
            "symptoms": set(),
            "labs": set(),
        }

        # Diagnoses
        for dx in timeline.get("diagnoses", []):
            name = dx.get("name", "").lower()
            if name:
                corpus["conditions"].add(name)

        # Symptoms
        for sym in timeline.get("symptoms", []):
            name = sym.get("symptom_name", "").lower()
            if name:
                corpus["symptoms"].add(name)

        # Lab names
        for lab in timeline.get("labs", []):
            name = lab.get("name", "").lower()
            if name:
                corpus["labs"].add(name)

        # Medications (some relevant conditions inferred from meds)
        for med in timeline.get("medications", []):
            reason = (med.get("reason") or "").lower()
            if reason:
                corpus["conditions"].add(reason)

        return corpus

    def _score_relevance(self, risk: dict,
                         corpus: dict) -> tuple[float, list[str]]:
        """
        Score how relevant a geographic risk is to the patient.

        Returns (score 0.0-1.0, list of reasons).
        Score 0 = general risk only, >0 = personalized match.
        """
        score = 0.0
        reasons = []

        # Check condition matches
        for cond in risk.get("relevant_conditions", []):
            cond_lower = cond.lower()
            for patient_cond in corpus["conditions"]:
                if cond_lower in patient_cond or patient_cond in cond_lower:
                    score += 0.4
                    reasons.append(
                        f"Your condition '{patient_cond}' is associated "
                        f"with this risk"
                    )
                    break

        # Check symptom matches
        for symp in risk.get("symptoms_to_watch", []):
            symp_lower = symp.lower()
            for patient_symp in corpus["symptoms"]:
                if symp_lower in patient_symp or patient_symp in symp_lower:
                    score += 0.2
                    reasons.append(
                        f"You track '{patient_symp}', which is a symptom "
                        f"to watch for this risk"
                    )
                    break

        # Check lab matches
        for lab in risk.get("relevant_labs", []):
            lab_lower = lab.lower()
            for patient_lab in corpus["labs"]:
                if lab_lower in patient_lab or patient_lab in lab_lower:
                    score += 0.1
                    reasons.append(
                        f"Your lab history includes '{patient_lab}', "
                        f"which is relevant to this risk"
                    )
                    break

        return min(score, 1.0), reasons
