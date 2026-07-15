"""Tests for SkillMemory orchestration (recall, distill, persist) with a fake SDK."""

from __future__ import annotations

from typing import Any

from claudecode_memanto.client import SOURCE_TAG, SkillMemory
from claudecode_memanto.config import SkillsConfig

from .conftest import FakeSdkClient


def _mem(config: SkillsConfig, client: FakeSdkClient) -> SkillMemory:
    return SkillMemory(config=config, client=client)


class TestSetup:
    def test_existing_agent_activates_without_create(
        self, config: SkillsConfig
    ) -> None:
        # Common case: agent already exists — exactly one network call.
        fake = FakeSdkClient()
        mem = _mem(config, fake)
        mem.setup()
        assert fake.created == []
        assert fake.activated == ["test-agent"]

    def test_missing_agent_is_created_then_activated(
        self, config: SkillsConfig
    ) -> None:
        fake = FakeSdkClient(agent_exists=False)
        mem = _mem(config, fake)
        mem.setup()
        assert fake.created == ["test-agent"]
        assert fake.activated == ["test-agent"]

    def test_setup_is_idempotent(self, config: SkillsConfig) -> None:
        fake = FakeSdkClient()
        mem = _mem(config, fake)
        mem.setup()
        mem.setup()
        # Activated at most once despite two setup calls.
        assert fake.activated == ["test-agent"]


class TestRecallForSkill:
    def test_recall_uses_skill_route(
        self, config: SkillsConfig, sample_memories: list[dict[str, Any]]
    ) -> None:
        fake = FakeSdkClient(recall_memories=sample_memories)
        mem = _mem(config, fake)
        profile = mem.recall_for_skill("tdd", task_hint="auth module")
        assert len(profile) == 3
        # Query is skill-routed and includes the task hint.
        call = fake.recall_calls[0]
        assert "testing" in call["query"]
        assert "auth module" in call["query"]
        # No hard type filter is passed (live-verified to over-constrain).
        assert "type" not in call or call["type"] is None


class TestDistillAndStore:
    def test_llm_path_stores_extracted(
        self, config: SkillsConfig, llm_answer_json: str
    ) -> None:
        fake = FakeSdkClient(answer_text=llm_answer_json)
        mem = _mem(config, fake)
        stored = mem.distill_and_store("grill-with-docs", "long transcript ...")
        assert len(stored) == 2
        # Persisted via batch with proper tags + source.
        assert len(fake.batch_calls) == 1
        persisted = fake.batch_calls[0]
        assert all(m["source"] == SOURCE_TAG for m in persisted)
        assert all(SOURCE_TAG in m["tags"] for m in persisted)
        assert all("skill:grill-with-docs" in m["tags"] for m in persisted)
        assert all(m["provenance"] == "inferred" for m in persisted)

    def test_falls_back_to_heuristic_when_llm_empty(self, config: SkillsConfig) -> None:
        fake = FakeSdkClient(answer_text="[]")  # LLM yields nothing
        mem = _mem(config, fake)
        stored = mem.distill_and_store("tdd", "We decided to use pytest for all tests.")
        assert len(stored) >= 1
        assert any(m["type"] == "decision" for m in stored)

    def test_empty_summary_stores_nothing(self, config: SkillsConfig) -> None:
        fake = FakeSdkClient()
        mem = _mem(config, fake)
        assert mem.distill_and_store("tdd", "   ") == []
        assert fake.batch_calls == []

    def test_batch_failure_falls_back_to_individual(
        self, config: SkillsConfig, llm_answer_json: str
    ) -> None:
        fake = FakeSdkClient(answer_text=llm_answer_json)

        def boom(*_: Any, **__: Any) -> dict:
            raise RuntimeError("batch down")

        fake.batch_remember = boom  # type: ignore[assignment]
        mem = _mem(config, fake)
        stored = mem.distill_and_store("tdd", "transcript")
        assert len(stored) == 2
        assert len(fake.remembered) == 2  # individual fallback used

    def test_llm_failure_falls_back_to_heuristic(self, config: SkillsConfig) -> None:
        fake = FakeSdkClient()

        def boom(*_: Any, **__: Any) -> dict:
            raise RuntimeError("llm down")

        fake.answer = boom  # type: ignore[assignment]
        mem = _mem(config, fake)
        stored = mem.distill_and_store("tdd", "We chose Redis for caching.")
        assert any(m["type"] == "decision" for m in stored)

    def test_returns_only_successfully_persisted_when_individuals_fail(
        self, config: SkillsConfig, llm_answer_json: str
    ) -> None:
        # batch_remember fails; per-memory remember fails for the FIRST item
        # only. The returned list must reflect reality: 1 stored, not 2.
        fake = FakeSdkClient(answer_text=llm_answer_json)

        def batch_boom(*_: Any, **__: Any) -> dict:
            raise RuntimeError("batch down")

        calls = {"n": 0}

        def remember_partial(*_: Any, **__: Any) -> dict:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("first write failed")
            return {"memory_id": "ok"}

        fake.batch_remember = batch_boom  # type: ignore[assignment]
        fake.remember = remember_partial  # type: ignore[assignment]
        mem = _mem(config, fake)
        stored = mem.distill_and_store("tdd", "transcript")
        # 2 attempted, 1 succeeded — the return value must agree.
        assert calls["n"] == 2
        assert len(stored) == 1

    def test_tags_use_normalized_skill_name(
        self, config: SkillsConfig, llm_answer_json: str
    ) -> None:
        # "/TDD " must be canonicalised to "skill:tdd" so the same skill never
        # splits into two tag identities.
        fake = FakeSdkClient(answer_text=llm_answer_json)
        mem = _mem(config, fake)
        mem.distill_and_store("/TDD ", "transcript")
        for persisted in fake.batch_calls[0]:
            assert "skill:tdd" in persisted["tags"]
            assert "skill:/TDD " not in persisted["tags"]
            assert "skill:/tdd " not in persisted["tags"]


class TestProfileBlock:
    def test_profile_block_renders(
        self, config: SkillsConfig, sample_memories: list[dict[str, Any]]
    ) -> None:
        fake = FakeSdkClient(recall_memories=sample_memories)
        mem = _mem(config, fake)
        block = mem.profile_block()
        assert "engineering-profile" in block
