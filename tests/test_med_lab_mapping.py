"""
Tests for src/analysis/med_lab_mapping.py

Covers:
  - get_relevant_medications with known medication-lab pairs
  - Case-insensitive matching
  - Dose change detection from sequential records
  - Empty medication list handling
  - Labs with no known mapping (fallback behavior)
  - get_medication_events within and outside date range
"""

import pytest
from datetime import date

from src.analysis.med_lab_mapping import (
    get_relevant_medications,
    detect_dose_changes,
    get_medication_events,
    MED_LAB_EFFECTS,
    MED_COLORS,
)


# ── Fixtures ──────────────────────────────────────────────

@pytest.fixture
def sample_medications():
    """Realistic medication list matching demo profile structure."""
    return [
        {
            "name": "Metformin",
            "dose": "1000mg",
            "status": "active",
            "start_date": "2019-04-01",
        },
        {
            "name": "Lisinopril",
            "dose": "20mg",
            "status": "active",
            "start_date": "2020-02-15",
        },
        {
            "name": "Atorvastatin",
            "dose": "40mg",
            "status": "active",
            "start_date": "2020-02-15",
        },
        {
            "name": "Metoprolol Succinate",
            "dose": "50mg",
            "status": "active",
            "start_date": "2021-03-20",
        },
        {
            "name": "Insulin Glargine",
            "dose": "24 units",
            "status": "active",
            "start_date": "2023-06-01",
        },
        {
            "name": "Gabapentin",
            "dose": "300mg",
            "status": "active",
            "start_date": "2024-01-15",
        },
        {
            "name": "Omeprazole",
            "dose": "20mg",
            "status": "active",
            "start_date": "2021-08-20",
        },
        {
            "name": "Vitamin D3",
            "dose": "2000 IU",
            "status": "active",
            "start_date": "2024-03-01",
        },
        {
            "name": "Glipizide",
            "dose": "5mg",
            "status": "discontinued",
            "start_date": "2019-04-01",
            "end_date": "2023-05-15",
        },
    ]


# ── get_relevant_medications ──────────────────────────────

class TestGetRelevantMedications:

    def test_hba1c_returns_diabetes_meds(self, sample_medications):
        """HbA1c should match diabetes medications."""
        result = get_relevant_medications("HbA1c", sample_medications)
        names = [m["name"] for m in result]
        assert "Metformin" in names
        assert "Insulin Glargine" in names
        assert "Glipizide" in names

    def test_hba1c_does_not_return_unrelated_meds(self, sample_medications):
        """HbA1c should NOT match statins or PPIs."""
        result = get_relevant_medications("HbA1c", sample_medications)
        names = [m["name"] for m in result]
        assert "Atorvastatin" not in names
        assert "Omeprazole" not in names

    def test_ldl_returns_statin(self, sample_medications):
        """LDL should match Atorvastatin."""
        result = get_relevant_medications("LDL", sample_medications)
        names = [m["name"] for m in result]
        assert "Atorvastatin" in names
        assert "Metformin" not in names

    def test_creatinine_returns_renal_meds(self, sample_medications):
        """Creatinine should match medications that affect kidneys."""
        result = get_relevant_medications("Creatinine", sample_medications)
        names = [m["name"] for m in result]
        assert "Lisinopril" in names
        assert "Metformin" in names

    def test_vitamin_d_returns_supplement(self, sample_medications):
        """Vitamin D lab should match Vitamin D3 supplement."""
        result = get_relevant_medications("Vitamin D", sample_medications)
        names = [m["name"] for m in result]
        assert "Vitamin D3" in names

    def test_case_insensitive_metformin(self, sample_medications):
        """Matching should be case-insensitive."""
        result_lower = get_relevant_medications("hba1c", sample_medications)
        result_upper = get_relevant_medications("HBAIC", sample_medications)
        result_mixed = get_relevant_medications("HbA1c", sample_medications)

        # Lower and mixed should both find Metformin
        names_lower = [m["name"] for m in result_lower]
        names_mixed = [m["name"] for m in result_mixed]
        assert "Metformin" in names_lower
        assert "Metformin" in names_mixed

    def test_enriched_fields_present(self, sample_medications):
        """Each returned medication should have all enrichment fields."""
        result = get_relevant_medications("HbA1c", sample_medications)
        assert len(result) > 0

        for med in result:
            assert "name" in med
            assert "generic_name" in med
            assert "start_date" in med
            assert "end_date" in med
            assert "dosage" in med
            assert "status" in med
            assert "color" in med
            assert "dose_changes" in med
            assert "events" in med
            # Color should be from the palette
            assert med["color"] in MED_COLORS

    def test_empty_medication_list(self):
        """Empty medication list should return empty result."""
        result = get_relevant_medications("HbA1c", [])
        assert result == []

    def test_none_medication_list(self):
        """None medication list should return empty result."""
        result = get_relevant_medications("HbA1c", None)
        assert result == []

    def test_empty_lab_name(self, sample_medications):
        """Empty lab name should return empty result."""
        result = get_relevant_medications("", sample_medications)
        assert result == []

    def test_fallback_when_no_mappings_exist(self):
        """When no medications have known mappings, show ALL as fallback."""
        unknown_meds = [
            {"name": "SuperDrug X", "dose": "10mg", "status": "active", "start_date": "2024-01-01"},
            {"name": "MysteryPill Y", "dose": "5mg", "status": "active", "start_date": "2024-06-01"},
        ]
        result = get_relevant_medications("HbA1c", unknown_meds)
        # Fallback: should return all medications
        assert len(result) == 2
        names = [m["name"] for m in result]
        assert "SuperDrug X" in names
        assert "MysteryPill Y" in names

    def test_discontinued_med_still_returned(self, sample_medications):
        """Discontinued medications should still appear if they affect the lab."""
        result = get_relevant_medications("glucose", sample_medications)
        names = [m["name"] for m in result]
        assert "Glipizide" in names  # discontinued but still relevant

    def test_glipizide_has_end_date(self, sample_medications):
        """Discontinued Glipizide should carry its end_date."""
        result = get_relevant_medications("glucose", sample_medications)
        glipizide = [m for m in result if m["name"] == "Glipizide"][0]
        assert glipizide["end_date"] == "2023-05-15"
        assert glipizide["status"] == "discontinued"

    def test_vitamin_b12_returns_ppi_and_metformin(self, sample_medications):
        """Vitamin B12 should match both PPI (Omeprazole) and Metformin."""
        result = get_relevant_medications("Vitamin B12", sample_medications)
        names = [m["name"] for m in result]
        assert "Omeprazole" in names
        assert "Metformin" in names


# ── detect_dose_changes ───────────────────────────────────

class TestDetectDoseChanges:

    def test_detects_dose_change(self):
        """Should detect when dose changes between two records of same med."""
        meds = [
            {"name": "Metformin", "dose": "500mg", "start_date": "2019-01-01"},
            {"name": "Metformin", "dose": "1000mg", "start_date": "2019-06-01"},
            {"name": "Lisinopril", "dose": "10mg", "start_date": "2020-01-01"},
        ]
        changes = detect_dose_changes("Metformin", meds)
        assert len(changes) == 1
        assert changes[0]["from_dose"] == "500mg"
        assert changes[0]["to_dose"] == "1000mg"
        assert changes[0]["date"] == "2019-06-01"

    def test_no_change_same_dose(self):
        """Should return empty if dose is the same."""
        meds = [
            {"name": "Metformin", "dose": "1000mg", "start_date": "2019-01-01"},
            {"name": "Metformin", "dose": "1000mg", "start_date": "2020-01-01"},
        ]
        changes = detect_dose_changes("Metformin", meds)
        assert len(changes) == 0

    def test_multiple_dose_changes(self):
        """Should detect multiple sequential dose changes."""
        meds = [
            {"name": "Lisinopril", "dose": "5mg", "start_date": "2019-01-01"},
            {"name": "Lisinopril", "dose": "10mg", "start_date": "2019-06-01"},
            {"name": "Lisinopril", "dose": "20mg", "start_date": "2020-03-01"},
        ]
        changes = detect_dose_changes("Lisinopril", meds)
        assert len(changes) == 2
        assert changes[0]["to_dose"] == "10mg"
        assert changes[1]["to_dose"] == "20mg"

    def test_single_record_no_changes(self):
        """Single record cannot have dose changes."""
        meds = [
            {"name": "Metformin", "dose": "1000mg", "start_date": "2019-01-01"},
        ]
        changes = detect_dose_changes("Metformin", meds)
        assert len(changes) == 0

    def test_empty_list(self):
        """Empty list should return no changes."""
        changes = detect_dose_changes("Metformin", [])
        assert changes == []

    def test_empty_name(self):
        """Empty medication name should return no changes."""
        changes = detect_dose_changes("", [{"name": "Metformin", "dose": "500mg", "start_date": "2024-01-01"}])
        assert changes == []


# ── get_medication_events ─────────────────────────────────

class TestGetMedicationEvents:

    def test_active_med_has_started_event(self):
        """Active medication should have a 'started' event."""
        med = {"name": "Metformin", "start_date": "2019-04-01", "status": "active"}
        events = get_medication_events(med)
        types = [e["type"] for e in events]
        assert "started" in types
        started = [e for e in events if e["type"] == "started"][0]
        assert started["date"] == "2019-04-01"
        assert "Metformin" in started["label"]

    def test_discontinued_med_has_stopped_event(self):
        """Discontinued medication should have both started and stopped events."""
        med = {
            "name": "Glipizide",
            "start_date": "2019-04-01",
            "end_date": "2023-05-15",
            "status": "discontinued",
        }
        events = get_medication_events(med)
        types = [e["type"] for e in events]
        assert "started" in types
        assert "stopped" in types

    def test_date_range_filters_events(self):
        """Events outside the date range should be filtered out."""
        med = {
            "name": "Glipizide",
            "start_date": "2019-04-01",
            "end_date": "2023-05-15",
            "status": "discontinued",
        }
        # Range that only includes the stop date
        events = get_medication_events(med, date_range=("2023-01-01", "2024-01-01"))
        types = [e["type"] for e in events]
        assert "stopped" in types
        assert "started" not in types

    def test_date_range_excludes_all(self):
        """Range that doesn't overlap any events should return empty."""
        med = {
            "name": "Metformin",
            "start_date": "2019-04-01",
            "status": "active",
        }
        events = get_medication_events(med, date_range=("2024-01-01", "2025-01-01"))
        assert len(events) == 0

    def test_no_dates_returns_empty(self):
        """Medication with no dates should return no events."""
        med = {"name": "Metformin", "status": "active"}
        events = get_medication_events(med)
        assert len(events) == 0

    def test_none_date_range_returns_all(self):
        """None date_range should return all events (no filtering)."""
        med = {
            "name": "Glipizide",
            "start_date": "2019-04-01",
            "end_date": "2023-05-15",
        }
        events = get_medication_events(med, date_range=None)
        assert len(events) == 2


# ── Mapping Table Coverage ────────────────────────────────

class TestMappingTableIntegrity:

    def test_mapping_table_not_empty(self):
        """Mapping table should have at least 40 entries."""
        assert len(MED_LAB_EFFECTS) >= 40

    def test_all_lab_names_lowercase(self):
        """All lab names in mappings should be lowercase."""
        for med, labs in MED_LAB_EFFECTS.items():
            for lab in labs:
                assert lab == lab.lower(), f"Lab '{lab}' for med '{med}' is not lowercase"

    def test_all_med_names_lowercase(self):
        """All medication keys should be lowercase."""
        for med in MED_LAB_EFFECTS:
            assert med == med.lower(), f"Medication key '{med}' is not lowercase"

    def test_color_palette_has_entries(self):
        """Color palette should have at least 6 colors."""
        assert len(MED_COLORS) >= 6
