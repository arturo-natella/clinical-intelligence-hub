"""Structured evidence matching for the systemic-disease rule engine.

The engine used to join every record into one string and strip qualifiers
before substring matching, so a NORMAL ferritin satisfied "high ferritin" and
"denies chest pain" counted as chest pain. This module keeps labs structured
(name + direction + abnormality) and matches text per record entry with a
negation/attribution guard, so a marker only counts when the record actually
supports it.

Nothing here logs or returns raw record text — callers receive booleans and
the marker strings they passed in.
"""

from __future__ import annotations

import re

# Flag vocabularies seen across the pipeline, FHIR imports, and legacy rows.
_HIGH_FLAGS = {"h", "hh", "high", "abnormal high", "critical high", "elevated", "above"}
_LOW_FLAGS = {"l", "ll", "low", "abnormal low", "critical low", "decreased", "below"}
_NORMAL_FLAGS = {"n", "normal", "within range", "wnl", ""}

_POSITIVE_WORDS = ("positive", "reactive", "detected", "present")
_NEGATIVE_WORDS = ("negative", "non-reactive", "nonreactive", "not detected", "absent")

# Cues that flip a mention from "the patient has this" to "they don't" (or
# "someone else does"). Checked within the same clause, before the match.
NEGATION_CUES = (
    "no", "not", "never", "denies", "denied", "negative for", "without",
    "ruled out", "r/o", "rule out", "absent", "resolved", "no history of",
    "family history of", "fh of", "mother", "father", "sibling", "brother",
    "sister", "maternal", "paternal",
)

# Symptoms too common to distinguish one systemic disease from another. A
# triad needs at least one signal outside this set (or an abnormal lab) to fire.
NON_SPECIFIC_SYMPTOMS = {
    "fatigue", "tiredness", "tired", "exhaustion", "malaise", "headache",
    "dizziness", "lightheadedness", "nausea", "weakness", "brain fog",
    "insomnia", "anxiety", "depression", "weight gain", "weight loss",
    "joint pain", "muscle pain", "muscle aches", "body aches", "pain",
    "discomfort", "sleep disturbance", "poor sleep", "malaise fatigue",
}

# Lay ↔ clinical pairs. Records mix both registers; each group is mutually
# interchangeable when matching symptom terms.
_SYNONYM_GROUPS = (
    ("dyspnea", "shortness of breath", "breathlessness"),
    ("fatigue", "tiredness", "exhaustion"),
    ("pruritus", "itching", "itchy skin"),
    ("syncope", "fainting", "passing out"),
    ("myalgia", "muscle pain", "muscle aches"),
    ("arthralgia", "joint pain"),
    ("paresthesia", "numbness", "tingling"),
    ("edema", "swelling"),
    ("palpitations", "racing heart", "heart racing"),
    ("alopecia", "hair loss"),
    ("dysphagia", "trouble swallowing", "difficulty swallowing"),
    ("pyrexia", "fever"),
    ("epistaxis", "nosebleed", "nose bleeds"),
    ("xerostomia", "dry mouth"),
)

_SYNONYMS: dict[str, set[str]] = {}
for _group in _SYNONYM_GROUPS:
    for _term in _group:
        _SYNONYMS.setdefault(_term, set()).update(_group)


def _norm(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _to_float(value):
    try:
        if value is None or value == "":
            return None
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _lab_name(lab: dict) -> str:
    """Name precedence mirrors the lab-date precedence used elsewhere."""
    for key in ("name", "test_name", "test", "display_name"):
        value = _norm(lab.get(key))
        if value:
            return value
    return ""


def _reference_bounds(lab: dict) -> tuple:
    low = _to_float(lab.get("reference_low"))
    high = _to_float(lab.get("reference_high"))
    if low is not None or high is not None:
        return low, high

    text = _norm(lab.get("reference_range") or lab.get("range"))
    if not text:
        return None, None
    span = re.match(r"^(-?[\d.]+)\s*[-–to]+\s*(-?[\d.]+)$", text)
    if span:
        return _to_float(span.group(1)), _to_float(span.group(2))
    below = re.match(r"^[<≤]\s*(-?[\d.]+)$", text)
    if below:
        return None, _to_float(below.group(1))
    above = re.match(r"^[>≥]\s*(-?[\d.]+)$", text)
    if above:
        return _to_float(above.group(1)), None
    return None, None


class _Lab:
    """One lab reading reduced to what matching needs."""

    __slots__ = ("name", "direction", "is_abnormal", "positivity")

    def __init__(self, lab: dict):
        self.name = _lab_name(lab)
        self.direction = None
        self.is_abnormal = False
        self.positivity = None  # True/False when the result is qualitative

        flag = _norm(lab.get("flag"))
        if flag in _HIGH_FLAGS:
            self.direction, self.is_abnormal = "high", True
        elif flag in _LOW_FLAGS:
            self.direction, self.is_abnormal = "low", True
        elif flag and flag not in _NORMAL_FLAGS:
            self.is_abnormal = True  # "Abnormal", "Critical", "Positive", …

        text = _norm(lab.get("value_text"))
        if text:
            if any(word in text for word in _NEGATIVE_WORDS):
                self.positivity, self.is_abnormal = False, False
            elif any(word in text for word in _POSITIVE_WORDS):
                self.positivity, self.is_abnormal = True, True

        if self.direction is None and flag not in _NORMAL_FLAGS - {""}:
            value = _to_float(lab.get("value"))
            low, high = _reference_bounds(lab)
            if value is not None:
                if high is not None and value > high:
                    self.direction, self.is_abnormal = "high", True
                elif low is not None and value < low:
                    self.direction, self.is_abnormal = "low", True

    def matches_name(self, base: str) -> bool:
        if not base or not self.name:
            return False
        return base in self.name or self.name in base


def _parse_marker(marker: str) -> tuple:
    """Split a triad marker into (base name, required direction, needs positive)."""
    text = _norm(marker)
    needs_positive = False
    direction = None

    for suffix in (" positive", " reactive", " detected"):
        if text.endswith(suffix):
            needs_positive = True
            text = text[: -len(suffix)].strip()

    for word, mapped in (
        ("high ", "high"), ("elevated ", "high"), ("increased ", "high"),
        ("low ", "low"), ("decreased ", "low"), ("reduced ", "low"),
    ):
        if text.startswith(word):
            direction = mapped
            text = text[len(word):].strip()
            break

    return text, direction, needs_positive


def is_specific_symptom(term: str) -> bool:
    """True when a symptom can help distinguish one systemic disease from another."""
    text = _norm(term)
    if not text:
        return False
    return text not in NON_SPECIFIC_SYMPTOMS


def _expand(term: str) -> set[str]:
    text = _norm(term)
    return {t for t in _SYNONYMS.get(text, {text}) if t}


class Evidence:
    """Structured view of a patient record for rule-engine matching."""

    def __init__(self, labs: list, text_entries: list):
        self.labs = labs
        self.text_entries = text_entries

    # ── text ────────────────────────────────────────────────

    @staticmethod
    def _negated(entry: str, start: int) -> bool:
        window = entry[max(0, start - 40):start]
        for cue in NEGATION_CUES:
            # Cue must sit in the same clause as the match.
            if re.search(r"\b" + re.escape(cue) + r"\b[^.;,]*$", window):
                return True
        return False

    def _match_text(self, term: str) -> bool:
        text = _norm(term)
        if not text:
            return False
        for entry in self.text_entries:
            start = entry.find(text)
            while start != -1:
                if not self._negated(entry, start):
                    return True
                start = entry.find(text, start + 1)
        return False

    def match_symptom(self, term: str) -> bool:
        return any(self._match_text(variant) for variant in _expand(term))

    # ── labs ────────────────────────────────────────────────

    def match_lab_marker(self, marker: str) -> bool:
        base, direction, needs_positive = _parse_marker(marker)
        if not base:
            return False

        for lab in self.labs:
            if not lab.matches_name(base):
                continue
            if needs_positive:
                if lab.positivity is True:
                    return True
                continue
            if lab.positivity is False:
                continue
            if direction:
                if lab.direction == direction:
                    return True
                continue
            if lab.is_abnormal:
                return True

        # Markers can also name a finding recorded as a diagnosis or on
        # imaging ("hypercalcemia", "proteinuria") rather than a lab row.
        return self._match_text(base)


def build_evidence(profile_data: dict) -> Evidence:
    """Structure a patient profile for matching (labs apart from free text)."""
    timeline = (profile_data or {}).get("clinical_timeline", {}) or {}

    labs = [_Lab(lab) for lab in timeline.get("labs", []) or [] if isinstance(lab, dict)]
    labs = [lab for lab in labs if lab.name]

    entries: list[str] = []

    def add(value):
        text = _norm(value)
        if text:
            entries.append(text)

    for dx in timeline.get("diagnoses", []) or []:
        if not isinstance(dx, dict):
            continue
        if _norm(dx.get("status")) not in ("resolved", "inactive", "historical"):
            add(dx.get("name"))

    for med in timeline.get("medications", []) or []:
        if not isinstance(med, dict):
            continue
        if _norm(med.get("status")) not in ("discontinued", "stopped"):
            add(med.get("name"))

    for symptom in timeline.get("symptoms", []) or []:
        if not isinstance(symptom, dict):
            continue
        add(symptom.get("symptom_name") or symptom.get("name"))
        for episode in symptom.get("episodes", []) or []:
            if isinstance(episode, dict):
                add(episode.get("description"))
                add(episode.get("triggers"))

    for img in timeline.get("imaging", []) or []:
        if not isinstance(img, dict):
            continue
        add(img.get("description"))
        for finding in img.get("findings", []) or []:
            if isinstance(finding, str):
                add(finding)
            elif isinstance(finding, dict):
                add(finding.get("description"))

    for variant in timeline.get("genetics", []) or []:
        if not isinstance(variant, dict):
            continue
        add(variant.get("gene"))
        add(variant.get("variant"))

    return Evidence(labs, entries)
