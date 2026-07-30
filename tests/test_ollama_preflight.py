"""Regression tests: Ollama preflight must verify the MODEL, not just the daemon.

2026-04-15 incident: `_check_ollama()` returned True because the daemon
answered, but the MedGemma model wasn't pulled — 1,593 chunks then silently
404'd inside a broad `except`. The preflight must (a) distinguish "daemon
down" from "model missing", (b) surface a visible progress message either
way, and (c) chunk requests small enough that JSON output isn't truncated
(2026-03-13 incident: 24K-char chunks + 4096-token output budget).
"""

import json
import logging
import sys
from types import SimpleNamespace

import pytest

from src.extraction import text_extractor
from src.extraction.text_extractor import TextExtractor, MODEL_NAME, MAX_CHUNK_CHARS


class FakeOllama:
    """Stands in for the `ollama` module inside TextExtractor."""

    def __init__(self, installed_models=None, daemon_up=True):
        self._installed = installed_models if installed_models is not None else []
        self._daemon_up = daemon_up
        self.chat_calls = []
        self.response_content = "{}"

    def list(self):
        if not self._daemon_up:
            raise ConnectionError("connection refused")
        return SimpleNamespace(
            models=[SimpleNamespace(model=m) for m in self._installed]
        )

    def chat(self, **kwargs):
        self.chat_calls.append(kwargs)
        return {"message": {"content": self.response_content}}

    def generate(self, **kwargs):
        return {}


@pytest.fixture
def fake_ollama(monkeypatch):
    def _install(**kw):
        fake = FakeOllama(**kw)
        monkeypatch.setitem(sys.modules, "ollama", fake)
        return fake
    return _install


def _messages(progress_events):
    return " | ".join(str(e) for e in progress_events)


def test_preflight_passes_when_model_installed(fake_ollama):
    fake_ollama(installed_models=[MODEL_NAME])
    extractor = TextExtractor()
    assert extractor._available is True


def test_preflight_accepts_latest_tag_variant(fake_ollama):
    fake_ollama(installed_models=[f"{MODEL_NAME}:latest"])
    extractor = TextExtractor()
    assert extractor._available is True


def test_preflight_fails_when_daemon_up_but_model_missing(fake_ollama):
    fake_ollama(installed_models=["llama3:8b"])  # daemon fine, wrong model
    events = []
    extractor = TextExtractor(progress_callback=lambda *a: events.append(a))
    assert extractor._available is False
    combined = _messages(events)
    assert MODEL_NAME in combined          # names the missing model
    assert "ollama pull" in combined       # tells the user how to fix it


def test_preflight_fails_when_daemon_down(fake_ollama):
    fake_ollama(daemon_up=False)
    events = []
    extractor = TextExtractor(progress_callback=lambda *a: events.append(a))
    assert extractor._available is False
    combined = _messages(events).lower()
    assert "ollama" in combined            # visible message names the culprit
    assert "ollama pull" not in combined   # daemon-down ≠ model-missing remediation


def test_extract_emits_visible_skip_message_when_unavailable(fake_ollama):
    fake_ollama(installed_models=[])
    events = []
    extractor = TextExtractor(progress_callback=lambda *a: events.append(a))
    result = extractor.extract([{"page": 1, "text": "CBC panel"}], "labs.pdf")
    assert result == {}
    assert "skip" in _messages(events).lower()


def test_chunks_capped_at_12k_chars():
    pages = [{"page": i, "text": "x" * 5000} for i in range(1, 11)]  # 50K chars
    extractor = object.__new__(TextExtractor)  # no preflight needed
    chunks = extractor._build_chunks(pages)
    assert MAX_CHUNK_CHARS <= 12000
    assert all(len(text) <= 12000 + 100 for _pages, text in chunks)  # +margin for page headers


def test_output_token_budget_prevents_truncation(fake_ollama):
    fake = fake_ollama(installed_models=[MODEL_NAME])
    extractor = TextExtractor()
    extractor._extract_chunk("Hemoglobin 13.2 g/dL")
    assert fake.chat_calls, "expected an ollama.chat call"
    options = fake.chat_calls[0].get("options", {})
    assert options.get("num_predict", 0) >= 16384


def test_extraction_logs_only_metadata_not_record_or_response_phi(
    fake_ollama,
    caplog,
):
    """Record text, model content, and identifying filenames stay out of logs."""
    fake = fake_ollama(installed_models=[MODEL_NAME])
    record_secret = "PATIENT_RECORD_PHI_6f5f2d"
    response_secret = "MEDGEMMA_RESPONSE_PHI_b94a10"
    source_secret = "PATIENT_FILENAME_PHI_20c72a.pdf"
    fake.response_content = json.dumps({
        "medications": [],
        "labs": [],
        "diagnoses": [],
        "procedures": [],
        "allergies": [],
        "genetics": [],
        "notes": [{"summary": response_secret}],
    })
    progress_events = []
    extractor = TextExtractor(
        progress_callback=lambda *event: progress_events.append(event),
    )
    caplog.set_level(logging.DEBUG, logger="CIH-TextExtractor")

    result = extractor.extract(
        [{"page": 1, "text": record_secret}],
        source_secret,
    )

    rendered_output = "\n".join(
        [record.getMessage() for record in caplog.records]
        + [str(event) for event in progress_events]
    )
    assert record_secret not in rendered_output
    assert response_secret not in rendered_output
    assert source_secret not in rendered_output
    assert "characters=" in rendered_output
    assert result["notes"][0].summary == response_secret
    assert result["notes"][0].provenance.source_file == source_secret


def test_checkpoint_callback_failure_is_safe_and_stops_extraction(
    fake_ollama,
    caplog,
):
    """A failed durable write must stop without logging callback contents."""
    fake = fake_ollama(installed_models=[MODEL_NAME])
    callback_secret = "CHECKPOINT_CALLBACK_PHI_5dfe91"
    fake.response_content = json.dumps({
        "notes": [{"summary": "safe structured result"}],
    })

    def fail_chunk_callback(_delta):
        raise RuntimeError(callback_secret)

    checkpoint_events = []
    extractor = TextExtractor(
        on_chunk_complete=fail_chunk_callback,
        on_chunk_checkpoint=lambda completed, total: checkpoint_events.append(
            (completed, total)
        ),
    )
    caplog.set_level(logging.DEBUG, logger="CIH-TextExtractor")

    with pytest.raises(
        RuntimeError,
        match="checkpoint persistence failed",
    ):
        extractor.extract(
            [{"page": 1, "text": "safe test record"}],
            "source.pdf",
        )

    rendered_output = "\n".join(
        record.getMessage() for record in caplog.records
    )
    assert callback_secret not in rendered_output
    assert checkpoint_events == []


def test_extraction_resumes_after_last_checkpointed_chunk(fake_ollama):
    """Only chunks after the durable cursor should be sent to MedGemma."""
    fake = fake_ollama(installed_models=[MODEL_NAME])
    fake.response_content = json.dumps({
        "notes": [{"summary": "remaining chunk result"}],
    })
    checkpoint_events = []
    progress_events = []
    extractor = TextExtractor(
        progress_callback=lambda *event: progress_events.append(event),
        on_chunk_checkpoint=lambda completed, total: checkpoint_events.append(
            (completed, total)
        ),
    )
    pages = [
        {"page": page, "text": f"Page {page} " + ("x" * 5000)}
        for page in range(1, 4)
    ]

    assert extractor.count_chunks(pages) == 2
    result = extractor.extract(pages, "source.pdf", start_chunk=1)

    assert len(fake.chat_calls) == 1
    assert checkpoint_events == [(2, 2)]
    assert result["notes"][0].summary == "remaining chunk result"
    assert "Resuming text extraction after chunk 1/2" in _messages(
        progress_events
    )


def test_invalid_model_response_is_not_written_to_logs(fake_ollama, caplog):
    """Malformed MedGemma output may be diagnosed without logging its content."""
    fake = fake_ollama(installed_models=[MODEL_NAME])
    response_secret = "INVALID_RESPONSE_PHI_135c30"
    fake.response_content = f"not-json {response_secret}"
    progress_events = []
    extractor = TextExtractor(
        progress_callback=lambda *event: progress_events.append(event),
    )
    caplog.set_level(logging.DEBUG, logger="CIH-TextExtractor")

    assert extractor._extract_chunk("safe test input") is None

    rendered_output = "\n".join(
        [record.getMessage() for record in caplog.records]
        + [str(event) for event in progress_events]
    )
    assert response_secret not in rendered_output
    assert "invalid JSON" in rendered_output


def test_parse_failure_logs_exclude_clinical_item_values(caplog):
    """Pydantic failures must not echo the rejected clinical payload."""
    clinical_secret = "REJECTED_CLINICAL_PHI_a842d1"
    extractor = object.__new__(TextExtractor)
    results = extractor._empty_result()
    caplog.set_level(logging.DEBUG, logger="CIH-TextExtractor")

    extractor._merge_results(
        results,
        {
            "labs": [{
                "name": clinical_secret,
                "value": {"secret": clinical_secret},
            }],
        },
        "source.pdf",
        1,
    )

    rendered_output = "\n".join(
        record.getMessage() for record in caplog.records
    )
    assert clinical_secret not in rendered_output
    assert "Dropped lab item during parsing" in rendered_output
