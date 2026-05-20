"""Tests for the Claude Code skills Memanto memory bridge."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# Load the hook module from the example path (not on sys.path)
EXAMPLE_DIR = Path(__file__).resolve().parents[1] / "claudecode-skills-memanto"
HOOK_PATH = EXAMPLE_DIR / "skill_memory_hook.py"
ADAPTER_PATH = EXAMPLE_DIR / "mattpocock_adapter.py"

spec = importlib.util.spec_from_file_location("skill_memory_hook", str(HOOK_PATH))
assert spec and spec.loader
hook = importlib.util.module_from_spec(spec)
sys.modules["skill_memory_hook"] = hook
spec.loader.exec_module(hook)

spec2 = importlib.util.spec_from_file_location("mattpocock_adapter", str(ADAPTER_PATH))
assert spec2 and spec2.loader
adapter = importlib.util.module_from_spec(spec2)
sys.modules["mattpocock_adapter"] = adapter
spec2.loader.exec_module(adapter)


# ---------------------------------------------------------------------------
# Fake backend
# ---------------------------------------------------------------------------


class FakeBackend:
    def __init__(self) -> None:
        self.stored: list[hook.DistilledMemory] = []
        self._memories: list[str] = []

    def seed(self, memories: list[str]) -> None:
        self._memories = list(memories)

    def recall(self, query: str, limit: int = 5) -> list[str]:
        return self._memories[:limit]

    def store(self, memory: hook.DistilledMemory) -> None:
        self.stored.append(memory)


# ---------------------------------------------------------------------------
# SkillRun
# ---------------------------------------------------------------------------


class TestSkillRun:
    def test_query_includes_skill_task_files(self) -> None:
        run = hook.SkillRun(
            skill="tdd",
            task="Add retry logic",
            files=("src/retries.py", "tests/test_retries.py"),
        )
        assert "tdd" in run.query
        assert "retry" in run.query
        assert "retries.py" in run.query

    def test_query_without_files(self) -> None:
        run = hook.SkillRun(skill="handoff", task="Summarize work")
        assert run.query == "handoff Summarize work"


# ---------------------------------------------------------------------------
# Local backend
# ---------------------------------------------------------------------------


class TestLocalBackend:
    def test_round_trip(self, tmp_path: Path) -> None:
        backend = hook.LocalBackend(tmp_path / "mem.jsonl")
        backend.store(
            hook.DistilledMemory(
                content="Keep retries deterministic",
                memory_type="decision",
                tags=["skill:tdd", "file:retries.py"],
            )
        )
        result = backend.recall("tdd retries deterministic")
        assert result == ["Keep retries deterministic"]

    def test_recall_empty_file(self, tmp_path: Path) -> None:
        backend = hook.LocalBackend(tmp_path / "empty.jsonl")
        assert backend.recall("anything") == []

    def test_recall_nonexistent_file(self, tmp_path: Path) -> None:
        backend = hook.LocalBackend(tmp_path / "nope.jsonl")
        assert backend.recall("anything") == []

    def test_recall_scores_by_term_overlap(self, tmp_path: Path) -> None:
        backend = hook.LocalBackend(tmp_path / "mem.jsonl")
        backend.store(
            hook.DistilledMemory(content="alpha beta gamma", memory_type="decision")
        )
        backend.store(hook.DistilledMemory(content="alpha only", memory_type="context"))
        result = backend.recall("alpha beta")
        assert result[0] == "alpha beta gamma"


# ---------------------------------------------------------------------------
# Memory distiller
# ---------------------------------------------------------------------------


class TestMemoryDistiller:
    def test_distills_decision(self) -> None:
        distiller = hook.MemoryDistiller()
        run = hook.SkillRun(skill="grill-with-docs", task="Review", files=("a.py",))
        memories = distiller.distill(
            "- Decision: Keep retries in the transport adapter.", run
        )
        assert len(memories) == 1
        assert memories[0].memory_type == "decision"
        assert "Keep retries in the transport adapter" in memories[0].content

    def test_distills_preference(self) -> None:
        distiller = hook.MemoryDistiller()
        run = hook.SkillRun(skill="tdd", task="Implement")
        memories = distiller.distill(
            "- Preference: Error messages name the upstream service.", run
        )
        assert memories[0].memory_type == "preference"

    def test_distills_instruction(self) -> None:
        distiller = hook.MemoryDistiller()
        run = hook.SkillRun(skill="tdd", task="Implement")
        memories = distiller.distill(
            "- Must: Never retry POST requests unless callers opt in.", run
        )
        assert memories[0].memory_type == "instruction"
        assert memories[0].confidence >= 0.85

    def test_distills_context(self) -> None:
        distiller = hook.MemoryDistiller()
        run = hook.SkillRun(skill="grill-with-docs", task="Review")
        memories = distiller.distill(
            "- Quirk: The billing service caches for 30s.", run
        )
        assert memories[0].memory_type == "context"

    def test_empty_transcript(self) -> None:
        distiller = hook.MemoryDistiller()
        run = hook.SkillRun(skill="tdd", task="x")
        assert distiller.distill("", run) == []

    def test_deduplicates(self) -> None:
        distiller = hook.MemoryDistiller()
        run = hook.SkillRun(skill="tdd", task="x")
        text = "Decision: Keep retries deterministic.\ndecision: Keep retries deterministic."
        memories = distiller.distill(text, run)
        assert len(memories) == 1

    def test_limits_to_12(self) -> None:
        distiller = hook.MemoryDistiller()
        run = hook.SkillRun(skill="tdd", task="x")
        lines = "\n".join(f"- Decision: Item {i}." for i in range(20))
        memories = distiller.distill(lines, run)
        assert len(memories) <= 12

    def test_tags_include_skill_and_files(self) -> None:
        distiller = hook.MemoryDistiller()
        run = hook.SkillRun(skill="tdd", task="x", files=("src/a.py", "src/b.py"))
        memories = distiller.distill(
            "- Decision: The retry handler must use exponential backoff.", run
        )
        assert len(memories) >= 1
        assert "skill:tdd" in memories[0].tags
        assert "file:a.py" in memories[0].tags
        assert "file:b.py" in memories[0].tags


# ---------------------------------------------------------------------------
# Context block
# ---------------------------------------------------------------------------


class TestContextBlock:
    def test_formats_memories(self) -> None:
        block = hook.build_context_block(["alpha", "beta"])
        assert "<memanto-engineering-memory>" in block
        assert "- alpha" in block
        assert "- beta" in block
        assert "</memanto-engineering-memory>" in block

    def test_empty_returns_empty_string(self) -> None:
        assert hook.build_context_block([]) == ""


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


class TestCliRecall:
    def test_recall_prints_context_block(self, tmp_path: Path) -> None:
        store = tmp_path / "mem.jsonl"
        backend = hook.LocalBackend(store)
        backend.store(
            hook.DistilledMemory(
                content="Keep retries deterministic", memory_type="decision"
            )
        )
        args = argparse_like(
            skill="tdd",
            task="Add retry tests",
            file=["src/retries.py"],
            backend="local",
            store=str(store),
        )
        rc = hook.cmd_recall(args)
        assert rc == 0


class TestCliStore:
    def test_store_distills_and_persists(self, tmp_path: Path) -> None:
        store = tmp_path / "mem.jsonl"
        args = argparse_like(
            skill="grill-with-docs",
            task="Review retries",
            file=["src/retries.py"],
            backend="local",
            store=str(store),
            transcript="- Decision: Keep retries deterministic.",
            transcript_file=None,
        )
        rc = hook.cmd_store(args)
        assert rc == 0
        assert store.exists()
        content = store.read_text()
        assert "deterministic" in content


class TestCliWrap:
    def test_wrap_runs_command_and_stores(self, tmp_path: Path) -> None:
        store = tmp_path / "mem.jsonl"
        args = argparse_like(
            skill="handoff",
            task="Summarize",
            file=[],
            backend="local",
            store=str(store),
            transcript=None,
            transcript_file=None,
            skill_command=[
                "python",
                "-c",
                "print('Decision: Handoff includes ownership.')",
            ],
        )
        rc = hook.cmd_wrap(args)
        assert rc == 0
        assert store.exists()


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class TestAdapter:
    def test_build_spec(self) -> None:
        spec = adapter.build_spec("tdd", task="Implement retries", files=["src/r.py"])
        assert spec.command == "/tdd"
        assert "recall" in spec.pre_hook
        assert "store" in spec.post_hook

    def test_unknown_skill_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown skill"):
            adapter.build_spec("nope", task="x")

    def test_write_wrappers(self, tmp_path: Path) -> None:
        import os

        orig = os.getcwd()
        os.chdir(tmp_path)
        try:
            written = adapter.write_wrappers(Path(".claude/commands"))
            assert len(written) == 3
            for p in written:
                assert p.exists()
                text = p.read_text()
                assert "skill_memory_hook.py recall" in text
                assert "skill_memory_hook.py store" in text
        finally:
            os.chdir(orig)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def argparse_like(**kwargs) -> object:
    class Args:
        pass

    a = Args()
    for k, v in kwargs.items():
        setattr(a, k, v)
    return a
