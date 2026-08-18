"""Tests for the shared hook plumbing (schema-tolerant transcript reading)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

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
        skill, text = common.read_transcript_for_distillation(
            str(f), last_assistant_message="Using Vitest."
        )
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
        answer = {
            "message": {
                "role": "assistant",
                "content": "Acknowledged the CQRS decision.",
            }
        }
        all_lines = [opener, *filler, decision, answer]
        f.write_text("\n".join(json.dumps(x) for x in all_lines), encoding="utf-8")

        skill, text = common.read_transcript_for_distillation(
            str(f),
            last_assistant_message="Acknowledged the CQRS decision.",
            max_chars=2000,
        )

        # Skill is recovered from BEFORE the truncation window.
        assert skill == "grill-with-docs"
        # The recent decision is in the truncated tail.
        assert "CQRS" in text
        # The opener has been truncated out — proving skill detection had to
        # scan beyond the returned text.
        assert "/grill-with-docs" not in text
        assert len(text) <= 2000

    def test_streams_transcript_without_requiring_readlines(self, monkeypatch) -> None:
        """Transcript reading must work with line-iterable files.

        Stop hooks can see very large JSONL transcripts. The reader should
        stream the file while locating the anchored turn instead of requiring
        ``readlines()`` to materialize the whole file before parsing.
        """
        lines = [
            json.dumps(
                {"message": {"role": "user", "content": "/tdd pin the parser bug"}}
            ),
            json.dumps(
                {
                    "message": {
                        "role": "assistant",
                        "content": "We will stream the transcript parser.",
                    }
                }
            ),
            json.dumps(
                {
                    "message": {
                        "role": "user",
                        "content": "Final decision: keep only the transcript tail.",
                    }
                }
            ),
            json.dumps(
                {
                    "message": {
                        "role": "assistant",
                        "content": "Confirmed the transcript tail decision.",
                    }
                }
            ),
        ]

        class StreamingOnlyFile:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def __iter__(self):
                return iter(lines)

            def readlines(self):  # pragma: no cover - old bug path
                raise AssertionError("readlines() should not be required")

        class FakePath:
            def __init__(self, raw):
                self.raw = raw

            def exists(self):
                return True

            def open(self, encoding=None):
                return StreamingOnlyFile()

        monkeypatch.setattr(common, "Path", FakePath)

        skill, text = common.read_transcript_for_distillation(
            "stream-only.jsonl",
            last_assistant_message="Confirmed the transcript tail decision.",
        )

        assert skill == "tdd"
        assert "Final decision" in text
        assert "Confirmed the transcript tail decision" in text
        assert "stream the transcript parser" not in text

    def test_missing_path_returns_none_and_empty(self) -> None:
        assert common.read_transcript_for_distillation(None) == (None, "")
        assert common.read_transcript_for_distillation("/no/such/file") == (None, "")

    def test_no_skill_in_transcript_returns_none_skill(self, tmp_path: Path) -> None:
        f = tmp_path / "t.jsonl"
        entries = [
            {"message": {"role": "user", "content": "just a chat, no skill"}},
            {"message": {"role": "assistant", "content": "A normal reply."}},
        ]
        f.write_text("\n".join(json.dumps(x) for x in entries), encoding="utf-8")
        skill, text = common.read_transcript_for_distillation(
            str(f), last_assistant_message="A normal reply."
        )
        assert skill is None
        assert "just a chat" in text

    def test_distills_only_the_latest_turn(self, tmp_path: Path) -> None:
        """A later Stop event must not re-submit an earlier turn."""
        f = tmp_path / "t.jsonl"
        lines = [
            {"message": {"role": "user", "content": "/tdd use unittest"}},
            {
                "message": {
                    "role": "assistant",
                    "content": "Old decision: use unittest.",
                }
            },
            {"message": {"role": "user", "content": "/diagnose inspect auth"}},
            {
                "message": {
                    "role": "assistant",
                    "content": "Current finding: tokens expire early.",
                }
            },
        ]
        f.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")

        skill, text = common.read_transcript_for_distillation(
            str(f), last_assistant_message="Current finding: tokens expire early."
        )

        assert skill == "diagnose"
        assert "tokens expire early" in text
        assert "Old decision" not in text
        assert "use unittest" not in text

    def test_assistant_anchor_excludes_a_later_appended_turn(
        self, tmp_path: Path
    ) -> None:
        """An async Stop hook must ingest the turn that spawned it."""
        f = tmp_path / "t.jsonl"
        lines = [
            {"message": {"role": "user", "content": "/tdd first task"}},
            {"message": {"role": "assistant", "content": "First answer."}},
            {"message": {"role": "user", "content": "second task"}},
            {"message": {"role": "assistant", "content": "Second answer."}},
            {"message": {"role": "user", "content": "/diagnose third task"}},
            {"message": {"role": "assistant", "content": "Third answer."}},
        ]
        f.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")

        skill, text = common.read_transcript_for_distillation(
            str(f), last_assistant_message="Second answer."
        )

        assert skill == "tdd"
        assert "second task" in text
        assert "Second answer" in text
        assert "first task" not in text
        assert "third task" not in text
        assert "Third answer" not in text

    @pytest.mark.parametrize("anchor", [None, "", "Unknown answer."])
    def test_missing_or_unknown_assistant_anchor_fails_closed(
        self, tmp_path: Path, anchor: str | None
    ) -> None:
        """A hook without one resolvable event anchor must store nothing."""
        f = tmp_path / "t.jsonl"
        lines = [
            {"message": {"role": "user", "content": "first task"}},
            {"message": {"role": "assistant", "content": "First answer."}},
            {"message": {"role": "user", "content": "later task"}},
            {"message": {"role": "assistant", "content": "Later answer."}},
        ]
        f.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")

        assert common.read_transcript_for_distillation(
            str(f), last_assistant_message=anchor
        ) == (None, "")

    def test_duplicate_assistant_anchor_fails_closed(self, tmp_path: Path) -> None:
        """Repeated assistant text is ambiguous and must not select one turn."""
        f = tmp_path / "t.jsonl"
        lines = [
            {"message": {"role": "user", "content": "first task"}},
            {"message": {"role": "assistant", "content": "Done."}},
            {"message": {"role": "user", "content": "second task"}},
            {"message": {"role": "assistant", "content": "Done."}},
        ]
        f.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")

        assert common.read_transcript_for_distillation(
            str(f), last_assistant_message="Done."
        ) == (None, "")
