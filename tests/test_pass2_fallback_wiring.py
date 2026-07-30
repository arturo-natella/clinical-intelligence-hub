"""Regression coverage for the privacy-gated, spend-bounded Pass 2 path."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from src.models import Medication, PatientProfile, Provenance


def test_fallback_chunking_processes_all_redacted_text():
    from src.analysis.gemini_fallback import GeminiFallback

    text = "0123456789" * 7
    chunks = GeminiFallback.chunk_redacted_text(text, chunk_chars=13)

    assert "".join(chunks) == text
    assert all(0 < len(chunk) <= 13 for chunk in chunks)


def test_completed_empty_local_extraction_becomes_fallback_candidate(
    monkeypatch, tmp_path,
):
    import src.ui.pipeline as pipeline_module

    class EmptyExtractor:
        def __init__(self, **kwargs):
            pass

        def count_chunks(self, pages):
            return 1

        def extract(self, pages, source_file, start_chunk=0):
            return {
                "medications": [], "labs": [], "diagnoses": [],
                "procedures": [], "allergies": [], "genetics": [],
                "notes": [],
            }

    monkeypatch.setitem(
        sys.modules,
        "src.extraction.text_extractor",
        SimpleNamespace(TextExtractor=EmptyExtractor),
    )

    pipeline = pipeline_module.Pipeline(tmp_path, "passphrase")
    pipeline._profile = PatientProfile()
    pipeline._db = SimpleNamespace(
        get_file_state=lambda file_id: {
            "text_chunks_completed": 1,
            "text_chunks_total": 1,
        },
        update_text_checkpoint=lambda *args: None,
    )

    raw_text = "Clinical narrative with no structured result. " * 3
    pipeline._pass_1a_text_extraction([{
        "file_id": "file-1",
        "filename": "record.pdf",
        "file_type": "pdf_text",
        "text": raw_text,
        "pages": [{"page": 1, "text": raw_text}],
    }])

    assert pipeline._local_processing_errors == []
    assert pipeline._fallback_candidates == [{
        "source_file": "record.pdf",
        "text": raw_text,
    }]


def test_redaction_prepares_only_whole_documents_inside_spend_caps(monkeypatch, tmp_path):
    import src.privacy.redactor as redactor_module
    import src.ui.pipeline as pipeline_module

    class FakeRedactor:
        def __init__(self, db=None):
            self.db = db
            self._presidio_available = True

        def redact_dict(self, data, source_file="unknown"):
            return data

        def redact(self, text, source_file="unknown"):
            return text.replace("Jane Doe", "[NAME_REDACTED]")

        def get_redaction_summary(self):
            return {"total": 1}

    monkeypatch.setattr(redactor_module, "PIIRedactor", FakeRedactor)
    monkeypatch.setattr(pipeline_module, "GEMINI_FALLBACK_MAX_DOCUMENTS", 2)
    monkeypatch.setattr(pipeline_module, "GEMINI_FALLBACK_MAX_DOCUMENT_CHARS", 30)

    pipeline = pipeline_module.Pipeline(tmp_path, "passphrase")
    pipeline._profile = PatientProfile(
        clinical_timeline={
            "medications": [Medication(
                name="Metformin",
                provenance=Provenance(source_file="Jane_Doe_record.pdf"),
            )],
        },
    )
    pipeline._fallback_candidates = [
        {"source_file": "Jane_Doe_record.pdf", "text": "Jane Doe takes metformin"},
        {"source_file": "oversized.pdf", "text": "x" * 31},
        {"source_file": "over-run-cap.pdf", "text": "short"},
    ]

    assert pipeline._pass_1_5_redaction() is True
    assert len(pipeline._redacted_fallback_documents) == 1
    prepared = pipeline._redacted_fallback_documents[0]
    assert prepared["redacted_text"] == "[NAME_REDACTED] takes metformin"
    assert prepared["source_file"] == "Jane_Doe_record.pdf"
    assert (
        pipeline._redacted_profile_dict["clinical_timeline"]["medications"][0]
        ["provenance"]["source_file"]
    ) == "[LOCAL_SOURCE_REDACTED]"


def test_raw_document_fallback_is_blocked_without_presidio(monkeypatch, tmp_path):
    import src.privacy.redactor as redactor_module
    import src.ui.pipeline as pipeline_module

    class RegexOnlyRedactor:
        _presidio_available = False

        def __init__(self, db=None):
            pass

    monkeypatch.setattr(redactor_module, "PIIRedactor", RegexOnlyRedactor)

    pipeline = pipeline_module.Pipeline(tmp_path, "passphrase")
    pipeline._profile = PatientProfile()
    pipeline._fallback_candidates = [{
        "source_file": "record.pdf",
        "text": "Jane Doe has a clinical record",
    }]

    assert pipeline._pass_1_5_redaction() is False
    assert pipeline._redacted_profile_dict is None
    assert pipeline._redacted_fallback_documents == []
    assert pipeline._local_processing_errors == [
        "PII redaction failed (RuntimeError)"
    ]


def test_cloud_fallback_merges_chunk_results_before_later_analysis(
    monkeypatch, tmp_path,
):
    import src.ui.pipeline as pipeline_module

    extracted_chunks = []
    deep_summaries = []

    class FakeFallback:
        def __init__(self, api_key):
            assert api_key == "gemini-key"

        @staticmethod
        def chunk_redacted_text(text, chunk_chars):
            return [text[index:index + chunk_chars] for index in range(0, len(text), chunk_chars)]

        def extract(self, redacted_text, source_file):
            extracted_chunks.append(redacted_text)
            return {
                "medications": [Medication(
                    name="Metformin",
                    provenance=Provenance(
                        source_file=source_file,
                        extraction_model="gemini-3-flash-preview",
                    ),
                )],
            }

    class FakeDeepResearch:
        def __init__(self, api_key):
            assert api_key == "gemini-key"

        def analyze(self, profile_summary, queries):
            deep_summaries.append(json.loads(profile_summary))
            return {"connections": [], "flags": [], "literature": []}

    class FakeCommunity:
        def __init__(self, api_key):
            pass

        def search(self, medications, diagnoses):
            return []

    monkeypatch.setitem(
        sys.modules,
        "src.analysis.gemini_fallback",
        SimpleNamespace(GeminiFallback=FakeFallback),
    )
    monkeypatch.setitem(
        sys.modules,
        "src.analysis.deep_research",
        SimpleNamespace(DeepResearch=FakeDeepResearch),
    )
    monkeypatch.setitem(
        sys.modules,
        "src.analysis.community_insights",
        SimpleNamespace(CommunityInsights=FakeCommunity),
    )
    monkeypatch.setattr(pipeline_module, "GEMINI_FALLBACK_CHUNK_CHARS", 4)

    pipeline = pipeline_module.Pipeline(tmp_path, "passphrase")
    pipeline._profile = PatientProfile()
    pipeline._vault = SimpleNamespace(
        get_api_key=lambda provider: "gemini-key" if provider == "gemini" else None
    )
    pipeline._redacted_profile_dict = {"clinical_timeline": {}, "analysis": {}}
    pipeline._redacted_fallback_documents = [{
        "source_file": "Jane_Doe_record.pdf",
        "redacted_text": "abcdefghij",
    }]
    pipeline._redactor = SimpleNamespace(redact_dict=lambda data, source_file: data)
    pipeline._publish_profile_snapshot = lambda: None

    pipeline._pass_2_4_cloud_analysis()

    assert extracted_chunks == ["abcd", "efgh", "ij"]
    assert [med.name for med in pipeline._profile.clinical_timeline.medications] == [
        "Metformin"
    ]
    cloud_med = deep_summaries[0]["clinical_timeline"]["medications"][0]
    assert cloud_med["name"] == "Metformin"
    assert cloud_med["provenance"]["source_file"] == "[LOCAL_SOURCE_REDACTED]"


def test_cloud_analysis_never_falls_back_to_raw_profile(tmp_path):
    from src.ui.pipeline import Pipeline

    pipeline = Pipeline(tmp_path, "passphrase")
    pipeline._profile = PatientProfile()
    pipeline._vault = SimpleNamespace(get_api_key=lambda provider: "gemini-key")
    pipeline._redacted_profile_dict = None

    pipeline._pass_2_4_cloud_analysis()

    assert pipeline._profile.clinical_timeline.medications == []
