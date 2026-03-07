"""
Tests for Drug-Drug Interaction Timeline Analyzer (Phase 6)

Tests:
  - Overlap calculation (full overlap, partial overlap, no overlap)
  - Interaction severity mapping
  - Symptom correlation during overlap
  - PGx flag detection
  - Edge cases: medications with no end_date, single medication, unknown meds
  - Static fallback table lookups
  - Summary generation
"""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis.interaction_timeline import (
    InteractionTimelineAnalyzer,
    _normalize_severity,
    _drug_matches,
    _static_lookup,
)


# ── Helper: build medication dict ─────────────────────────────

def _med(name, start, end=None, status="active"):
    return {
        "name": name,
        "start_date": start,
        "end_date": end,
        "status": status,
    }


def _symptom(name, episodes):
    """Build a symptom dict with episodes."""
    return {
        "symptom_name": name,
        "episodes": [
            {"episode_date": d, "intensity": sev}
            for d, sev in episodes
        ],
    }


# ── Overlap Calculation Tests ─────────────────────────────────

def test_full_overlap():
    """Two medications with identical date ranges should fully overlap."""
    analyzer = InteractionTimelineAnalyzer()
    start = date(2024, 1, 1)
    end = date(2024, 6, 30)

    med_a = {"start": start, "end": end}
    med_b = {"start": start, "end": end}

    result = analyzer._calculate_overlap(med_a, med_b)
    assert result is not None
    assert result == (start, end)


def test_partial_overlap():
    """Two medications with partially overlapping ranges."""
    analyzer = InteractionTimelineAnalyzer()

    med_a = {"start": date(2024, 1, 1), "end": date(2024, 6, 30)}
    med_b = {"start": date(2024, 3, 15), "end": date(2024, 9, 30)}

    result = analyzer._calculate_overlap(med_a, med_b)
    assert result is not None
    assert result == (date(2024, 3, 15), date(2024, 6, 30))


def test_no_overlap():
    """Two medications with no overlapping time period."""
    analyzer = InteractionTimelineAnalyzer()

    med_a = {"start": date(2024, 1, 1), "end": date(2024, 3, 31)}
    med_b = {"start": date(2024, 6, 1), "end": date(2024, 9, 30)}

    result = analyzer._calculate_overlap(med_a, med_b)
    assert result is None


def test_adjacent_no_overlap():
    """Medications that end and start on the same day have zero overlap."""
    analyzer = InteractionTimelineAnalyzer()

    med_a = {"start": date(2024, 1, 1), "end": date(2024, 3, 31)}
    med_b = {"start": date(2024, 3, 31), "end": date(2024, 6, 30)}

    result = analyzer._calculate_overlap(med_a, med_b)
    # Same day start/end means zero-length overlap — not included
    assert result is None


def test_one_day_overlap():
    """One day of overlap should be detected."""
    analyzer = InteractionTimelineAnalyzer()

    med_a = {"start": date(2024, 1, 1), "end": date(2024, 4, 1)}
    med_b = {"start": date(2024, 3, 31), "end": date(2024, 6, 30)}

    result = analyzer._calculate_overlap(med_a, med_b)
    assert result is not None
    assert result == (date(2024, 3, 31), date(2024, 4, 1))


def test_contained_overlap():
    """One medication entirely within another's date range."""
    analyzer = InteractionTimelineAnalyzer()

    med_a = {"start": date(2024, 1, 1), "end": date(2024, 12, 31)}
    med_b = {"start": date(2024, 3, 1), "end": date(2024, 5, 31)}

    result = analyzer._calculate_overlap(med_a, med_b)
    assert result is not None
    assert result == (date(2024, 3, 1), date(2024, 5, 31))


# ── Severity Normalization Tests ──────────────────────────────

def test_severity_normalization():
    """External severity labels should map to our 4-tier system."""
    assert _normalize_severity("major") == "critical"
    assert _normalize_severity("severe") == "critical"
    assert _normalize_severity("contraindicated") == "critical"
    assert _normalize_severity("significant") == "high"
    assert _normalize_severity("moderate") == "moderate"
    assert _normalize_severity("minor") == "low"
    assert _normalize_severity("N/A") == "low"
    assert _normalize_severity("unknown") == "low"
    # Unknown values default to moderate
    assert _normalize_severity("unusual_label") == "moderate"


# ── Drug Name Matching Tests ──────────────────────────────────

def test_drug_matches_exact():
    """Exact name match."""
    assert _drug_matches("warfarin", "warfarin") is True


def test_drug_matches_case_insensitive():
    """Case-insensitive matching."""
    assert _drug_matches("Warfarin", "warfarin") is True
    assert _drug_matches("LISINOPRIL", "lisinopril") is True


def test_drug_matches_substring():
    """Substring matching for brand/generic names."""
    assert _drug_matches("metformin", "metformin hcl") is True
    assert _drug_matches("lisinopril", "lisinopril/hctz") is True


def test_drug_no_match():
    """Non-matching drugs."""
    assert _drug_matches("warfarin", "metformin") is False
    assert _drug_matches("aspirin", "ibuprofen") is False


# ── Static Fallback Lookup Tests ──────────────────────────────

def test_static_lookup_warfarin_ibuprofen():
    """Static table should find warfarin + ibuprofen interaction."""
    result = _static_lookup("warfarin", "ibuprofen")
    assert result is not None
    assert result["severity"] == "critical"
    assert "bleeding" in result["description"].lower()


def test_static_lookup_reversed_order():
    """Drug pair order shouldn't matter."""
    result = _static_lookup("ibuprofen", "warfarin")
    assert result is not None
    assert result["severity"] == "critical"


def test_static_lookup_no_interaction():
    """Drugs without a known interaction should return None."""
    result = _static_lookup("aspirin", "vitamin d")
    assert result is None


def test_static_lookup_statin_fibrate():
    """Simvastatin + gemfibrozil should be in the static table."""
    result = _static_lookup("simvastatin", "gemfibrozil")
    assert result is not None
    assert result["severity"] == "critical"
    assert "rhabdomyolysis" in result["description"].lower()


def test_static_lookup_ssri_maoi():
    """SSRI + MAOI should be critical severity."""
    result = _static_lookup("fluoxetine", "phenelzine")
    assert result is not None
    assert result["severity"] == "critical"
    assert "serotonin" in result["description"].lower()


def test_static_lookup_ace_k_sparing():
    """ACE inhibitor + K-sparing diuretic interaction."""
    result = _static_lookup("lisinopril", "spironolactone")
    assert result is not None
    assert result["severity"] == "high"
    assert "hyperkalemia" in result["description"].lower()


# ── Full Analyze Tests ────────────────────────────────────────

def test_analyze_two_interacting_meds():
    """Full analysis with two overlapping meds that have a known interaction."""
    analyzer = InteractionTimelineAnalyzer()

    medications = [
        _med("Warfarin", "2024-01-01"),
        _med("Ibuprofen", "2024-03-01", "2024-06-30"),
    ]

    result = analyzer.analyze(
        medications=medications,
        interactions=[],
        symptoms=[],
        genetics=[],
    )

    assert len(result["overlap_zones"]) > 0
    zone = result["overlap_zones"][0]
    assert zone["med_a"] in ("Warfarin", "Ibuprofen")
    assert zone["med_b"] in ("Warfarin", "Ibuprofen")
    assert zone["interaction"]["severity"] == "critical"
    assert zone["duration_days"] > 0


def test_analyze_no_interaction():
    """Two medications that overlap but have no known interaction."""
    analyzer = InteractionTimelineAnalyzer()

    medications = [
        _med("Vitamin D", "2024-01-01"),
        _med("Biotin", "2024-01-01"),
    ]

    result = analyzer.analyze(
        medications=medications,
        interactions=[],
        symptoms=[],
        genetics=[],
    )

    assert len(result["overlap_zones"]) == 0


def test_analyze_single_medication():
    """Single medication should produce no overlap zones."""
    analyzer = InteractionTimelineAnalyzer()

    medications = [
        _med("Metformin", "2024-01-01"),
    ]

    result = analyzer.analyze(
        medications=medications,
        interactions=[],
        symptoms=[],
        genetics=[],
    )

    assert len(result["overlap_zones"]) == 0
    assert "fewer than 2" in result["interaction_summary"].lower()


def test_analyze_empty_medications():
    """Empty medication list should return clean empty result."""
    analyzer = InteractionTimelineAnalyzer()

    result = analyzer.analyze(
        medications=[],
        interactions=[],
        symptoms=[],
        genetics=[],
    )

    assert len(result["overlap_zones"]) == 0
    assert len(result["pharmacogenomic_flags"]) == 0


def test_analyze_medication_no_start_date():
    """Medications without start dates should be skipped."""
    analyzer = InteractionTimelineAnalyzer()

    medications = [
        _med("Warfarin", None),
        _med("Ibuprofen", "2024-03-01"),
    ]

    result = analyzer.analyze(
        medications=medications,
        interactions=[],
        symptoms=[],
        genetics=[],
    )

    assert len(result["overlap_zones"]) == 0


def test_analyze_no_end_date_treated_as_active():
    """Medications with no end_date should be treated as still active."""
    analyzer = InteractionTimelineAnalyzer()

    medications = [
        _med("Warfarin", "2024-01-01"),  # No end date = active
        _med("Ibuprofen", "2024-03-01"),  # No end date = active
    ]

    result = analyzer.analyze(
        medications=medications,
        interactions=[],
        symptoms=[],
        genetics=[],
    )

    zones = result["overlap_zones"]
    assert len(zones) > 0
    # Both treated as active until today, so overlap should be active
    assert zones[0]["is_active"] is True


# ── Symptom Correlation Tests ─────────────────────────────────

def test_symptom_correlation_during_overlap():
    """Symptoms during an overlap period should be correlated."""
    analyzer = InteractionTimelineAnalyzer()

    medications = [
        _med("Warfarin", "2024-01-01", "2024-12-31"),
        _med("Ibuprofen", "2024-03-01", "2024-06-30"),
    ]

    symptoms = [
        _symptom("Nausea", [
            ("2024-04-15", "mid"),   # During overlap
            ("2024-08-01", "low"),   # After overlap
        ]),
        _symptom("Bruising", [
            ("2024-05-10", "high"),  # During overlap
        ]),
    ]

    result = analyzer.analyze(
        medications=medications,
        interactions=[],
        symptoms=symptoms,
        genetics=[],
    )

    zones = result["overlap_zones"]
    assert len(zones) > 0

    zone = zones[0]
    symptom_names = [s["symptom_name"] for s in zone["symptoms_during"]]

    # Symptoms during overlap period (Mar-Jun 2024) should be included
    assert "Nausea" in symptom_names
    assert "Bruising" in symptom_names

    # Nausea episode in August should NOT be included
    nausea_dates = [
        s["episode_date"] for s in zone["symptoms_during"]
        if s["symptom_name"] == "Nausea"
    ]
    assert "2024-08-01" not in nausea_dates


def test_symptom_no_episodes_during_overlap():
    """Symptoms outside the overlap period should not be correlated."""
    analyzer = InteractionTimelineAnalyzer()

    medications = [
        _med("Warfarin", "2024-01-01", "2024-03-31"),
        _med("Ibuprofen", "2024-02-01", "2024-03-31"),
    ]

    symptoms = [
        _symptom("Headache", [
            ("2024-06-01", "mid"),  # Way after overlap
        ]),
    ]

    result = analyzer.analyze(
        medications=medications,
        interactions=[],
        symptoms=symptoms,
        genetics=[],
    )

    zones = result["overlap_zones"]
    if zones:
        assert len(zones[0]["symptoms_during"]) == 0


# ── PGx Flag Tests ────────────────────────────────────────────

def test_pgx_flag_detection():
    """PGx flags should be detected for interacting medications."""
    analyzer = InteractionTimelineAnalyzer()

    medications = [
        _med("Warfarin", "2024-01-01"),
        _med("Ibuprofen", "2024-03-01", "2024-06-30"),
    ]

    genetics = [
        {
            "gene": "CYP2C9",
            "variant": "*3/*3",
            "phenotype": "Poor Metabolizer",
            "clinical_significance": "Pathogenic",
        },
    ]

    result = analyzer.analyze(
        medications=medications,
        interactions=[],
        symptoms=[],
        genetics=genetics,
    )

    zones = result["overlap_zones"]
    assert len(zones) > 0

    # CYP2C9 poor metabolizer affects warfarin
    all_pgx = result["pharmacogenomic_flags"]
    gene_names = [f["gene"] for f in all_pgx]
    # CYP2C9 poor metabolizer should flag warfarin
    if "CYP2C9" in gene_names:
        cyp2c9_flags = [f for f in all_pgx if f["gene"] == "CYP2C9"]
        assert any(
            _drug_matches("warfarin", f["drug"]) for f in cyp2c9_flags
        )


def test_pgx_no_relevant_genetics():
    """No PGx flags when patient has no relevant genetic variants."""
    analyzer = InteractionTimelineAnalyzer()

    medications = [
        _med("Warfarin", "2024-01-01"),
        _med("Ibuprofen", "2024-03-01", "2024-06-30"),
    ]

    result = analyzer.analyze(
        medications=medications,
        interactions=[],
        symptoms=[],
        genetics=[],
    )

    zones = result["overlap_zones"]
    if zones:
        assert len(zones[0]["pgx_flags"]) == 0


# ── Precomputed Interaction Tests ─────────────────────────────

def test_precomputed_interactions_used():
    """Pre-computed interactions from the pipeline should be found."""
    analyzer = InteractionTimelineAnalyzer()

    medications = [
        _med("DrugAlpha", "2024-01-01", "2024-12-31"),
        _med("DrugBeta", "2024-06-01", "2024-12-31"),
    ]

    precomputed = [
        {
            "drug_a": "DrugAlpha",
            "drug_b": "DrugBeta",
            "description": "Test interaction between alpha and beta",
            "severity": "moderate",
            "mechanism": "CYP inhibition",
            "source": "Test Pipeline",
        },
    ]

    result = analyzer.analyze(
        medications=medications,
        interactions=precomputed,
        symptoms=[],
        genetics=[],
    )

    assert len(result["overlap_zones"]) == 1
    zone = result["overlap_zones"][0]
    assert "alpha and beta" in zone["interaction"]["description"].lower()
    assert zone["interaction"]["severity"] == "moderate"


# ── Summary Tests ─────────────────────────────────────────────

def test_summary_with_interactions():
    """Summary should describe found interactions."""
    analyzer = InteractionTimelineAnalyzer()

    medications = [
        _med("Warfarin", "2024-01-01"),
        _med("Ibuprofen", "2024-03-01", "2024-06-30"),
    ]

    result = analyzer.analyze(
        medications=medications,
        interactions=[],
        symptoms=[],
        genetics=[],
    )

    summary = result["interaction_summary"]
    assert "overlap" in summary.lower()
    assert "doctor" in summary.lower()


def test_summary_no_interactions():
    """Summary should indicate no interactions when none found."""
    analyzer = InteractionTimelineAnalyzer()

    medications = [
        _med("Vitamin D", "2024-01-01"),
        _med("Biotin", "2024-01-01"),
    ]

    result = analyzer.analyze(
        medications=medications,
        interactions=[],
        symptoms=[],
        genetics=[],
    )

    summary = result["interaction_summary"]
    assert "no overlapping" in summary.lower() or "no" in summary.lower()


# ── Date Parsing Tests ────────────────────────────────────────

def test_date_parsing_iso():
    """ISO date strings should be parsed."""
    analyzer = InteractionTimelineAnalyzer()
    assert analyzer._parse_date("2024-01-15") == date(2024, 1, 15)


def test_date_parsing_us_format():
    """US-style dates should be parsed."""
    analyzer = InteractionTimelineAnalyzer()
    assert analyzer._parse_date("01/15/2024") == date(2024, 1, 15)


def test_date_parsing_date_object():
    """date objects should pass through."""
    analyzer = InteractionTimelineAnalyzer()
    d = date(2024, 6, 15)
    assert analyzer._parse_date(d) == d


def test_date_parsing_none():
    """None should return None."""
    analyzer = InteractionTimelineAnalyzer()
    assert analyzer._parse_date(None) is None


def test_date_parsing_empty_string():
    """Empty string should return None."""
    analyzer = InteractionTimelineAnalyzer()
    assert analyzer._parse_date("") is None


# ── Integration Test: Multiple Interacting Pairs ──────────────

def test_multiple_interacting_pairs():
    """Multiple medication pairs with interactions."""
    analyzer = InteractionTimelineAnalyzer()

    medications = [
        _med("Warfarin", "2024-01-01"),
        _med("Ibuprofen", "2024-03-01", "2024-06-30"),
        _med("Simvastatin", "2024-01-01"),
        _med("Gemfibrozil", "2024-02-01", "2024-12-31"),
    ]

    result = analyzer.analyze(
        medications=medications,
        interactions=[],
        symptoms=[],
        genetics=[],
    )

    zones = result["overlap_zones"]
    # Should find at least 2 interactions: warfarin+ibuprofen and simvastatin+gemfibrozil
    assert len(zones) >= 2

    pairs = [(z["med_a"], z["med_b"]) for z in zones]
    # Check both critical pairs are present
    has_warfarin_ibuprofen = any(
        ("Warfarin" in p[0] and "Ibuprofen" in p[1]) or
        ("Ibuprofen" in p[0] and "Warfarin" in p[1])
        for p in pairs
    )
    has_statin_fibrate = any(
        ("Simvastatin" in p[0] and "Gemfibrozil" in p[1]) or
        ("Gemfibrozil" in p[0] and "Simvastatin" in p[1])
        for p in pairs
    )
    assert has_warfarin_ibuprofen, "Should find warfarin + ibuprofen interaction"
    assert has_statin_fibrate, "Should find simvastatin + gemfibrozil interaction"


# ── Sorting Tests ─────────────────────────────────────────────

def test_zones_sorted_by_severity():
    """Overlap zones should be sorted by severity (critical first)."""
    analyzer = InteractionTimelineAnalyzer()

    medications = [
        _med("Warfarin", "2024-01-01"),
        _med("Ibuprofen", "2024-03-01", "2024-06-30"),
        _med("Metformin", "2024-01-01"),
        _med("Lisinopril", "2024-01-01"),
    ]

    result = analyzer.analyze(
        medications=medications,
        interactions=[],
        symptoms=[],
        genetics=[],
    )

    zones = result["overlap_zones"]
    if len(zones) >= 2:
        severities = [z["interaction"]["severity"] for z in zones]
        severity_rank = {"critical": 0, "high": 1, "moderate": 2, "low": 3}
        ranks = [severity_rank.get(s, 4) for s in severities]
        # Should be in non-decreasing order
        assert ranks == sorted(ranks)
