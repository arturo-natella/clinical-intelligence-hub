"""Contract for headless passphrase resolution in the monitoring scheduler.

install_monitors.sh stores the vault passphrase in the macOS Keychain
(service ``com.medprep.vault``); under launchd there is no TTY, so the
scheduler must read that Keychain entry itself. Resolution order:

    --passphrase arg  →  Keychain  →  interactive prompt (TTY only)  →  None

The passphrase value must never be logged or printed (security rule);
these tests use throwaway dummy strings only.
"""

import subprocess
import sys
from types import SimpleNamespace

import pytest

from src.monitoring import scheduler as sched


class _Result(SimpleNamespace):
    pass


def _fake_run(returncode=0, stdout=""):
    def run(cmd, **kwargs):
        run.last_cmd = cmd
        return _Result(returncode=returncode, stdout=stdout, stderr="")
    run.last_cmd = None
    return run


def test_cli_arg_wins_without_touching_keychain(monkeypatch):
    def explode(*a, **k):
        raise AssertionError("Keychain must not be queried when arg given")
    monkeypatch.setattr(subprocess, "run", explode)
    assert sched.resolve_passphrase("dummy-arg") == "dummy-arg"


def test_keychain_fallback_when_no_arg(monkeypatch):
    fake = _fake_run(returncode=0, stdout="dummy-keychain-pass\n")
    monkeypatch.setattr(subprocess, "run", fake)
    assert sched.resolve_passphrase(None) == "dummy-keychain-pass"
    # Must query the same service install_monitors.sh writes to.
    assert "find-generic-password" in fake.last_cmd
    assert "com.medprep.vault" in fake.last_cmd
    assert "-w" in fake.last_cmd


def test_returns_none_headless_when_keychain_empty(monkeypatch):
    # returncode 44 = errSecItemNotFound
    monkeypatch.setattr(subprocess, "run", _fake_run(returncode=44))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    assert sched.resolve_passphrase(None) is None


def test_missing_security_binary_is_not_fatal(monkeypatch):
    # Linux CI has no `security`; resolution must degrade, not raise.
    def raise_missing(*a, **k):
        raise FileNotFoundError("security")
    monkeypatch.setattr(subprocess, "run", raise_missing)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    assert sched.resolve_passphrase(None) is None


def test_tty_prompt_still_works(monkeypatch):
    import getpass
    monkeypatch.setattr(subprocess, "run", _fake_run(returncode=44))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": "dummy-typed")
    assert sched.resolve_passphrase(None) == "dummy-typed"


def test_main_exits_cleanly_when_unresolvable(monkeypatch, tmp_path):
    """Under launchd with no Keychain entry, main() must exit(1) with a
    pointer to the fix — not crash in getpass with an EOFError."""
    monkeypatch.setattr(subprocess, "run", _fake_run(returncode=44))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(
        sys, "argv",
        ["scheduler", "--mode", "api", "--data-dir", str(tmp_path)],
    )
    with pytest.raises(SystemExit) as exc:
        sched.main()
    assert exc.value.code == 1
