"""
Tests for src/analysis/side_effect_scorer.py

Covers:
  - Known side effect matching (Factor 1)
  - Temporal relationship detection (Factor 2)
  - Dose-response correlation (Factor 3)
  - Genetic factor lookup (Factor 4)
  - Alternative explanation logic (Factor 5)
  - Likelihood thresholds (low / moderate / high / very_high)
  - Batch scoring (score_all_linked_episodes)
"""

import pytest

from src.analysis.side_effect_scorer import (
    SideEffectScorer,
    COMMON_SIDE_EFFECTS,
    GENE_DRUG_RISK,
    _normalize_name,
    _find_side_effect_key,
    _symptom_matches,
    _parse_date,
    _extract_dose_number,
)


# ── Fixtures ──────────────────────────────────────────────

@pytest.fixture
def scorer():
    return SideEffectScorer()


@pytest.fixture
def metformin_med():
    return {
        "name": "Metformin",
        "generic_name": "metformin",
        "dosage": "1000mg",
        "start_date": "2020-01-15",
        "end_date": None,
        "status": "active",
        "dose_changes": [
            {"date": "2021-06-01", "from_dose": "500mg", "to_dose": "1000mg"},
        ],
    }


@pytest.fixture
def gabapentin_med():
    return {
        "name": "Gabapentin",
        "generic_name": "gabapentin",
        "dosage": "300mg",
        "start_date": "2024-01-15",
        "end_date": None,
        "status": "active",
        "dose_changes": [],
    }


@pytest.fixture
def atorvastatin_med():
    return {
        "name": "Atorvastatin",
        "generic_name": "atorvastatin",
        "dosage": "40mg",
        "start_date": "2020-02-15",
        "end_date": None,
        "status": "active",
        "dose_changes": [
            {"date": "2022-01-10", "from_dose": "20mg", "to_dose": "40mg"},
        ],
    }


@pytest.fixture
def sample_medications(metformin_med, gabapentin_med, atorvastatin_med):
    return [metformin_med, gabapentin_med, atorvastatin_med]


@pytest.fixture
def sample_genetics():
    return [
        {
            "gene": "SLCO1B1",
            "variant": "rs4149056",
            "phenotype": "Poor Transporter",
            "clinical_significance": "Pathogenic",
        },
        {
            "gene": "CYP2D6",
            "variant": "*4/*4",
            "phenotype": "Poor Metabolizer",
            "clinical_significance": "Pathogenic",
        },
    ]


# ── Helper Function Tests ────────────────────────────────

class TestHelpers:

    def test_normalize_name(self):
        assert _normalize_name("Metformin") == "metformin"
        assert _normalize_name("  Gabapentin  ") == "gabapentin"
        assert _normalize_name("") == ""
        assert _normalize_name(None) == ""

    def test_find_side_effect_key_exact(self):
        assert _find_side_effect_key("metformin") == "metformin"
        assert _find_side_effect_key("Metformin") == "metformin"

    def test_find_side_effect_key_substring(self):
        assert _find_side_effect_key("metformin hcl") == "metformin"

    def test_find_side_effect_key_missing(self):
        assert _find_side_effect_key("totally_unknown_drug") is None
        assert _find_side_effect_key("") is None

    def test_symptom_matches(self):
        assert _symptom_matches("nausea", "nausea") is True
        assert _symptom_matches("Nausea", "nausea") is True
        assert _symptom_matches("muscle pain", "muscle pain") is True
        assert _symptom_matches("dizziness", "headache") is False

    def test_symptom_matches_partial(self):
        # "muscle pain" is contained in "muscle pain and stiffness"
        assert _symptom_matches("muscle pain", "muscle pain and stiffness") is True

    def test_parse_date_string(self):
        d = _parse_date("2024-03-15")
        assert d is not None
        assert d.year == 2024
        assert d.month == 3
        assert d.day == 15

    def test_parse_date_none(self):
        assert _parse_date(None) is None
        assert _parse_date("") is None

    def test_extract_dose_number(self):
        assert _extract_dose_number("500mg") == 500.0
        assert _extract_dose_number("1000mg") == 1000.0
        assert _extract_dose_number("24 units") == 24.0
        assert _extract_dose_number("2.5mg") == 2.5
        assert _extract_dose_number("") is None
        assert _extract_dose_number(None) is None


# ── Factor 1: Known Side Effect ──────────────────────────

class TestKnownSideEffect:

    def test_known_match(self, scorer, metformin_med):
        result = scorer._check_known_side_effect("Nausea", metformin_med)
        assert result["matched"] is True
        assert "common" in result["text"].lower()

    def test_known_no_match(self, scorer, metformin_med):
        result = scorer._check_known_side_effect("Hair loss", metformin_med)
        assert result["matched"] is False

    def test_unknown_medication(self, scorer):
        med = {"name": "TotallyUnknownDrug123", "generic_name": ""}
        result = scorer._check_known_side_effect("Nausea", med)
        assert result["matched"] is False
        assert "no side effect data" in result["text"].lower()

    def test_partial_symptom_match(self, scorer, atorvastatin_med):
        # "muscle" is a substring of "muscle pain"
        result = scorer._check_known_side_effect("muscle pain", atorvastatin_med)
        assert result["matched"] is True


# ── Factor 2: Temporal Relationship ──────────────────────

class TestTemporalRelationship:

    def test_symptom_after_med_start(self, scorer, metformin_med):
        episode = {"episode_date": "2020-06-01", "intensity": "mid"}
        result = scorer._check_temporal_relationship(episode, metformin_med)
        assert result["matched"] is True
        assert "days after" in result["text"]

    def test_symptom_before_med_start(self, scorer, metformin_med):
        episode = {"episode_date": "2019-12-01", "intensity": "mid"}
        result = scorer._check_temporal_relationship(episode, metformin_med)
        assert result["matched"] is False
        assert "before" in result["text"].lower()

    def test_symptom_after_dose_change(self, scorer, metformin_med):
        episode = {"episode_date": "2021-06-15", "intensity": "high"}
        result = scorer._check_temporal_relationship(episode, metformin_med)
        assert result["matched"] is True
        assert "dose change" in result["text"].lower()

    def test_missing_dates(self, scorer):
        med = {"name": "Test", "start_date": None}
        episode = {"episode_date": None}
        result = scorer._check_temporal_relationship(episode, med)
        assert result["matched"] is False
        assert "insufficient" in result["text"].lower()


# ── Factor 3: Dose-Response ──────────────────────────────

class TestDoseResponse:

    def test_dose_increase_correlates(self, scorer, atorvastatin_med):
        # Episode shortly after dose increased from 20mg to 40mg
        episode = {
            "episode_date": "2022-02-01",
            "intensity": "high",
        }
        result = scorer._check_dose_response(episode, atorvastatin_med)
        assert result["matched"] is True
        assert "20mg" in result["text"]
        assert "40mg" in result["text"]

    def test_no_dose_changes(self, scorer, gabapentin_med):
        episode = {"episode_date": "2024-06-01", "intensity": "mid"}
        result = scorer._check_dose_response(episode, gabapentin_med)
        assert result["matched"] is False
        assert "no dose changes" in result["text"].lower()

    def test_dose_change_too_long_ago(self, scorer, atorvastatin_med):
        # Episode 200+ days after dose change — outside 90-day window
        episode = {
            "episode_date": "2022-09-01",
            "intensity": "mid",
        }
        result = scorer._check_dose_response(episode, atorvastatin_med)
        assert result["matched"] is False

    def test_episode_before_dose_change(self, scorer, atorvastatin_med):
        # Episode before the dose change date
        episode = {
            "episode_date": "2021-12-01",
            "intensity": "high",
        }
        result = scorer._check_dose_response(episode, atorvastatin_med)
        assert result["matched"] is False


# ── Factor 4: Genetic Factors ────────────────────────────

class TestGeneticFactors:

    def test_slco1b1_statin_match(self, scorer, atorvastatin_med, sample_genetics):
        result = scorer._check_genetic_factors(atorvastatin_med, sample_genetics)
        assert result["matched"] is True
        assert "SLCO1B1" in result["text"]
        assert "myopathy" in result["text"].lower()

    def test_no_genetic_data(self, scorer, metformin_med):
        result = scorer._check_genetic_factors(metformin_med, [])
        assert result["matched"] is False
        assert "no genetic" in result["text"].lower()

    def test_no_matching_gene_drug_pair(self, scorer, gabapentin_med, sample_genetics):
        result = scorer._check_genetic_factors(gabapentin_med, sample_genetics)
        assert result["matched"] is False

    def test_cyp2d6_metoprolol_match(self, scorer, sample_genetics):
        med = {"name": "Metoprolol Succinate", "generic_name": "metoprolol succinate"}
        result = scorer._check_genetic_factors(med, sample_genetics)
        assert result["matched"] is True
        assert "CYP2D6" in result["text"]


# ── Factor 5: Alternative Explanations ───────────────────

class TestAlternativeExplanations:

    def test_no_alternatives(self, scorer, gabapentin_med, sample_medications):
        # "peripheral edema" is known for gabapentin but not for metformin or atorvastatin
        result = scorer._check_alternative_explanations(
            "peripheral edema", gabapentin_med, sample_medications
        )
        assert result["matched"] is True
        assert "no other" in result["text"].lower()

    def test_has_alternatives(self, scorer, metformin_med, sample_medications):
        # "nausea" is a side effect of both metformin and gabapentin
        result = scorer._check_alternative_explanations(
            "Nausea", metformin_med, sample_medications
        )
        assert result["matched"] is False
        assert "gabapentin" in result["text"].lower() or "atorvastatin" in result["text"].lower()

    def test_single_medication_no_alternatives(self, scorer, metformin_med):
        result = scorer._check_alternative_explanations(
            "Diarrhea", metformin_med, [metformin_med]
        )
        assert result["matched"] is True


# ── Full Episode Scoring ─────────────────────────────────

class TestScoreEpisode:

    def test_high_likelihood_episode(self, scorer, atorvastatin_med, sample_medications, sample_genetics):
        """Muscle pain + statin + SLCO1B1 + temporal match = high likelihood."""
        episode = {
            "episode_id": "ep1",
            "episode_date": "2022-02-01",  # after dose change
            "intensity": "high",
            "linked_medication_id": "Atorvastatin",
        }
        result = scorer.score_episode(
            "muscle pain", episode, atorvastatin_med, sample_medications, sample_genetics
        )
        assert result["likelihood"] in ("high", "very_high")
        assert result["matched_count"] >= 3
        assert result["total_factors"] == 5
        assert result["episode_id"] == "ep1"

    def test_low_likelihood_episode(self, scorer, gabapentin_med, sample_medications):
        """Unknown symptom + no dose change + no genetics + alternatives = low."""
        episode = {
            "episode_id": "ep2",
            "episode_date": "2019-01-01",  # before med start
            "intensity": "low",
        }
        result = scorer.score_episode(
            "hair loss", episode, gabapentin_med, sample_medications, []
        )
        assert result["likelihood"] == "low"
        assert result["matched_count"] <= 1

    def test_result_structure(self, scorer, metformin_med, sample_medications):
        episode = {
            "episode_id": "ep3",
            "episode_date": "2020-06-01",
            "intensity": "mid",
        }
        result = scorer.score_episode("Nausea", episode, metformin_med, sample_medications, [])
        assert "likelihood" in result
        assert "factors" in result
        assert len(result["factors"]) == 5
        assert "matched_count" in result
        assert "total_factors" in result
        assert result["total_factors"] == 5

        for f in result["factors"]:
            assert "name" in f
            assert "matched" in f
            assert "text" in f
            assert "source" in f


# ── Likelihood Thresholds ────────────────────────────────

class TestLikelihoodThresholds:

    def test_threshold_mapping(self):
        scorer = SideEffectScorer()
        assert scorer.LIKELIHOOD_THRESHOLDS[0] == "low"
        assert scorer.LIKELIHOOD_THRESHOLDS[1] == "low"
        assert scorer.LIKELIHOOD_THRESHOLDS[2] == "moderate"
        assert scorer.LIKELIHOOD_THRESHOLDS[3] == "high"
        assert scorer.LIKELIHOOD_THRESHOLDS[4] == "very_high"
        assert scorer.LIKELIHOOD_THRESHOLDS[5] == "very_high"


# ── Batch Scoring ────────────────────────────────────────

class TestBatchScoring:

    def test_score_all_linked_episodes(self, scorer, sample_medications, sample_genetics):
        symptoms = [
            {
                "symptom_name": "Muscle pain",
                "episodes": [
                    {
                        "episode_id": "e1",
                        "episode_date": "2022-03-01",
                        "intensity": "high",
                        "linked_medication_id": "Atorvastatin",
                    },
                    {
                        "episode_id": "e2",
                        "episode_date": "2024-05-01",
                        "intensity": "mid",
                        "linked_medication_id": None,  # not linked — should be skipped
                    },
                ],
            },
            {
                "symptom_name": "Nausea",
                "episodes": [
                    {
                        "episode_id": "e3",
                        "episode_date": "2020-03-01",
                        "intensity": "mid",
                        "linked_medication_id": "Metformin",
                    },
                ],
            },
        ]
        result = scorer.score_all_linked_episodes(symptoms, sample_medications, sample_genetics)

        assert "Atorvastatin" in result
        assert "Metformin" in result
        assert len(result["Atorvastatin"]) == 1  # only e1 (e2 has no linked_medication_id)
        assert len(result["Metformin"]) == 1

        # Verify scored episode structure
        scored = result["Atorvastatin"][0]
        assert scored["episode_id"] == "e1"
        assert scored["symptom_name"] == "Muscle pain"
        assert "likelihood" in scored

    def test_batch_empty_symptoms(self, scorer, sample_medications):
        result = scorer.score_all_linked_episodes([], sample_medications, [])
        assert result == {}

    def test_batch_no_linked_episodes(self, scorer, sample_medications):
        symptoms = [
            {
                "symptom_name": "Headache",
                "episodes": [
                    {"episode_id": "e1", "episode_date": "2024-01-01", "intensity": "low"},
                ],
            },
        ]
        result = scorer.score_all_linked_episodes(symptoms, sample_medications, [])
        assert result == {}

    def test_batch_unknown_medication(self, scorer, sample_medications):
        """Linked medication not in the medication list should be skipped with warning."""
        symptoms = [
            {
                "symptom_name": "Rash",
                "episodes": [
                    {
                        "episode_id": "e1",
                        "episode_date": "2024-01-01",
                        "intensity": "mid",
                        "linked_medication_id": "TotallyUnknownMed",
                    },
                ],
            },
        ]
        result = scorer.score_all_linked_episodes(symptoms, sample_medications, [])
        assert result == {}


# ── Static Data Coverage ─────────────────────────────────

class TestStaticDataCoverage:

    def test_common_side_effects_not_empty(self):
        assert len(COMMON_SIDE_EFFECTS) > 30

    def test_gene_drug_risk_not_empty(self):
        assert len(GENE_DRUG_RISK) > 10

    def test_metformin_has_key_side_effects(self):
        effects = COMMON_SIDE_EFFECTS.get("metformin", {})
        assert "nausea" in effects
        assert "diarrhea" in effects

    def test_statin_has_muscle_pain(self):
        for statin in ["atorvastatin", "rosuvastatin", "simvastatin"]:
            effects = COMMON_SIDE_EFFECTS.get(statin, {})
            assert "muscle pain" in effects, f"{statin} missing muscle pain"

    def test_gabapentin_has_dizziness(self):
        effects = COMMON_SIDE_EFFECTS.get("gabapentin", {})
        assert "dizziness" in effects
        assert "drowsiness" in effects
