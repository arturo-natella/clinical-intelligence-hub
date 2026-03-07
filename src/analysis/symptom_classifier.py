"""
Clinical Intelligence Hub — Symptom Body System Classifier

Auto-classifies patient-reported symptoms into body systems based on
keyword matching against symptom names and descriptions.

Body Systems:
  - gi:              GI / Digestive
  - musculoskeletal: Musculoskeletal
  - neurological:    Neurological
  - mood_energy:     Mood & Energy
  - cardiovascular:  Cardiovascular
  - sleep:           Sleep
  - skin:            Skin
  - other:           Other (unclassified)
"""

import logging
from typing import Optional

logger = logging.getLogger("CIH-SymptomClassifier")


# ── Keyword Dictionaries ───────────────────────────────────────

BODY_SYSTEM_KEYWORDS = {
    "gi": [
        "nausea", "vomiting", "diarrhea", "constipation", "stomach",
        "abdominal", "bloating", "heartburn", "acid reflux", "gerd",
        "appetite", "cramp", "gas", "bowel", "indigestion", "reflux",
        "gastric", "intestinal", "colitis", "ibs",
    ],
    "musculoskeletal": [
        "muscle", "joint", "joint pain", "stiffness", "weakness",
        "cramp", "back pain", "knee", "hip", "shoulder", "arthritis",
        "myalgia", "spasm", "tendon", "fibromyalgia", "bone",
        "muscle pain", "muscle ache",
    ],
    "neurological": [
        "headache", "migraine", "dizziness", "vertigo", "numbness",
        "tingling", "tremor", "seizure", "neuropathy", "brain fog",
        "confusion", "balance", "nerve", "neuralgia",
    ],
    "mood_energy": [
        "fatigue", "tired", "exhausted", "anxiety", "depression", "mood",
        "irritable", "energy", "motivation", "brain fog", "lethargy",
        "apathy", "restless", "panic", "stress",
    ],
    "cardiovascular": [
        "palpitation", "chest pain", "chest", "shortness of breath", "swelling",
        "edema", "blood pressure", "heart", "tachycardia", "bradycardia",
        "angina", "arrhythmia",
    ],
    "sleep": [
        "insomnia", "sleep", "drowsy", "drowsiness", "wake", "restless",
        "apnea", "nightmare", "vivid dream", "sleepless", "snoring",
    ],
    "skin": [
        "rash", "itching", "hives", "dry skin", "bruise", "skin",
        "hair loss", "sweating", "acne", "sensitivity", "eczema",
        "dermatitis", "psoriasis",
    ],
}

BODY_SYSTEM_LABELS = {
    "gi": "GI / Digestive",
    "musculoskeletal": "Musculoskeletal",
    "neurological": "Neurological",
    "mood_energy": "Mood & Energy",
    "cardiovascular": "Cardiovascular",
    "sleep": "Sleep",
    "skin": "Skin",
    "other": "Other",
}


class SymptomClassifier:
    """Classifies symptoms into body systems using keyword matching."""

    def classify(self, symptom_name: str, description: str = "") -> str:
        """
        Returns the best-matching body system key for a symptom.

        Checks symptom_name first (higher priority), then description.
        Returns 'other' if no keyword matches.

        Args:
            symptom_name: The name of the symptom (e.g. "Nausea")
            description: Optional description text for additional context

        Returns:
            Body system key (e.g. "gi", "neurological", "other")
        """
        if not symptom_name:
            logger.warning("classify() called with empty symptom_name, returning 'other'")
            return "other"

        # Score each body system by number of keyword matches
        # Longer keyword matches score higher (more specific = more confident)
        scores = {}
        name_lower = symptom_name.lower()
        desc_lower = (description or "").lower()

        for system, keywords in BODY_SYSTEM_KEYWORDS.items():
            score = 0.0
            for keyword in keywords:
                kw_len_bonus = len(keyword.split())  # multi-word keywords score higher
                # Name matches count double, with bonus for specificity
                if keyword in name_lower:
                    score += 2 * kw_len_bonus
                # Description matches count once
                if desc_lower and keyword in desc_lower:
                    score += 1 * kw_len_bonus
            if score > 0:
                scores[system] = score

        if not scores:
            return "other"

        # Return the system with the highest score
        best_system = max(scores, key=scores.get)
        return best_system

    def classify_all(self, symptoms: list) -> dict:
        """
        Auto-classifies all symptoms into body system groups.

        Args:
            symptoms: List of symptom dicts with at least 'symptom_name'
                      and optionally episode descriptions

        Returns:
            Dict keyed by body_system with lists of symptom dicts.
            Each symptom dict gets a 'body_system' field added.
        """
        result = {}

        for s in symptoms:
            name = s.get("symptom_name", "")
            # Gather description text from episodes for richer matching
            descriptions = []
            for ep in s.get("episodes", []):
                desc = (ep.get("description") or "").strip()
                if desc:
                    descriptions.append(desc)
            combined_desc = " ".join(descriptions[:5])  # Limit to avoid noise

            system = self.classify(name, combined_desc)

            # Add body_system to the symptom dict (non-destructive copy)
            enriched = dict(s)
            enriched["body_system"] = system

            if system not in result:
                result[system] = []
            result[system].append(enriched)

        return result

    @staticmethod
    def get_label(system_key: str) -> str:
        """Get the human-readable label for a body system key."""
        return BODY_SYSTEM_LABELS.get(system_key, "Other")

    @staticmethod
    def get_all_systems() -> dict:
        """Return all body system keys with their labels."""
        return dict(BODY_SYSTEM_LABELS)
