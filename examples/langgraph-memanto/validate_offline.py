"""Offline validation for the LangGraph + Memanto example."""

from __future__ import annotations

from langgraph_memanto import LocalMemoryAdapter, run_support_session, seed_day_one


def validate() -> None:
    adapter = LocalMemoryAdapter()
    adapter.clear()
    seed_day_one(adapter)
    result = run_support_session(adapter)

    recalled = result["recalled_memories"]
    response = result["response"]

    assert len(recalled) >= 3, "expected at least three recalled day-one memories"
    assert "AR-8841" in response, "response should recall the prior order id"
    assert "replacement before issuing a refund" in response
    assert "concise replies with bullet points" in response
    assert result["memory_written"].startswith("local-")
    print("offline validation passed")


if __name__ == "__main__":
    validate()
