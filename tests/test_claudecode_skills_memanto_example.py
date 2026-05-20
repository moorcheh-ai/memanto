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

WRAPPER_PATH = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "claudecode-skills-memanto"
    / "run_skill_with_memory.py"
)
wrapper_spec = importlib.util.spec_from_file_location("run_skill_with_memory", WRAPPER_PATH)
assert wrapper_spec and wrapper_spec.loader
wrapper = importlib.util.module_from_spec(wrapper_spec)
sys.modules["run_skill_with_memory"] = wrapper
wrapper_spec.loader.exec_module(wrapper)

BENCHMARK_PATH = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "claudecode-skills-memanto"
    / "productivity_benchmark.py"
)
benchmark_spec = importlib.util.spec_from_file_location(
    "productivity_benchmark", BENCHMARK_PATH
)
assert benchmark_spec and benchmark_spec.loader
benchmark = importlib.util.module_from_spec(benchmark_spec)
sys.modules["productivity_benchmark"] = benchmark
benchmark_spec.loader.exec_module(benchmark)

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


class FakeDistillingBackend(FakeBackend):
    def distill_transcript(self, run: hook.SkillRun) -> list[dict[str, object]]:
        assert run.skill == "handoff"
        return [
            {
                "content": "Use the repository service layer for billing retries.",
                "memory_type": "decision",
                "title": "billing retry layer",
                "tags": ["claude-code-skills", "skill:handoff"],
                "confidence": 0.93,
            }
        ]


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


def test_post_hook_extracts_multiple_typed_memories() -> None:
    backend = FakeBackend()
    run = hook.SkillRun(
        skill="grill-with-docs",
        task="Review auth session design",
        files=("src/auth/session.ts",),
        transcript=(
            "Decision: keep refresh tokens server-side only. "
            "Preference: test session expiry at the service boundary. "
            "Never: log raw tokens in debug output."
        ),
    )

    stored = hook.store_completed_run(run, backend)

    assert stored == 3
    assert [memory["memory_type"] for memory in backend.stored] == [
        "decision",
        "preference",
        "instruction",
    ]
    assert "server-side only" in backend.stored[0]["content"]
    assert "service boundary" in backend.stored[1]["content"]
    assert "raw tokens" in backend.stored[2]["content"]
    assert backend.stored[2]["confidence"] == 0.9


def test_post_hook_prefers_backend_llm_distillation() -> None:
    backend = FakeDistillingBackend()
    run = hook.SkillRun(
        skill="handoff",
        task="Summarize billing retry implementation",
        files=("src/billing/retries.ts",),
        transcript="Implemented retries without a structured decision prefix.",
    )

    stored = hook.store_completed_run(run, backend)

    assert stored == 1
    assert backend.stored[0]["title"] == "billing retry layer"
    assert "repository service layer" in backend.stored[0]["content"]
    assert backend.stored[0]["confidence"] == 0.93


def test_sdk_answer_parser_accepts_json_wrapped_in_text() -> None:
    answer = """
    Here is the distilled output:
    {
      "memories": [
        {
          "type": "instruction",
          "title": "token logging",
          "content": "Never log raw OAuth tokens in debug traces.",
          "confidence": 1.4
        }
      ]
    }
    """
    run = hook.SkillRun(
        skill="grill-with-docs",
        task="Review OAuth refresh flow",
        files=("src/auth/oauth.ts",),
    )

    memories = hook._parse_distilled_memories(run, answer)

    assert memories == [
        {
            "content": "Never log raw OAuth tokens in debug traces.",
            "memory_type": "instruction",
            "title": "token logging",
            "tags": [
                "claude-code-skills",
                "skill:grill-with-docs",
                "file:oauth.ts",
            ],
            "confidence": 1.0,
        }
    ]


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


def test_build_backend_uses_local_jsonl_store(tmp_path) -> None:
    store = tmp_path / "memory.jsonl"
    backend = hook.build_backend("local-jsonl", store)

    backend.remember(
        content="Use a wrapper environment variable for recalled skill context.",
        memory_type="decision",
        title="wrapper context",
        tags=["skill:tdd"],
        confidence=0.88,
    )

    assert backend.recall("wrapper skill context") == [
        "Use a wrapper environment variable for recalled skill context."
    ]


def test_sdk_recall_extractor_reads_memory_content() -> None:
    result = {
        "memories": [
            {"content": "Prefer service-level retry tests."},
            {"content": "Preserve idempotency keys."},
            {"content": ""},
            {"title": "missing content"},
        ]
    }

    memories = hook._extract_sdk_memory_lines(result)

    assert memories == [
        "Prefer service-level retry tests.",
        "Preserve idempotency keys.",
    ]


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


def test_wrapper_exports_recalled_context_to_child_command(tmp_path, capsys) -> None:
    store = tmp_path / "memory.jsonl"
    backend = hook.LocalJsonlBackend(store)
    backend.remember(
        content="Keep invoice retry tests deterministic across sessions.",
        memory_type="decision",
        title="invoice retry tests",
        tags=["skill:tdd", "file:retries.ts"],
        confidence=0.91,
    )

    child = (
        "import os; "
        "print(os.environ.get('MEMANTO_SKILL_CONTEXT', '').splitlines()[1])"
    )
    status = wrapper.main(
        [
            "--skill",
            "tdd",
            "--task",
            "invoice retry tests",
            "--file",
            "src/billing/retries.ts",
            "--backend",
            "local-jsonl",
            "--store",
            str(store),
            "--",
            sys.executable,
            "-c",
            child,
        ]
    )

    captured = capsys.readouterr()
    assert status == 0
    assert "Relevant prior engineering decisions" in captured.out
    assert "Keep invoice retry tests deterministic" in captured.out


def test_productivity_benchmark_measures_repeated_instruction_reduction(tmp_path) -> None:
    result = benchmark.run_benchmark(tmp_path / "benchmark-memory.jsonl")

    assert result["skill_runs"] == 3
    assert result["stored_memories"] >= 6
    assert result["baseline_repeated_prompts"] == 2
    assert result["memanto_reused_prompts"] == 2
    assert result["repeated_instruction_reduction"] == 1.0
