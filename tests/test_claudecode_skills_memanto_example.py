from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


EXAMPLE_PATH = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "claudecode-skills-memanto"
    / "memanto_skills_hook.py"
)

spec = importlib.util.spec_from_file_location("memanto_skills_hook", EXAMPLE_PATH)
assert spec and spec.loader
hook = importlib.util.module_from_spec(spec)
sys.modules["memanto_skills_hook"] = hook
spec.loader.exec_module(hook)

ADAPTER_PATH = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "claudecode-skills-memanto"
    / "mattpocock_adapter.py"
)
adapter_spec = importlib.util.spec_from_file_location(
    "mattpocock_adapter", ADAPTER_PATH
)
assert adapter_spec and adapter_spec.loader
adapter = importlib.util.module_from_spec(adapter_spec)
sys.modules["mattpocock_adapter"] = adapter
adapter_spec.loader.exec_module(adapter)

HOOK_MANIFEST_PATH = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "claudecode-skills-memanto"
    / "claude-code-hooks.example.json"
)


class FakeBackend:
    def __init__(self) -> None:
        self.stored = []

    def recall(self, query: str, limit: int = 5) -> list[str]:
        assert "tdd" in query
        return [
            "Use service-level tests for billing retry policy.",
            "Keep retry delays deterministic in unit tests.",
        ][:limit]

    def remember(
        self,
        content: str,
        memory_type: str,
        title: str,
        tags: list[str],
        confidence: float,
    ) -> None:
        self.stored.append(
            {
                "content": content,
                "memory_type": memory_type,
                "title": title,
                "tags": tags,
                "confidence": confidence,
            }
        )


def test_pre_hook_formats_recalled_engineering_memory() -> None:
    run = hook.SkillRun(
        skill="tdd",
        task="Add invoice retry tests",
        files=("src/billing/retries.ts",),
    )

    context = hook.build_context_block(run, FakeBackend())

    assert "<memanto-engineering-memory>" in context
    assert "service-level tests" in context
    assert "deterministic" in context


def test_post_hook_stores_typed_decision_memory() -> None:
    backend = FakeBackend()
    run = hook.SkillRun(
        skill="handoff",
        task="Summarize billing retry implementation",
        files=("src/billing/retries.ts",),
        transcript="Implemented bounded retries. Preserved idempotency key handling.",
    )

    stored = hook.store_completed_run(run, backend)

    assert stored == 1
    memory = backend.stored[0]
    assert memory["memory_type"] == "decision"
    assert "bounded retries" in memory["content"]
    assert "skill:handoff" in memory["tags"]
    assert "file:retries.ts" in memory["tags"]


def test_local_jsonl_backend_round_trips_memory(tmp_path) -> None:
    backend = hook.LocalJsonlBackend(tmp_path / "memory.jsonl")
    backend.remember(
        content="Keep billing retry delays deterministic in tests.",
        memory_type="decision",
        title="billing retries",
        tags=["skill:tdd", "file:retries.ts"],
        confidence=0.9,
    )

    memories = backend.recall("tdd billing retries", limit=3)

    assert memories == ["Keep billing retry delays deterministic in tests."]


def test_mattpocock_adapter_builds_memory_aware_skill_spec() -> None:
    spec = adapter.build_skill_spec(
        "grill-with-docs",
        task="Review billing retry architecture",
        files=["src/billing/retries.ts"],
        backend="local-jsonl",
        store="/tmp/memory.jsonl",
    )

    assert spec.command == "/grill-with-docs"
    assert "pre" in spec.pre_hook
    assert "post" in spec.post_hook
    assert "--store" in spec.pre_hook
    assert "src/billing/retries.ts" in spec.post_hook
    assert "skill prompt" in spec.prompt_prefix


def test_static_hook_manifest_covers_named_skills() -> None:
    manifest = json.loads(HOOK_MANIFEST_PATH.read_text(encoding="utf-8"))

    assert sorted(manifest["skills"]) == ["grill-with-docs", "handoff", "tdd"]
    for skill, entry in manifest["skills"].items():
        assert entry["command"] == f"/{skill}"
        assert "pre" in entry["memory"]["before"]
        assert "post" in entry["memory"]["after"]
        assert "$SKILL_TASK" in entry["memory"]["before"]
        assert "$TRANSCRIPT_FILE" in entry["memory"]["after"]
