"""Tests for the LangGraph + Memanto example helpers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


EXAMPLE_DIR = Path(__file__).resolve().parents[1] / "examples" / "langgraph-memanto"
sys.path.insert(0, str(EXAMPLE_DIR))

memory_store_spec = importlib.util.spec_from_file_location(
    "langgraph_memanto_memory_store", EXAMPLE_DIR / "memory_store.py"
)
support_agent_spec = importlib.util.spec_from_file_location(
    "langgraph_memanto_support_agent", EXAMPLE_DIR / "support_agent.py"
)
assert memory_store_spec and memory_store_spec.loader
assert support_agent_spec and support_agent_spec.loader

memory_store = importlib.util.module_from_spec(memory_store_spec)
sys.modules["memory_store"] = memory_store
sys.modules[memory_store_spec.name] = memory_store
memory_store_spec.loader.exec_module(memory_store)

support_agent = importlib.util.module_from_spec(support_agent_spec)
sys.modules[support_agent_spec.name] = support_agent
support_agent_spec.loader.exec_module(support_agent)


def test_extract_memories_creates_typed_customer_facts():
    memories = support_agent.extract_memories(
        "acme-ops",
        (
            "Enterprise customer in Europe/London prefers a dark dashboard "
            "and wants Tuesday follow-up."
        ),
    )

    memory_types = {memory.memory_type for memory in memories}
    titles = {memory.title for memory in memories}

    assert {"fact", "preference", "commitment"}.issubset(memory_types)
    assert "acme-ops plan" in titles
    assert "acme-ops dashboard preference" in titles


def test_local_store_recalls_memories_across_instances(tmp_path):
    store_path = tmp_path / "memories.json"
    day1 = memory_store.LocalJsonMemoryStore(store_path)
    day1.remember(
        memory_store.MemoryItem(
            title="acme-ops dashboard preference",
            content="acme-ops prefers a dark analytics dashboard.",
            memory_type="preference",
            tags=("acme-ops", "dashboard"),
        )
    )

    day2 = memory_store.LocalJsonMemoryStore(store_path)
    results = day2.recall("what dashboard preference does acme-ops have?")

    assert len(results) == 1
    assert results[0].title == "acme-ops dashboard preference"
    assert "dark analytics dashboard" in results[0].content
