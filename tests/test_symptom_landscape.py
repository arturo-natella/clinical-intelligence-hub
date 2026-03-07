"""
Tests for Symptom Landscape — Phase 5

Tests cover:
  1. SymptomClassifier: body system classification accuracy
  2. SymptomClassifier: case-insensitive matching
  3. SymptomClassifier: multi-system ambiguity (picks best match)
  4. SymptomClassifier: "other" fallback for unknown symptoms
  5. SymptomAnalytics.detect_temporal_clusters: overlapping dates within window
  6. SymptomAnalytics.detect_temporal_clusters: configurable window size
  7. SymptomAnalytics.detect_temporal_clusters: empty symptoms list
  8. SymptomAnalytics.detect_temporal_clusters: single symptom (no clusters)
"""

import sys
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from src.analysis.symptom_classifier import SymptomClassifier, BODY_SYSTEM_LABELS
from src.analysis.symptom_analytics import SymptomAnalytics


# ── Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def classifier():
    return SymptomClassifier()


@pytest.fixture
def analytics():
    return SymptomAnalytics()


def _make_symptom(name, episodes=None):
    """Helper to create a symptom dict."""
    return {
        "symptom_id": f"test-{name.lower().replace(' ', '-')}",
        "symptom_name": name,
        "episodes": episodes or [],
    }


def _make_episode(date_str, intensity="mid", description=None, linked_medication_id=None):
    """Helper to create an episode dict."""
    ep = {
        "episode_id": f"ep-{date_str}",
        "episode_date": date_str,
        "intensity": intensity,
    }
    if description:
        ep["description"] = description
    if linked_medication_id:
        ep["linked_medication_id"] = linked_medication_id
    return ep


# ══════════════════════════════════════════════════════════════
# SymptomClassifier Tests
# ══════════════════════════════════════════════════════════════

class TestSymptomClassifier:
    """Test body system classification."""

    def test_gi_symptoms(self, classifier):
        """Known GI symptoms should classify as 'gi'."""
        assert classifier.classify("Nausea") == "gi"
        assert classifier.classify("Bloating") == "gi"
        assert classifier.classify("Diarrhea") == "gi"
        assert classifier.classify("Acid Reflux") == "gi"
        assert classifier.classify("Stomach Pain") == "gi"
        assert classifier.classify("Constipation") == "gi"

    def test_neurological_symptoms(self, classifier):
        """Known neurological symptoms should classify as 'neurological'."""
        assert classifier.classify("Headache") == "neurological"
        assert classifier.classify("Migraine") == "neurological"
        assert classifier.classify("Dizziness") == "neurological"
        assert classifier.classify("Numbness in hands") == "neurological"
        assert classifier.classify("Tremor") == "neurological"

    def test_musculoskeletal_symptoms(self, classifier):
        """Known musculoskeletal symptoms should classify as 'musculoskeletal'."""
        assert classifier.classify("Joint Pain") == "musculoskeletal"
        assert classifier.classify("Muscle Stiffness") == "musculoskeletal"
        assert classifier.classify("Back Pain") == "musculoskeletal"

    def test_mood_energy_symptoms(self, classifier):
        """Known mood/energy symptoms should classify as 'mood_energy'."""
        assert classifier.classify("Fatigue") == "mood_energy"
        assert classifier.classify("Anxiety") == "mood_energy"
        assert classifier.classify("Depression") == "mood_energy"

    def test_cardiovascular_symptoms(self, classifier):
        """Known cardiovascular symptoms should classify as 'cardiovascular'."""
        assert classifier.classify("Palpitations") == "cardiovascular"
        assert classifier.classify("Chest Pain") == "cardiovascular"
        assert classifier.classify("Shortness of Breath") == "cardiovascular"

    def test_sleep_symptoms(self, classifier):
        """Known sleep symptoms should classify as 'sleep'."""
        assert classifier.classify("Insomnia") == "sleep"
        assert classifier.classify("Sleep Apnea") == "sleep"
        assert classifier.classify("Vivid Dreams") == "sleep"

    def test_skin_symptoms(self, classifier):
        """Known skin symptoms should classify as 'skin'."""
        assert classifier.classify("Rash") == "skin"
        assert classifier.classify("Itching") == "skin"
        assert classifier.classify("Hair Loss") == "skin"
        assert classifier.classify("Dry Skin") == "skin"

    def test_case_insensitive(self, classifier):
        """Classification should be case-insensitive."""
        assert classifier.classify("NAUSEA") == "gi"
        assert classifier.classify("nausea") == "gi"
        assert classifier.classify("Nausea") == "gi"
        assert classifier.classify("HEADACHE") == "neurological"
        assert classifier.classify("headache") == "neurological"

    def test_unknown_symptom_returns_other(self, classifier):
        """Unknown symptoms should return 'other'."""
        assert classifier.classify("Mysterious symptom X") == "other"
        assert classifier.classify("Something weird") == "other"
        assert classifier.classify("Blinking rapidly") == "other"

    def test_empty_symptom_name(self, classifier):
        """Empty symptom name should return 'other'."""
        assert classifier.classify("") == "other"
        assert classifier.classify("   ") == "other"

    def test_description_helps_classify(self, classifier):
        """Description can help classify when name alone is ambiguous."""
        # "Pain" alone is too generic — returns "other"
        result_name_only = classifier.classify("Pain")
        assert result_name_only == "other"

        # With a stomach-related description, GI context wins
        result_with_desc = classifier.classify(
            "Pain",
            description="stomach cramping and nausea after eating"
        )
        assert result_with_desc == "gi"

        # With a joint-related description, musculoskeletal context wins
        result_joint = classifier.classify(
            "Pain",
            description="joint stiffness and muscle aches in the morning"
        )
        assert result_joint == "musculoskeletal"

    def test_multi_system_picks_best(self, classifier):
        """When a symptom matches multiple systems, the best match wins."""
        # "Brain fog" appears in both neurological and mood_energy
        # Both should be valid, but the classifier should pick one consistently
        result = classifier.classify("Brain Fog")
        assert result in ("neurological", "mood_energy")

    def test_classify_all(self, classifier):
        """classify_all should group symptoms by body system."""
        symptoms = [
            _make_symptom("Nausea"),
            _make_symptom("Headache"),
            _make_symptom("Fatigue"),
            _make_symptom("Joint Pain"),
            _make_symptom("Unknown Thing"),
        ]

        result = classifier.classify_all(symptoms)

        assert "gi" in result
        assert "neurological" in result
        assert "mood_energy" in result
        assert "musculoskeletal" in result
        assert "other" in result

        # Verify each group has the right symptoms
        gi_names = [s["symptom_name"] for s in result["gi"]]
        assert "Nausea" in gi_names

        neuro_names = [s["symptom_name"] for s in result["neurological"]]
        assert "Headache" in neuro_names

    def test_classify_all_adds_body_system_field(self, classifier):
        """classify_all should add body_system field to each symptom."""
        symptoms = [_make_symptom("Nausea"), _make_symptom("Headache")]
        result = classifier.classify_all(symptoms)

        for system, symptom_list in result.items():
            for s in symptom_list:
                assert "body_system" in s
                assert s["body_system"] == system

    def test_get_label(self):
        """get_label should return human-readable labels."""
        assert SymptomClassifier.get_label("gi") == "GI / Digestive"
        assert SymptomClassifier.get_label("neurological") == "Neurological"
        assert SymptomClassifier.get_label("unknown_key") == "Other"

    def test_get_all_systems(self):
        """get_all_systems should return all system labels."""
        systems = SymptomClassifier.get_all_systems()
        assert len(systems) == 8
        assert "gi" in systems
        assert "other" in systems


# ══════════════════════════════════════════════════════════════
# Temporal Cluster Detection Tests
# ══════════════════════════════════════════════════════════════

class TestTemporalClusters:
    """Test detect_temporal_clusters in SymptomAnalytics."""

    def test_empty_symptoms(self, analytics):
        """Empty symptoms list should return no clusters."""
        result = analytics.detect_temporal_clusters([])
        assert result == []

    def test_single_symptom_no_clusters(self, analytics):
        """A single symptom can never form a cluster (needs 2+ different symptoms)."""
        symptoms = [
            _make_symptom("Nausea", [
                _make_episode("2025-01-01"),
                _make_episode("2025-01-05"),
                _make_episode("2025-01-10"),
            ]),
        ]
        result = analytics.detect_temporal_clusters(symptoms)
        assert result == []

    def test_two_symptoms_within_window(self, analytics):
        """Two different symptoms with episodes within 14 days should form a cluster."""
        symptoms = [
            _make_symptom("Nausea", [
                _make_episode("2025-01-10"),
            ]),
            _make_symptom("Headache", [
                _make_episode("2025-01-12"),
            ]),
        ]
        result = analytics.detect_temporal_clusters(symptoms, window_days=14)
        assert len(result) == 1

        cluster = result[0]
        symptom_names = set(s["symptom_name"] for s in cluster["symptoms"])
        assert "Nausea" in symptom_names
        assert "Headache" in symptom_names

    def test_two_symptoms_outside_window(self, analytics):
        """Two symptoms with episodes far apart should NOT cluster."""
        symptoms = [
            _make_symptom("Nausea", [
                _make_episode("2025-01-01"),
            ]),
            _make_symptom("Headache", [
                _make_episode("2025-06-01"),  # 5 months later
            ]),
        ]
        result = analytics.detect_temporal_clusters(symptoms, window_days=14)
        assert len(result) == 0

    def test_configurable_window_size(self, analytics):
        """Window size should be configurable."""
        symptoms = [
            _make_symptom("Nausea", [
                _make_episode("2025-01-01"),
            ]),
            _make_symptom("Headache", [
                _make_episode("2025-01-10"),
            ]),
        ]

        # With 7-day window: 9 days apart, should NOT cluster
        result_narrow = analytics.detect_temporal_clusters(symptoms, window_days=7)
        assert len(result_narrow) == 0

        # With 14-day window: 9 days apart, SHOULD cluster
        result_wide = analytics.detect_temporal_clusters(symptoms, window_days=14)
        assert len(result_wide) == 1

    def test_cross_system_flag(self, analytics):
        """Cluster should flag cross_system when symptoms span 2+ body systems."""
        symptoms = [
            {
                "symptom_name": "Nausea",
                "body_system": "gi",
                "episodes": [_make_episode("2025-01-10")],
            },
            {
                "symptom_name": "Headache",
                "body_system": "neurological",
                "episodes": [_make_episode("2025-01-12")],
            },
        ]
        result = analytics.detect_temporal_clusters(symptoms, window_days=14)
        assert len(result) == 1
        assert result[0]["cross_system"] is True
        assert len(result[0]["body_systems_involved"]) == 2

    def test_same_system_not_cross(self, analytics):
        """Cluster with same body system should not be cross_system."""
        symptoms = [
            {
                "symptom_name": "Nausea",
                "body_system": "gi",
                "episodes": [_make_episode("2025-01-10")],
            },
            {
                "symptom_name": "Diarrhea",
                "body_system": "gi",
                "episodes": [_make_episode("2025-01-12")],
            },
        ]
        result = analytics.detect_temporal_clusters(symptoms, window_days=14)
        assert len(result) == 1
        assert result[0]["cross_system"] is False

    def test_attribution_status_all_unattributed(self, analytics):
        """All episodes without linked_medication_id -> all_unattributed."""
        symptoms = [
            _make_symptom("Nausea", [_make_episode("2025-01-10")]),
            _make_symptom("Headache", [_make_episode("2025-01-12")]),
        ]
        result = analytics.detect_temporal_clusters(symptoms, window_days=14)
        assert len(result) == 1
        assert result[0]["attribution_status"] == "all_unattributed"

    def test_attribution_status_all_attributed(self, analytics):
        """All episodes with linked_medication_id -> all_attributed."""
        symptoms = [
            _make_symptom("Nausea", [
                _make_episode("2025-01-10", linked_medication_id="Metformin"),
            ]),
            _make_symptom("Headache", [
                _make_episode("2025-01-12", linked_medication_id="Lisinopril"),
            ]),
        ]
        result = analytics.detect_temporal_clusters(symptoms, window_days=14)
        assert len(result) == 1
        assert result[0]["attribution_status"] == "all_attributed"

    def test_attribution_status_mixed(self, analytics):
        """Mix of attributed and unattributed -> mixed."""
        symptoms = [
            _make_symptom("Nausea", [
                _make_episode("2025-01-10", linked_medication_id="Metformin"),
            ]),
            _make_symptom("Headache", [
                _make_episode("2025-01-12"),
            ]),
        ]
        result = analytics.detect_temporal_clusters(symptoms, window_days=14)
        assert len(result) == 1
        assert result[0]["attribution_status"] == "mixed"

    def test_multiple_clusters(self, analytics):
        """Multiple separate time windows should produce multiple clusters."""
        symptoms = [
            _make_symptom("Nausea", [
                _make_episode("2025-01-10"),
                _make_episode("2025-06-10"),
            ]),
            _make_symptom("Headache", [
                _make_episode("2025-01-12"),
                _make_episode("2025-06-12"),
            ]),
        ]
        result = analytics.detect_temporal_clusters(symptoms, window_days=14)
        assert len(result) == 2

    def test_cluster_has_dates(self, analytics):
        """Each cluster should have window_start, window_end, cluster_center_date."""
        symptoms = [
            _make_symptom("Nausea", [_make_episode("2025-01-10")]),
            _make_symptom("Headache", [_make_episode("2025-01-12")]),
        ]
        result = analytics.detect_temporal_clusters(symptoms, window_days=14)
        assert len(result) == 1

        cluster = result[0]
        assert "cluster_center_date" in cluster
        assert "window_start" in cluster
        assert "window_end" in cluster
        assert cluster["window_start"] == "2025-01-10"
        assert cluster["window_end"] == "2025-01-12"

    def test_episodes_without_dates_are_skipped(self, analytics):
        """Episodes missing episode_date should be silently skipped."""
        symptoms = [
            _make_symptom("Nausea", [
                {"episode_id": "ep1", "intensity": "mid"},  # No date
                _make_episode("2025-01-10"),
            ]),
            _make_symptom("Headache", [
                _make_episode("2025-01-12"),
            ]),
        ]
        result = analytics.detect_temporal_clusters(symptoms, window_days=14)
        assert len(result) == 1
        # Should only have 2 episodes (the ones with dates)
        assert len(result[0]["symptoms"]) == 2

    def test_same_symptom_multiple_episodes_not_self_cluster(self, analytics):
        """Multiple episodes of the SAME symptom should NOT form a cluster alone."""
        symptoms = [
            _make_symptom("Nausea", [
                _make_episode("2025-01-10"),
                _make_episode("2025-01-11"),
                _make_episode("2025-01-12"),
            ]),
        ]
        result = analytics.detect_temporal_clusters(symptoms, window_days=14)
        assert len(result) == 0

    def test_window_days_zero_returns_empty(self, analytics):
        """Window of 0 days should return no clusters."""
        symptoms = [
            _make_symptom("Nausea", [_make_episode("2025-01-10")]),
            _make_symptom("Headache", [_make_episode("2025-01-10")]),
        ]
        result = analytics.detect_temporal_clusters(symptoms, window_days=0)
        assert result == []


# ══════════════════════════════════════════════════════════════
# BodySystem Enum Tests
# ══════════════════════════════════════════════════════════════

class TestBodySystemEnum:
    """Test the BodySystem enum in models.py."""

    def test_enum_values(self):
        from src.models import BodySystem

        assert BodySystem.GI.value == "gi"
        assert BodySystem.MUSCULOSKELETAL.value == "musculoskeletal"
        assert BodySystem.NEUROLOGICAL.value == "neurological"
        assert BodySystem.MOOD_ENERGY.value == "mood_energy"
        assert BodySystem.CARDIOVASCULAR.value == "cardiovascular"
        assert BodySystem.SLEEP.value == "sleep"
        assert BodySystem.SKIN.value == "skin"
        assert BodySystem.OTHER.value == "other"

    def test_symptom_episode_body_system_field(self):
        from src.models import SymptomEpisode

        # Default is None
        ep = SymptomEpisode()
        assert ep.body_system is None

        # Can be set
        ep2 = SymptomEpisode(body_system="gi")
        assert ep2.body_system == "gi"
