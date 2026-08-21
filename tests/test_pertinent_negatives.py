"""Pertinent negatives must not become stored diagnoses (2026-08-18 fix).

An uploaded record's "Pertinent Negatives" table (conditions the provider
explicitly ruled out) was imported wholesale as Active conditions: neither
extraction prompt had a negation vocabulary, and no storage path filtered
negated findings before they reached the conditions list. These tests pin
the fix: a shared "Ruled out" status vocabulary in src/models.py, a
storage-time guard at the pipeline's single append choke point, prompt
instructions in both extraction lanes, and visit-prep status hardening.

Also pins the separate date bug found in the same report: bare YYYY-MM-DD
strings parsed with `new Date()` render one calendar day early in US
timezones.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from src.models import PatientProfile, is_negated_status
from src.ui.pipeline import Pipeline
from src.analysis.visit_prep import VisitPrepGenerator

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_JS = REPO_ROOT / "src" / "ui" / "static" / "app.js"


# ── Negated-status vocabulary ───────────────────────────────

def test_negated_status_vocabulary_recognizes_ruled_out_variants():
    """Canonical negations — unambiguous whatever the diagnosis is."""
    for status in (
        "Ruled out",
        "ruled-out",
        "RULED OUT",
        "Ruled out (10/07/2025)",
        "Denied",
        "Negative",
        "Refuted",
        "Pertinent negative",
        "Pertinent negatives",
        "Not present",
        "Absent",
    ):
        assert is_negated_status(status), status


def test_negated_status_vocabulary_keeps_real_statuses():
    for status in ("Active", "Chronic", "Resolved", "", None):
        assert not is_negated_status(status), repr(status)


# ── Cue phrases negate only their own diagnosis ─────────────

def test_cue_phrase_negates_when_its_object_is_the_diagnosis():
    """A model echoing the record's cue phrase instead of "Ruled out"
    still counts — but only when the phrase is about THIS condition."""
    for status, name in (
        ("Negative for diabetes", "Diabetes mellitus type 2"),
        ("No history of asthma", "Asthma"),
        ("Denies chest pain", "Chest pain"),
        ("No evidence of malignancy", "Malignancy"),
    ):
        assert is_negated_status(status, name), f"{status!r} / {name!r}"


def test_cue_phrase_is_inert_without_a_diagnosis_name():
    """Without the name there is no way to tell a pertinent negative from
    an oncology surveillance status, and the safe answer is to keep the
    diagnosis: a missed negative is visible and correctable, a deleted
    condition is neither."""
    for status in (
        "Negative for diabetes",
        "No history of asthma",
        "Denies chest pain",
        "No evidence of malignancy",
    ):
        assert not is_negated_status(status), status


def test_surveillance_statuses_never_delete_a_real_condition():
    """THE dangerous direction. "No evidence of disease" (NED) and
    "negative for recurrence" are standard oncology surveillance statuses
    on a cancer the patient definitively HAS. Reading them as negations
    erases a cancer history, and PHI-safe logging records only a count —
    so the loss is both unrecoverable and invisible."""
    for status, name in (
        ("No evidence of disease", "Breast cancer, left"),
        ("No evidence of disease", "Coronary artery disease"),
        ("Negative for recurrence", "Stage II colon adenocarcinoma"),
        ("No history of recurrence", "Hodgkin lymphoma"),
        ("No evidence of metastasis", "Melanoma"),
        ("No history available", "Hypertension"),
        ("Denies adherence", "Hypertension"),
        ("Negative for diabetes, positive for prediabetes", "Prediabetes"),
    ):
        assert not is_negated_status(status, name), f"{status!r} / {name!r}"


# ── Storage guard at the pipeline choke point ───────────────

def _bare_pipeline():
    """Pipeline with only the state _append_extraction_results touches."""
    pipeline = Pipeline.__new__(Pipeline)
    pipeline._profile = PatientProfile()
    return pipeline


def _dx(name, status):
    return {
        "name": name,
        "status": status,
        "provenance": {"source_file": "test.pdf"},
    }


def test_append_extraction_results_drops_ruled_out_diagnoses():
    """The Aug 2026 defect: a 'Pertinent Negatives' table row must not be
    stored as a condition, whichever extraction lane produced it."""
    pipeline = _bare_pipeline()
    pipeline._append_extraction_results({
        "diagnoses": [
            _dx("Diabetes mellitus", "Ruled out"),
            _dx("Malignant hyperthermia due to anesthesia", "ruled-out"),
            _dx("Asthma", "Active"),
        ],
    })
    stored = [d.name for d in pipeline._profile.clinical_timeline.diagnoses]
    assert stored == ["Asthma"]


def test_append_extraction_results_keeps_oncology_surveillance_diagnoses():
    """The guard is a permanent `continue` at the only diagnoses write
    path, so a false positive destroys a real condition with no undo.
    Surveillance statuses must survive it."""
    pipeline = _bare_pipeline()
    pipeline._append_extraction_results({
        "diagnoses": [
            _dx("Breast cancer, left", "No evidence of disease"),
            _dx("Stage II colon adenocarcinoma", "Negative for recurrence"),
            _dx("Prediabetes", "Negative for diabetes, positive for prediabetes"),
            _dx("Hypertension", "No history available"),
            _dx("Pulmonary embolism", "Ruled out"),
            _dx("Asthma", "Active"),
        ],
    })
    stored = [d.name for d in pipeline._profile.clinical_timeline.diagnoses]
    assert stored == [
        "Breast cancer, left",
        "Stage II colon adenocarcinoma",
        "Prediabetes",
        "Hypertension",
        "Asthma",
    ]


def test_append_extraction_results_drops_cue_phrase_negatives_for_their_own_condition():
    """A model echoing the record's cue phrase is still a pertinent
    negative when the phrase names this very condition."""
    pipeline = _bare_pipeline()
    pipeline._append_extraction_results({
        "diagnoses": [
            _dx("Diabetes mellitus type 2", "Negative for diabetes"),
            _dx("Asthma", "No history of asthma"),
            _dx("Hyperlipidemia", "Active"),
        ],
    })
    stored = [d.name for d in pipeline._profile.clinical_timeline.diagnoses]
    assert stored == ["Hyperlipidemia"]


def test_append_extraction_results_keeps_normal_statuses():
    pipeline = _bare_pipeline()
    pipeline._append_extraction_results({
        "diagnoses": [
            _dx("Hyperlipidemia", "Active"),
            _dx("Pneumonia", "Resolved"),
            _dx("Hypertension", "Chronic"),
            _dx("Migraine", None),
        ],
    })
    assert len(pipeline._profile.clinical_timeline.diagnoses) == 4


# ── Extraction prompts teach the negation vocabulary ────────

def test_medgemma_prompt_teaches_ruled_out():
    from src.extraction.text_extractor import TextExtractor

    prompt = TextExtractor._build_prompt(
        TextExtractor.__new__(TextExtractor), "sample text"
    )
    assert "Ruled out" in prompt
    assert "Pertinent Negatives" in prompt


def test_gemini_fallback_prompt_teaches_ruled_out():
    from src.analysis.gemini_fallback import GeminiFallback

    prompt = GeminiFallback._build_extraction_prompt(
        GeminiFallback.__new__(GeminiFallback), "sample text", None
    )
    assert "Ruled out" in prompt
    assert "Pertinent Negatives" in prompt


# ── Visit prep status handling ──────────────────────────────

def test_visit_prep_null_status_counts_as_active_without_crashing():
    """A present-but-null status (the model's default) used to raise
    AttributeError and 500 the /api/visit-prep endpoint."""
    conditions = VisitPrepGenerator()._active_conditions(
        {"diagnoses": [{"name": "Anemia", "status": None}]}
    )
    assert [c["name"] for c in conditions] == ["Anemia"]
    assert conditions[0]["status"] == "active"


def test_visit_prep_excludes_ruled_out_status():
    """Regression pin: the inclusion filter must keep excluding negated
    statuses if its semantics ever change."""
    conditions = VisitPrepGenerator()._active_conditions(
        {"diagnoses": [
            {"name": "Epilepsy", "status": "Ruled out"},
            {"name": "Asthma", "status": "Active"},
        ]}
    )
    assert [c["name"] for c in conditions] == ["Asthma"]


def test_visit_prep_null_lab_flag_does_not_crash():
    """Same 500 as the null diagnosis status: a lab whose flag is null
    (the model default) hit None.lower() in _flagged_labs."""
    flagged = VisitPrepGenerator()._flagged_labs(
        {"labs": [{"name": "TSH", "flag": None, "value": 2.1}]}
    )
    assert flagged == []


# ── formatDate local-day rendering (app.js) ─────────────────

@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
class TestFormatDate:
    """Run the real formatDate from app.js under a US timezone."""

    @staticmethod
    def _format_date(value):
        source = APP_JS.read_text()
        match = re.search(r"function formatDate\(dateStr\) \{.*?\n\}", source, re.DOTALL)
        assert match, "formatDate not found in app.js"
        script = (
            "function escapeHtml(s) { return s; }\n"
            + match.group(0)
            + f"\nprocess.stdout.write(formatDate({value!r}));"
        )
        result = subprocess.run(
            ["node", "-e", script],
            capture_output=True,
            text=True,
            env={**os.environ, "TZ": "America/New_York"},
        )
        assert result.returncode == 0, result.stderr
        return result.stdout

    def test_bare_iso_date_renders_same_calendar_day(self):
        """The off-by-one: '2025-10-07' rendered as 'Oct 6, 2025' in US zones."""
        assert self._format_date("2025-10-07") == "Oct 7, 2025"

    def test_full_timestamp_still_renders_local_day(self):
        assert self._format_date("2025-10-07T15:30:00") == "Oct 7, 2025"

    def test_empty_value_renders_em_dash(self):
        assert self._format_date("") == "—"

    def test_impossible_calendar_date_renders_raw_string(self):
        """A malformed extracted date must stay visibly wrong, not be
        silently normalized into a credible-looking clinical date."""
        assert self._format_date("2025-02-30") == "2025-02-30"
        assert self._format_date("2025-13-05") == "2025-13-05"
