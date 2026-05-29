from __future__ import annotations

from memanto_skills import (
    LocalJsonlBackend,
    SkillMemory,
    post_skill_capture,
    pre_skill_context,
)


def test_cross_skill_memory_round_trip(tmp_path):
    backend = LocalJsonlBackend(tmp_path / "memory.jsonl")

    post_skill_capture(
        backend=backend,
        skill="/grill-with-docs",
        prompt="Review the payments service architecture.",
        transcript=(
            "Decision: keep Stripe webhook signature verification at the "
            "HTTP boundary and store normalized events through a repository."
        ),
        path_hint="services/payments",
    )

    context = pre_skill_context(
        backend=backend,
        skill="/tdd",
        prompt="Add webhook retry tests.",
        path_hint="services/payments",
    )

    assert "Stripe webhook signature verification" in context
    assert "repository" in context


def test_unrelated_query_does_not_inject_context(tmp_path):
    backend = LocalJsonlBackend(tmp_path / "memory.jsonl")

    post_skill_capture(
        backend=backend,
        skill="/handoff",
        prompt="Document frontend routing.",
        transcript="Decision: keep route objects in web/router.",
        path_hint="web/router",
    )

    context = pre_skill_context(
        backend=backend,
        skill="/tdd",
        prompt="Add database migration tests.",
        path_hint="db/migrations",
    )

    assert context == ""


def test_single_shared_token_does_not_inject_context(tmp_path):
    backend = LocalJsonlBackend(tmp_path / "memory.jsonl")
    backend.remember(
        SkillMemory(
            memory_type="decision",
            title="Webhook note",
            content="Document webhook retries in the API guide.",
            skill="/handoff",
            path_hint="docs/api",
        )
    )

    context = pre_skill_context(
        backend=backend,
        skill="/tdd",
        prompt="Add webhook retry tests.",
        path_hint="services/payments",
    )

    assert context == ""


def test_empty_query_does_not_inject_context(tmp_path):
    backend = LocalJsonlBackend(tmp_path / "memory.jsonl")
    backend.remember(
        SkillMemory(
            memory_type="decision",
            title="Payments backend",
            content="Use repository storage for Stripe webhooks.",
            skill="/grill-with-docs",
            path_hint="services/payments",
        )
    )

    assert backend.recall("") == []


def test_corrupt_jsonl_line_is_skipped(tmp_path):
    store = tmp_path / "memory.jsonl"
    store.write_text(
        '{"memory_type":"decision","title":"Valid","content":"Use repository '
        'storage for Stripe webhooks.","skill":"/grill-with-docs",'
        '"path_hint":"services/payments","confidence":0.9}\n'
        "{not-json}\n",
        encoding="utf-8",
    )
    backend = LocalJsonlBackend(store)

    context = pre_skill_context(
        backend=backend,
        skill="/tdd",
        prompt="Add Stripe webhook storage tests.",
        path_hint="services/payments",
    )

    assert "Use repository storage" in context


def test_prompt_decision_text_is_not_treated_as_session_output(tmp_path):
    backend = LocalJsonlBackend(tmp_path / "memory.jsonl")

    memory = post_skill_capture(
        backend=backend,
        skill="/handoff",
        prompt="Decision: use Redis for webhook storage?",
        transcript="We explored storage tradeoffs but did not finalize a backend.",
        path_hint="services/payments",
    )

    assert memory.memory_type == "preference"
    assert "Redis" not in memory.content
