"""
Clinical Intelligence Hub — Medication ↔ Lab Test Mapping

Static knowledge base mapping medications to the lab tests they affect.
Used by the Trajectories overlay to show treatment bars alongside lab charts.

Functions:
  - get_relevant_medications(lab_name, medications) → filtered + enriched list
  - detect_dose_changes(medication_name, all_medications) → [{date, from_dose, to_dose}]
  - get_medication_events(medication, date_range) → [{type, date, label}]
"""

import logging
from datetime import date, datetime
from typing import Optional

logger = logging.getLogger("CIH-MedLabMapping")


# ── Color Palette for Treatment Bars ─────────────────────

MED_COLORS = [
    "#3b82f6",   # blue
    "#f97316",   # orange
    "#a78bfa",   # violet
    "#ec4899",   # pink
    "#10b981",   # emerald
    "#f0c550",   # honey
]


# ── Medication → Lab Test Mapping Table ──────────────────
#
# Keys: lowercase generic medication name
# Values: set of lowercase lab test names this drug affects
#
# Grouped by therapeutic class for maintainability.

MED_LAB_EFFECTS = {
    # ── Diabetes ──────────────────────────────────────────
    "metformin":            {"hba1c", "hemoglobin a1c", "glucose", "fasting glucose", "vitamin b12", "creatinine", "egfr"},
    "glipizide":            {"hba1c", "hemoglobin a1c", "glucose", "fasting glucose"},
    "glyburide":            {"hba1c", "hemoglobin a1c", "glucose", "fasting glucose"},
    "glimepiride":          {"hba1c", "hemoglobin a1c", "glucose", "fasting glucose"},
    "insulin glargine":     {"hba1c", "hemoglobin a1c", "glucose", "fasting glucose"},
    "insulin lispro":       {"hba1c", "hemoglobin a1c", "glucose", "fasting glucose"},
    "insulin aspart":       {"hba1c", "hemoglobin a1c", "glucose", "fasting glucose"},
    "insulin detemir":      {"hba1c", "hemoglobin a1c", "glucose", "fasting glucose"},
    "insulin nph":          {"hba1c", "hemoglobin a1c", "glucose", "fasting glucose"},
    "semaglutide":          {"hba1c", "hemoglobin a1c", "glucose", "fasting glucose", "triglycerides", "total cholesterol"},
    "liraglutide":          {"hba1c", "hemoglobin a1c", "glucose", "fasting glucose"},
    "dulaglutide":          {"hba1c", "hemoglobin a1c", "glucose", "fasting glucose"},
    "tirzepatide":          {"hba1c", "hemoglobin a1c", "glucose", "fasting glucose", "triglycerides"},
    "empagliflozin":        {"hba1c", "hemoglobin a1c", "glucose", "fasting glucose", "egfr", "creatinine", "potassium"},
    "dapagliflozin":        {"hba1c", "hemoglobin a1c", "glucose", "fasting glucose", "egfr", "creatinine"},
    "canagliflozin":        {"hba1c", "hemoglobin a1c", "glucose", "fasting glucose", "egfr", "creatinine"},
    "pioglitazone":         {"hba1c", "hemoglobin a1c", "glucose", "fasting glucose", "alt", "ast"},
    "sitagliptin":          {"hba1c", "hemoglobin a1c", "glucose", "fasting glucose"},

    # ── Cardiovascular: Statins ──────────────────────────
    "atorvastatin":         {"ldl", "hdl", "total cholesterol", "triglycerides", "alt", "ast", "crp"},
    "rosuvastatin":         {"ldl", "hdl", "total cholesterol", "triglycerides", "alt", "ast", "crp"},
    "simvastatin":          {"ldl", "hdl", "total cholesterol", "triglycerides", "alt", "ast"},
    "pravastatin":          {"ldl", "hdl", "total cholesterol", "triglycerides", "alt", "ast"},
    "lovastatin":           {"ldl", "hdl", "total cholesterol", "triglycerides", "alt", "ast"},

    # ── Cardiovascular: ACE Inhibitors / ARBs ────────────
    "lisinopril":           {"creatinine", "egfr", "potassium", "bun"},
    "enalapril":            {"creatinine", "egfr", "potassium", "bun"},
    "ramipril":             {"creatinine", "egfr", "potassium", "bun"},
    "losartan":             {"creatinine", "egfr", "potassium", "bun", "uric acid"},
    "valsartan":            {"creatinine", "egfr", "potassium", "bun"},
    "irbesartan":           {"creatinine", "egfr", "potassium", "bun"},
    "olmesartan":           {"creatinine", "egfr", "potassium", "bun"},

    # ── Cardiovascular: Beta Blockers ────────────────────
    "metoprolol succinate": {"glucose", "fasting glucose", "triglycerides"},
    "metoprolol tartrate":  {"glucose", "fasting glucose", "triglycerides"},
    "atenolol":             {"glucose", "fasting glucose", "triglycerides"},
    "carvedilol":           {"glucose", "fasting glucose"},
    "propranolol":          {"glucose", "fasting glucose", "triglycerides", "tsh"},

    # ── Cardiovascular: Other ────────────────────────────
    "amlodipine":           {"creatinine", "egfr"},
    "hydrochlorothiazide":  {"potassium", "sodium", "glucose", "fasting glucose", "uric acid", "calcium", "creatinine"},
    "furosemide":           {"potassium", "sodium", "creatinine", "egfr", "bun", "calcium"},
    "spironolactone":       {"potassium", "sodium", "creatinine", "egfr"},
    "warfarin":             {"inr"},
    "apixaban":             {"creatinine", "egfr"},
    "rivaroxaban":          {"creatinine", "egfr"},
    "clopidogrel":          {"platelets"},
    "aspirin":              {"platelets"},

    # ── Thyroid ──────────────────────────────────────────
    "levothyroxine":        {"tsh", "free t4", "free t3", "total cholesterol", "ldl"},
    "methimazole":          {"tsh", "free t4", "free t3", "wbc", "alt", "ast"},
    "propylthiouracil":     {"tsh", "free t4", "free t3", "wbc", "alt", "ast"},

    # ── GI / Acid Suppression ────────────────────────────
    "omeprazole":           {"vitamin b12", "calcium", "iron", "ferritin"},
    "pantoprazole":         {"vitamin b12", "calcium", "iron", "ferritin"},
    "esomeprazole":         {"vitamin b12", "calcium", "iron", "ferritin"},
    "lansoprazole":         {"vitamin b12", "calcium", "iron", "ferritin"},

    # ── Neurological / Pain ──────────────────────────────
    "gabapentin":           {"creatinine", "egfr"},
    "pregabalin":           {"creatinine", "egfr"},
    "carbamazepine":        {"sodium", "wbc", "platelets", "alt", "ast"},
    "valproic acid":        {"alt", "ast", "platelets", "ammonia"},
    "phenytoin":            {"albumin", "calcium", "folate", "vitamin d", "25-hydroxy vitamin d"},

    # ── Supplements ──────────────────────────────────────
    "vitamin d3":           {"vitamin d", "25-hydroxy vitamin d", "calcium"},
    "cholecalciferol":      {"vitamin d", "25-hydroxy vitamin d", "calcium"},
    "iron supplement":      {"iron", "ferritin", "hemoglobin", "hematocrit"},
    "ferrous sulfate":      {"iron", "ferritin", "hemoglobin", "hematocrit"},

    # ── Immunosuppressants / Rheumatology ────────────────
    "methotrexate":         {"alt", "ast", "wbc", "rbc", "platelets", "creatinine", "albumin"},
    "prednisone":           {"glucose", "fasting glucose", "wbc", "potassium", "calcium"},
    "hydroxychloroquine":   {"crp", "esr", "wbc"},

    # ── Gout ─────────────────────────────────────────────
    "allopurinol":          {"uric acid", "alt", "ast", "creatinine", "egfr"},
    "febuxostat":           {"uric acid", "alt", "ast"},
    "colchicine":           {"uric acid", "wbc"},
}


def _normalize_name(name: str) -> str:
    """Lowercase, strip whitespace for matching."""
    return (name or "").strip().lower()


def _find_mapping_key(medication_name: str) -> Optional[str]:
    """
    Find the MED_LAB_EFFECTS key that matches a medication name.
    Tries exact match first, then substring containment.
    """
    norm = _normalize_name(medication_name)
    if not norm:
        return None

    # Exact match
    if norm in MED_LAB_EFFECTS:
        return norm

    # Check if the medication name contains a known key
    for key in MED_LAB_EFFECTS:
        if key in norm or norm in key:
            return key

    return None


def get_relevant_medications(lab_name: str, medications: list) -> list:
    """
    Given a lab test name and a list of medication dicts, return only the
    medications that are known to affect that lab.

    If no mapping exists for any of the medications, falls back to showing
    ALL active medications (better to over-show than silently hide).

    Args:
        lab_name: The lab test name (e.g., "HbA1c", "LDL")
        medications: List of medication dicts from profile_data

    Returns:
        List of enriched medication dicts with: name, generic_name,
        start_date, end_date, dosage, status, color, dose_changes, events
    """
    if not medications:
        return []

    lab_key = _normalize_name(lab_name)
    if not lab_key:
        return []

    matched = []
    unmatched_count = 0

    for med in medications:
        med_name = med.get("name", "")
        generic = med.get("generic_name") or ""
        mapping_key = _find_mapping_key(med_name) or _find_mapping_key(generic)

        if mapping_key is not None:
            affected_labs = MED_LAB_EFFECTS[mapping_key]
            if lab_key in affected_labs:
                matched.append(med)
            else:
                # Check partial lab name match (e.g., "HbA1c" vs "hba1c")
                lab_found = False
                for affected in affected_labs:
                    if affected in lab_key or lab_key in affected:
                        lab_found = True
                        break
                if lab_found:
                    matched.append(med)
        else:
            unmatched_count += 1

    # Fallback: if NO medications have mappings at all, show everything active
    if unmatched_count == len(medications) and unmatched_count > 0:
        logger.warning(
            "No medication mappings found for lab '%s' — showing all %d medications as fallback",
            lab_name, len(medications),
        )
        matched = list(medications)

    # Enrich each matched medication with display fields
    result = []
    for idx, med in enumerate(matched):
        color = MED_COLORS[idx % len(MED_COLORS)]
        med_name = med.get("name", "Unknown")

        # Detect dose changes for this medication
        dose_changes = detect_dose_changes(med_name, medications)

        # Get date range from the lab data (we don't have it here, so get all events)
        events = get_medication_events(med, date_range=None)

        enriched = {
            "name": med_name,
            "generic_name": med.get("generic_name") or "",
            "start_date": _format_date(med.get("start_date")),
            "end_date": _format_date(med.get("end_date")),
            "dosage": med.get("dosage") or med.get("dose") or "",
            "status": med.get("status", "unknown"),
            "color": color,
            "dose_changes": dose_changes,
            "events": events,
        }
        result.append(enriched)

    return result


def detect_dose_changes(medication_name: str, all_medications: list) -> list:
    """
    Find dose changes by looking at multiple records of the same medication
    with different dosages at different dates.

    Returns: [{date, from_dose, to_dose}]
    """
    if not medication_name or not all_medications:
        return []

    norm_name = _normalize_name(medication_name)
    same_med_records = []

    for med in all_medications:
        if _normalize_name(med.get("name", "")) == norm_name:
            dose = med.get("dosage") or med.get("dose") or ""
            start = med.get("start_date")
            if start and dose:
                same_med_records.append({
                    "dose": dose,
                    "start_date": start,
                })

    if len(same_med_records) < 2:
        return []

    # Sort by date
    def parse_date_for_sort(d):
        if isinstance(d, date):
            return d
        if isinstance(d, str):
            try:
                return datetime.strptime(d.strip(), "%Y-%m-%d").date()
            except (ValueError, TypeError):
                return date.min
        return date.min

    same_med_records.sort(key=lambda r: parse_date_for_sort(r["start_date"]))

    changes = []
    for i in range(1, len(same_med_records)):
        prev_dose = same_med_records[i - 1]["dose"]
        curr_dose = same_med_records[i]["dose"]
        if _normalize_name(prev_dose) != _normalize_name(curr_dose):
            change_date = same_med_records[i]["start_date"]
            changes.append({
                "date": _format_date(change_date),
                "from_dose": prev_dose,
                "to_dose": curr_dose,
            })

    return changes


def get_medication_events(medication: dict, date_range: tuple = None) -> list:
    """
    Return events (started, stopped, dose_changed) for a medication,
    optionally filtered to a date range.

    Args:
        medication: Single medication dict
        date_range: Optional (start_date, end_date) tuple as date objects or ISO strings

    Returns: [{type, date, label}]
    """
    events = []
    med_name = medication.get("name", "Unknown")

    start = medication.get("start_date")
    end = medication.get("end_date")

    if start:
        events.append({
            "type": "started",
            "date": _format_date(start),
            "label": "Started " + med_name,
        })

    if end:
        events.append({
            "type": "stopped",
            "date": _format_date(end),
            "label": "Stopped " + med_name,
        })

    # Filter by date range if provided
    if date_range is not None and len(date_range) == 2:
        range_start = _parse_date(date_range[0])
        range_end = _parse_date(date_range[1])

        if range_start and range_end:
            filtered = []
            for evt in events:
                evt_date = _parse_date(evt["date"])
                if evt_date and range_start <= evt_date <= range_end:
                    filtered.append(evt)
            events = filtered

    return events


def _format_date(d) -> Optional[str]:
    """Convert date to ISO string, or return as-is if already a string."""
    if d is None:
        return None
    if isinstance(d, date):
        return d.isoformat()
    if isinstance(d, str):
        return d.strip()
    return str(d)


def _parse_date(d) -> Optional[date]:
    """Parse a date from string or date object."""
    if isinstance(d, date):
        return d
    if isinstance(d, str):
        try:
            return datetime.strptime(d.strip(), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None
    return None
