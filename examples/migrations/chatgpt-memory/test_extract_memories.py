"""Tests for the ChatGPT memory OKF adapter."""

from __future__ import annotations

from pathlib import Path

from extract_memories import (
    _infer_category,
    _safe_filename,
    extract_memories,
    write_okf_bundle,
)


def _threads(messages) -> list[dict]:
    return [{"thread_id": "t1", "title": "T1", "messages": messages}]


def _user(text: str, ts: str = "2026-01-01T00:00:00Z") -> dict:
    return {"role": "user", "content": text, "timestamp": ts}


def _assistant(text: str) -> dict:
    return {"role": "assistant", "content": text, "timestamp": "2026-01-01T00:00:01Z"}


class TestCategoryInference:
    def test_preference_signal(self):
        assert _infer_category("I prefer Kotlin over Java.") == "preference"

    def test_fact_signal(self):
        assert _infer_category("I work with Kubernetes on Linux.") == "fact"

    def test_decision_signal(self):
        assert _infer_category("We went with PostgreSQL.") == "decision"

    def test_goal_signal(self):
        assert _infer_category("I want to ship by August.") == "goal"

    def test_fallback_to_context(self):
        assert _infer_category("How are you doing today?") == "context"


class TestExtractMemories:
    def test_skips_assistant_messages(self):
        # User message must be >=30 chars to be considered durable.
        mems = extract_memories(
            _threads([_user("I like Rust a lot and prefer it to Go."), _assistant("Rust is great.")])
        )
        assert len(mems) == 1
        assert all(m.thread_id == "t1" for m in mems)

    def test_skips_greetings_and_one_liners(self):
        mems = extract_memories(_threads([_user("Hi there!"), _user("ok")]))
        assert mems == []

    def test_skips_empty_content(self):
        mems = extract_memories(_threads([_user("")]))
        assert mems == []

    def test_captures_preference(self):
        mems = extract_memories(
            _threads([_user("I prefer Kotlin, I always use Ktor, and I hate messy code.")])
        )
        assert len(mems) == 1
        assert mems[0].category == "preference"
        assert "Kotlin" in mems[0].body
        assert mems[0].sources == ["2026-01-01T00:00:00Z"]

    def test_captures_fact(self):
        mems = extract_memories(
            _threads(
                [
                    _user(
                        "I work with Kubernetes on Arch Linux and my stack is Python 3.12."
                    )
                ]
            )
        )
        assert len(mems) == 1
        assert mems[0].category == "fact"

    def test_deduplicates_identical_body_same_thread(self):
        mems = extract_memories(
            _threads(
                [
                    _user("I like Go. I like Go. I like Go."),
                    _user("I like Go. I like Go. I like Go."),
                ]
            )
        )
        assert len(mems) == 1

    def test_empty_threads(self):
        assert extract_memories([]) == []
        assert extract_memories([{"thread_id": "x", "messages": []}]) == []

    def test_non_list_messages(self):
        assert extract_memories([{"thread_id": "x", "messages": None}]) == []

    def test_thread_identity(self):
        mems = extract_memories(
            _threads([_user("I live in Berlin and I work remotely.")])
        )
        m = mems[0]
        assert m.thread_title == "T1"
        assert "Berlin" in m.body


class TestOkfBundle:
    def _write_and_load(self, messages) -> tuple[Path, dict]:
        mems = extract_memories(_threads(messages))
        out = Path(f"/tmp/test_okf_bundle_chatgpt_{id(self)}_{id(messages)}")
        out.mkdir(exist_ok=True)
        write_okf_bundle(mems, out)

        import yaml

        docs = {}
        for f in sorted(out.glob("*.md")):
            if f.name == "index.md":
                continue
            text = f.read_text()
            parts = text.split("---", 2)
            fm = yaml.safe_load(parts[1])
            body = parts[2].strip()
            docs[f.name] = (fm, body)
        return out, docs

    def test_writes_valid_frontmatter(self):
        _, docs = self._write_and_load([_user("I prefer Kotlin and I use Arch Linux.")])
        assert len(docs) == 1
        fm, body = next(iter(docs.values()))
        assert fm["type"] == "preference"
        assert "x_memanto" in fm
        assert fm["x_memanto"]["source"] == "chatgpt"
        assert fm["resource"].startswith("chatgpt://thread/")

    def test_index_is_type_index(self):
        out, _ = self._write_and_load([_user("I prefer Kotlin and I use Arch Linux.")])
        idx = (out / "index.md").read_text()
        assert "---\ntype: index\n" in idx

    def test_bundle_count_matches_extraction(self):
        out, docs = self._write_and_load(
            [
                _user("I prefer Kotlin and I work with Kubernetes on Linux."),
                _user("I want to ship the MVP by August."),
            ]
        )
        assert len(docs) == 2

    def test_no_body_memory_produces_title(self):
        # Edge case: empty body but we already skip empties in extract; cover
        # the safe-filename helper instead.
        assert _safe_filename("  ") == "untitled"
        assert _safe_filename("A & B!") == "a-b"
        assert _safe_filename("normal").isascii()
