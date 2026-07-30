"""Contract tests for /api/system-health — the dashboard System Status card.

The endpoint must NEVER raise, never touch patient data, and always return the
six known checks with enum-bounded statuses, whatever is broken underneath.
"""

from types import SimpleNamespace

import pytest

from src.ui import app as app_module


VALID_STATUSES = {"ok", "warn", "fail", "unknown"}
EXPECTED_IDS = ["ollama", "medgemma_text", "medgemma_vision", "disk", "privacy", "vault"]


class _DownOllama:
    """Stub: daemon unreachable — every call explodes."""

    def list(self):  # noqa: A003 - mirrors ollama client API
        raise ConnectionError("connection refused")


class _UpOllama:
    def __init__(self, names):
        self._names = names

    def list(self):  # noqa: A003
        models = [SimpleNamespace(model=name) for name in self._names]
        return SimpleNamespace(models=models)


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(app_module, "_health_cache", {"at": 0.0, "payload": None})
    return app_module.app.test_client()


def _get_health(client, refresh=True):
    url = "/api/system-health" + ("?refresh=1" if refresh else "")
    resp = client.get(url)
    assert resp.status_code == 200
    return resp.get_json()


def _check_by_id(payload, check_id):
    matches = [c for c in payload["checks"] if c["id"] == check_id]
    assert len(matches) == 1, f"expected exactly one {check_id} check"
    return matches[0]


def test_contract_never_raises_even_when_everything_is_broken(client, monkeypatch):
    monkeypatch.setattr(app_module, "ollama", _DownOllama())

    def _boom(_path):
        raise OSError("disk exploded")

    monkeypatch.setattr(app_module.shutil, "disk_usage", _boom)

    payload = _get_health(client)

    assert [c["id"] for c in payload["checks"]] == EXPECTED_IDS
    for check in payload["checks"]:
        assert check["status"] in VALID_STATUSES
        assert isinstance(check["label"], str) and check["label"]
        assert isinstance(check["detail"], str)
        assert isinstance(check["hint"], str)
    assert payload["overall"] in VALID_STATUSES
    assert payload["checked_at"]


def test_daemon_down_marks_models_unknown_and_overall_fail(client, monkeypatch):
    monkeypatch.setattr(app_module, "ollama", _DownOllama())

    payload = _get_health(client)

    assert _check_by_id(payload, "ollama")["status"] == "fail"
    assert _check_by_id(payload, "medgemma_text")["status"] == "unknown"
    assert _check_by_id(payload, "medgemma_vision")["status"] == "unknown"
    assert payload["overall"] == "fail"


def test_model_detection_accepts_latest_variant(client, monkeypatch):
    monkeypatch.setattr(
        app_module,
        "ollama",
        _UpOllama([f"{app_module.TEXT_MODEL_NAME}:latest", app_module.VISION_MODEL_NAME]),
    )

    payload = _get_health(client)

    assert _check_by_id(payload, "ollama")["status"] == "ok"
    assert _check_by_id(payload, "medgemma_text")["status"] == "ok"
    assert _check_by_id(payload, "medgemma_vision")["status"] == "ok"


def test_missing_text_model_fails_missing_vision_model_warns(client, monkeypatch):
    monkeypatch.setattr(app_module, "ollama", _UpOllama(["some-other-model:7b"]))

    payload = _get_health(client)

    text_check = _check_by_id(payload, "medgemma_text")
    vision_check = _check_by_id(payload, "medgemma_vision")
    assert text_check["status"] == "fail"
    assert text_check["hint"]
    assert vision_check["status"] == "warn"
    assert payload["overall"] == "fail"


@pytest.mark.parametrize(
    ("free_gb", "expected"),
    [(500, "ok"), (30, "warn"), (5, "fail")],
)
def test_disk_thresholds(client, monkeypatch, free_gb, expected):
    monkeypatch.setattr(app_module, "ollama", _UpOllama([app_module.TEXT_MODEL_NAME]))

    def _usage(_path):
        gib = 1024 ** 3
        return SimpleNamespace(total=2000 * gib, used=0, free=free_gb * gib)

    monkeypatch.setattr(app_module.shutil, "disk_usage", _usage)

    assert _check_by_id(_get_health(client), "disk")["status"] == expected


def test_vault_locked_warns_unlocked_ok(client, monkeypatch):
    monkeypatch.setattr(app_module, "ollama", _UpOllama([app_module.TEXT_MODEL_NAME]))

    monkeypatch.setattr(app_module, "_passphrase", None)
    assert _check_by_id(_get_health(client), "vault")["status"] == "warn"

    monkeypatch.setattr(app_module, "_passphrase", "test-passphrase")
    assert _check_by_id(_get_health(client), "vault")["status"] == "ok"


def test_results_cached_until_refresh(client, monkeypatch):
    monkeypatch.setattr(app_module, "ollama", _UpOllama([app_module.TEXT_MODEL_NAME]))

    first = _get_health(client, refresh=True)
    # Underlying state flips, but the cache should still answer.
    monkeypatch.setattr(app_module, "ollama", _DownOllama())
    cached = _get_health(client, refresh=False)
    assert cached["checked_at"] == first["checked_at"]
    assert _check_by_id(cached, "ollama")["status"] == "ok"

    refreshed = _get_health(client, refresh=True)
    assert _check_by_id(refreshed, "ollama")["status"] == "fail"
