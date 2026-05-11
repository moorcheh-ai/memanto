#!/usr/bin/env python3
from __future__ import annotations

from graph import build_support_graph, default_initial_state


class FakeMemory:
    def __init__(self) -> None:
        self.writes: list[str] = []

    def recall(
        self, query: str, *, limit: int = 5, memory_type: str | None = None
    ) -> str:
        return (
            "maya-rivera prefers concise email updates, is in the "
            "America/Los_Angeles timezone, and has open support issue INV-4832."
        )

    def remember(
        self,
        content: str,
        *,
        memory_type: str = "fact",
        tags: list[str] | None = None,
        confidence: float = 0.8,
        provenance: str = "explicit_statement",
    ) -> str:
        self.writes.append(content)
        return "stored"


def main() -> None:
    memory = FakeMemory()
    graph = build_support_graph(memory)
    final_state = graph.invoke(default_initial_state())

    assert "INV-4832" in final_state["reply"]
    assert "concise" in final_state["reply"]
    assert final_state.get("memories_written")
    assert memory.writes

    print("Smoke test passed: LangGraph recalled context and wrote a follow-up.")


if __name__ == "__main__":
    main()
