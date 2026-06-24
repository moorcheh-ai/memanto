"""Tests for the shared hook plumbing (schema-tolerant transcript reading)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_HOOKS_DIR = Path(__file__).resolve().parent.parent / "hooks"


def _load_common():
    spec = importlib.util.spec_from_file_location(
        "_memanto_hook_common", _HOOKS_DIR / "_common.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["_memanto_hook_common"] = module
    spec.loader.exec_module(module)
    return module


common = _load_common()


class TestDetectSkill:
    def test_detects_leading_slash_skill(self) -> None:
        assert common.detect_skill("/tdd write tests for auth") == "tdd"

    def test_detects_hyphenated_skill(self) -> None:
        assert (
            common.detect_skill("please run /grill-with-docs now") == "grill-with-docs"
        )

    def test_returns_none_without_skill(self) -> None:
        assert common.detect_skill("just a normal prompt") is None

    def test_file_paths_are_not_skills(self) -> None:
        # Path-like tokens must not be mistaken for skill invocations.
        assert common.detect_skill("/usr/local/bin has the binary") is None
        assert common.detect_skill("look at /tmp/foo.txt please") is None

    def test_skill_followed_by_path_argument(self) -> None:
        assert common.detect_skill("/tdd write tests for src/auth.py") == "tdd"

    def test_handles_empty(self) -> None:
        assert common.detect_skill("") is None
        assert common.detect_skill(None) is None


class TestReadHookInput:
    def test_parses_valid_json(self, monkeypatch) -> None:
        import io

        monkeypatch.setattr("sys.stdin", io.StringIO('{"prompt":"hi"}'))
        assert common.read_hook_input() == {"prompt": "hi"}

    def test_malformed_returns_empty(self, monkeypatch) -> None:
        import io

        monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
        assert common.read_hook_input() == {}


class TestReadTranscriptText:
    def test_missing_path_returns_empty(self) -> None:
        assert common.read_transcript_text(None) == ""
        assert common.read_transcript_text("/no/such/file.jsonl") == ""

    def test_reads_string_content(self, tmp_path: Path) -> None:
        f = tmp_path / "t.jsonl"
        lines = [
            {"message": {"role": "user", "content": "/tdd add tests"}},
            {"message": {"role": "assistant", "content": "Using Vitest."}},
        ]
        f.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
        text = common.read_transcript_text(str(f))
        assert "Vitest" in text
        assert "tdd" in text

    def test_reads_block_content(self, tmp_path: Path) -> None:
        f = tmp_path / "t.jsonl"
        entry = {
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "We use CQRS."},
                    {"type": "tool_use", "name": "Bash"},
                ],
            }
        }
        f.write_text(json.dumps(entry), encoding="utf-8")
        text = common.read_transcript_text(str(f))
        assert "CQRS" in text
        assert "Bash" not in text  # tool blocks are skipped

    def test_skips_malformed_lines(self, tmp_path: Path) -> None:
        f = tmp_path / "t.jsonl"
        f.write_text(
            'garbage\n{"message":{"role":"user","content":"real line"}}\n',
            encoding="utf-8",
        )
        assert "real line" in common.read_transcript_text(str(f))

    def test_truncates_to_max_chars(self, tmp_path: Path) -> None:
        f = tmp_path / "t.jsonl"
        big = {"message": {"role": "user", "content": "x" * 50000}}
        f.write_text(json.dumps(big), encoding="utf-8")
        assert len(common.read_transcript_text(str(f), max_chars=1000)) <= 1000


class TestReadTranscriptForDistillation:
    def test_returns_skill_and_text_on_short_transcript(self, tmp_path: Path) -> None:
        f = tmp_path / "t.jsonl"
        lines = [
            {"message": {"role": "user", "content": "/tdd add tests for auth"}},
            {"message": {"role": "assistant", "content": "Using Vitest."}},
        ]
        f.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
        skill, text = common.read_transcript_for_distillation(str(f))
        assert skill == "tdd"
        assert "Vitest" in text

    def test_recovers_skill_when_opener_is_outside_tail(self, tmp_path: Path) -> None:
        """Regression: long sessions must still tag with the opening skill.

        The user invokes ``/grill-with-docs`` at the very start. After many
        intermediate messages the opening prompt falls outside ``max_chars``,
        but the persisted memories must still be tagged ``skill:grill-with-docs``,
        not ``skill:unknown``.
        """
        f = tmp_path / "t.jsonl"
        opener = {
            "message": {
                "role": "user",
                "content": "/grill-with-docs let's nail down the orders service",
            }
        }
        # Filler dominates the tail and pushes the opener outside max_chars.
        filler = [
            {"message": {"role": "assistant", "content": "x" * 500}} for _ in range(40)
        ]
        decision = {
            "message": {
                "role": "user",
                "content": "We decided on CQRS for the Order domain.",
            }
        }
        all_lines = [opener, *filler, decision]
        f.write_text("\n".join(json.dumps(x) for x in all_lines), encoding="utf-8")

        skill, text = common.read_transcript_for_distillation(str(f), max_chars=2000)

        # Skill is recovered from BEFORE the truncation window.
        assert skill == "grill-with-docs"
        # The recent decision is in the truncated tail.
        assert "CQRS" in text
        # The opener has been truncated out — proving skill detection had to
        # scan beyond the returned text.
        assert "/grill-with-docs" not in text
        assert len(text) <= 2000

    def test_missing_path_returns_none_and_empty(self) -> None:
        assert common.read_transcript_for_distillation(None) == (None, "")
        assert common.read_transcript_for_distillation("/no/such/file") == (None, "")

    def test_no_skill_in_transcript_returns_none_skill(self, tmp_path: Path) -> None:
        f = tmp_path / "t.jsonl"
        entry = {"message": {"role": "user", "content": "just a chat, no skill"}}
        f.write_text(json.dumps(entry), encoding="utf-8")
        skill, text = common.read_transcript_for_distillation(str(f))
        assert skill is None
        assert "just a chat" in text
