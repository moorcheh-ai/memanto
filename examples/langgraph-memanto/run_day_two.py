"""Day-two script: prove LangGraph can recall yesterday's Memanto memories."""

from __future__ import annotations

from memory_store import format_memories
from run_full_demo import create_memory
from support_graph import build_support_graph


if __name__ == "__main__":
    memory = create_memory()
    graph = build_support_graph(memory)
    result = graph.invoke(
        {
            "user_id": "maya",
            "message": "Can you send my receipt and remind me what happened to my order?",
            "session_label": "day-two",
        }
    )
    print(format_memories(result["retrieved_memories"]))
    print(result["response"])
