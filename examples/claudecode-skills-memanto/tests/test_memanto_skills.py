from __future__ import annotations

from memanto_skills import LocalJsonlBackend, post_skill_capture, pre_skill_context


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
