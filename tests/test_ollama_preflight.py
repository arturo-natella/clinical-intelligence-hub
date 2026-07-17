"""Regression tests: Ollama preflight must verify the MODEL, not just the daemon.

2026-04-15 incident: `_check_ollama()` returned True because the daemon
answered, but the MedGemma model wasn't pulled — 1,593 chunks then silently
404'd inside a broad `except`. The preflight must (a) distinguish "daemon
down" from "model missing", (b) surface a visible progress message either
way, and (c) chunk requests small enough that JSON output isn't truncated
(2026-03-13 incident: 24K-char chunks + 4096-token output budget).
"""

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

    def list(self):
        if not self._daemon_up:
            raise ConnectionError("connection refused")
        return SimpleNamespace(
            models=[SimpleNamespace(model=m) for m in self._installed]
        )

    def chat(self, **kwargs):
        self.chat_calls.append(kwargs)
        return {"message": {"content": "{}"}}

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
