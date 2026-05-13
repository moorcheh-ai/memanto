from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_example_module():
    path = Path(__file__).with_name("langgraph_memanto.py")
    spec = importlib.util.spec_from_file_location("langgraph_memanto_example", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_in_memory_store_recalls_seeded_customer_context():
    module = load_example_module()
    store = module.InMemoryMemoryStore()

    store.remember(
        memory_type="fact",
        title="ada invoice",
        content="ada-lovelace invoice INV-1001 blocks renewal",
        tags=["support"],
    )

    memories = store.recall("What invoice context exists for ada-lovelace?")

    assert len(memories) == 1
    assert memories[0]["memory_id"] == "preview-1"
    assert "INV-1001" in memories[0]["content"]


def test_extract_customer_memory_marks_cross_session_langgraph_tags():
    module = load_example_module()

    memory = module.extract_customer_memory(
        {
            "customer_id": "ada-lovelace",
            "message": "Ada prefers concise renewal updates.",
        }
    )

    assert memory["memory_type"] == "fact"
    assert memory["title"] == "ada-lovelace support context"
    assert "cross-session" in memory["tags"]
    assert "langgraph" in memory["tags"]
