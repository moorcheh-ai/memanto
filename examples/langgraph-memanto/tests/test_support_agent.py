from __future__ import annotations

from memory_adapter import InMemoryMemantoStore
from support_agent import run_support_turn


def test_support_agent_recalls_memory_across_fresh_graph_invocations() -> None:
    store = InMemoryMemantoStore()

    first_turn = run_support_turn(
        memory_store=store,
        user_id="customer-dana",
        thread_id="yesterday-onboarding-call",
        message=(
            "Remember that Dana wants invoices emailed every Friday with the "
            "purchase order in the subject"
        ),
    )

    second_turn = run_support_turn(
        memory_store=store,
        user_id="customer-dana",
        thread_id="today-new-ticket",
        message="In a fresh support thread, how should I send Dana's invoice?",
    )

    assert first_turn["recalled_memories"] == []
    assert first_turn["stored_memory_id"].startswith("dry-")
    assert "fresh support thread" in second_turn["message"]
    assert len(second_turn["recalled_memories"]) == 1
    assert "every Friday" in second_turn["response"]
    assert "purchase order" in second_turn["response"]


def test_support_agent_does_not_store_profile_memory_in_graph_state() -> None:
    store = InMemoryMemantoStore()

    result = run_support_turn(
        memory_store=store,
        user_id="customer-dana",
        thread_id="unknown-request",
        message="How should I send Dana's invoice?",
    )

    assert "stored_profile" not in result
    assert result["recalled_memories"] == []
    assert "clarifying question" in result["response"]
