from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_memory_adapter():
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "examples" / "langgraph-memanto" / "memory_adapter.py"
    spec = importlib.util.spec_from_file_location("langgraph_memory_adapter", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_local_json_memory_persists_and_recalls(tmp_path):
    memory_adapter = _load_memory_adapter()
    store = tmp_path / "memories.json"
    memory = memory_adapter.LocalJsonMemory(
        path=store,
        agent_id="test-langgraph-agent",
    )

    memory.setup()
    stored = memory.remember(
        memory_type="preference",
        title="Maya support preferences",
        content="Maya prefers dark-mode screenshots and concise support replies.",
        tags=["support", "langgraph-demo"],
    )
    recalled = memory.recall(query="dark-mode support preferences", limit=3)

    assert stored["memory_id"].startswith("local-")
    assert store.exists()
    assert recalled
    assert recalled[0]["title"] == "Maya support preferences"
