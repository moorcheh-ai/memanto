"""Unit tests for live-roundtrip env loading and API key prerequisite checks."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from record_live_terminal import (
    _has_moorcheh_api_key,
    _is_configured_api_key,
    _is_placeholder_api_key,
    _load_env_file,
    _moorcheh_api_key_problem,
    _require_live_prerequisites,
    _strip_env_value,
)


@pytest.fixture(autouse=True)
def _isolate_moorcheh_env(monkeypatch, tmp_path_factory):
    monkeypatch.delenv("MOORCHEH_API_KEY", raising=False)
    # Keep ~/.memanto/.env on the developer machine from leaking into checks.
    isolated_home = tmp_path_factory.mktemp("home")
    monkeypatch.setattr(Path, "home", lambda: isolated_home)


def test_strip_env_value_removes_matching_quotes():
    assert _strip_env_value('  "abc"  ') == "abc"
    assert _strip_env_value("  'abc'  ") == "abc"
    assert _strip_env_value("plain") == "plain"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "your_api_key_here",
        "YOUR_API_KEY_HERE",
        '"your_api_key_here"',
        "your_key",
        "changeme",
        "replace_me",
        "xxx",
        "todo",
        "<your_api_key>",
        "none",
        "null",
    ],
)
def test_placeholder_api_keys_are_rejected(value):
    assert _is_placeholder_api_key(value) is True
    assert _is_configured_api_key(value) is False


def test_real_looking_api_key_is_configured():
    assert _is_configured_api_key("mch_live_abc123XYZ") is True
    assert _is_placeholder_api_key("mch_live_abc123XYZ") is False


def test_load_env_file_sets_local_values(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "MOORCHEH_API_KEY=mch_from_local_env\nOTHER_FLAG=1\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("OTHER_FLAG", raising=False)

    _load_env_file(env_path)

    assert os.environ["MOORCHEH_API_KEY"] == "mch_from_local_env"
    assert os.environ["OTHER_FLAG"] == "1"


def test_load_env_file_does_not_override_existing_process_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MOORCHEH_API_KEY", "mch_from_process")
    env_path = tmp_path / ".env"
    env_path.write_text("MOORCHEH_API_KEY=mch_from_file\n", encoding="utf-8")

    _load_env_file(env_path)

    assert os.environ["MOORCHEH_API_KEY"] == "mch_from_process"


def test_load_env_file_skips_placeholder_moorcheh_key(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "MOORCHEH_API_KEY=your_api_key_here\nKEEP_ME=yes\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("KEEP_ME", raising=False)

    _load_env_file(env_path)

    assert "MOORCHEH_API_KEY" not in os.environ
    assert os.environ["KEEP_ME"] == "yes"


def test_has_moorcheh_api_key_rejects_process_placeholder(monkeypatch):
    monkeypatch.setenv("MOORCHEH_API_KEY", "your_api_key_here")
    assert _has_moorcheh_api_key() is False


def test_has_moorcheh_api_key_accepts_process_key(monkeypatch):
    monkeypatch.setenv("MOORCHEH_API_KEY", "mch_process_ok")
    assert _has_moorcheh_api_key() is True


def test_has_moorcheh_api_key_reads_memanto_env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    memanto = home / ".memanto"
    memanto.mkdir(parents=True)
    (memanto / ".env").write_text(
        "MOORCHEH_API_KEY=mch_from_memanto\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    assert _has_moorcheh_api_key() is True


def test_has_moorcheh_api_key_rejects_memanto_placeholder(tmp_path, monkeypatch):
    home = tmp_path / "home"
    memanto = home / ".memanto"
    memanto.mkdir(parents=True)
    (memanto / ".env").write_text(
        'MOORCHEH_API_KEY="your_api_key_here"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    assert _has_moorcheh_api_key() is False


def test_moorcheh_api_key_problem_mentions_placeholder_without_value(monkeypatch):
    monkeypatch.setenv("MOORCHEH_API_KEY", "your_api_key_here")
    message = _moorcheh_api_key_problem()
    assert message is not None
    assert "MOORCHEH_API_KEY is not set" in message
    assert "your_api_key_here" in message
    assert "mch_" not in message
    assert "never prints the key value" in message


def test_require_live_prerequisites_fails_fast_on_placeholder(monkeypatch):
    monkeypatch.setenv("MOORCHEH_API_KEY", "your_api_key_here")

    with pytest.raises(RuntimeError, match="MOORCHEH_API_KEY is not set") as excinfo:
        _require_live_prerequisites(
            check_example_venv=False,
            check_repo_venv=False,
            check_ffmpeg=False,
        )

    text = str(excinfo.value)
    assert "your_api_key_here" in text
    assert "never prints the key value" in text
    # Must not echo the configured env value beyond the known placeholder name in docs.
    assert "MOORCHEH_API_KEY=your_api_key_here" not in text


def test_require_live_prerequisites_passes_when_key_configured(monkeypatch):
    monkeypatch.setenv("MOORCHEH_API_KEY", "mch_live_test_key")
    _require_live_prerequisites(
        check_example_venv=False,
        check_repo_venv=False,
        check_ffmpeg=False,
    )


def test_load_then_has_key_rejects_copied_env_example(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    env_path = tmp_path / ".env"
    env_path.write_text("MOORCHEH_API_KEY=your_api_key_here\n", encoding="utf-8")

    _load_env_file(env_path)

    assert _has_moorcheh_api_key() is False
    assert _moorcheh_api_key_problem() is not None
