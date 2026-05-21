from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


def _example_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "examples" / "langgraph-memanto"


def _load_memory_adapter():
    module_path = _example_dir() / "memory_adapter.py"
    spec = importlib.util.spec_from_file_location(
        "langgraph_memory_adapter", module_path
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_graph():
    langgraph_module = types.ModuleType("langgraph")
    langgraph_graph_module = types.ModuleType("langgraph.graph")
    langgraph_graph_module.END = "__end__"
    langgraph_graph_module.StateGraph = object
    previous_langgraph = sys.modules.get("langgraph")
    previous_langgraph_graph = sys.modules.get("langgraph.graph")
    previous_memory_adapter = sys.modules.get("memory_adapter")
    sys.modules["langgraph"] = langgraph_module
    sys.modules["langgraph.graph"] = langgraph_graph_module
    inserted_path = str(_example_dir())
    sys.path.insert(0, inserted_path)
    try:
        module_path = _example_dir() / "graph.py"
        spec = importlib.util.spec_from_file_location(
            "langgraph_demo_graph", module_path
        )
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if inserted_path in sys.path:
            sys.path.remove(inserted_path)
        if previous_langgraph is None:
            sys.modules.pop("langgraph", None)
        else:
            sys.modules["langgraph"] = previous_langgraph
        if previous_langgraph_graph is None:
            sys.modules.pop("langgraph.graph", None)
        else:
            sys.modules["langgraph.graph"] = previous_langgraph_graph
        if previous_memory_adapter is None:
            sys.modules.pop("memory_adapter", None)
        else:
            sys.modules["memory_adapter"] = previous_memory_adapter


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


def test_local_json_memory_recovers_from_malformed_store(tmp_path):
    memory_adapter = _load_memory_adapter()
    store = tmp_path / "memories.json"
    store.write_text("{not valid json", encoding="utf-8")
    memory = memory_adapter.LocalJsonMemory(
        path=store,
        agent_id="test-langgraph-agent",
    )

    assert memory.recall(query="dark-mode support preferences") == []
    stored = memory.remember(
        memory_type="preference",
        title="Maya support preferences",
        content="Maya prefers concise replies.",
        tags=["support"],
    )

    assert stored["memory_id"].startswith("local-")


def test_session_boundary_clears_day1_state():
    graph = _load_graph()

    result = graph._session_boundary(
        {
            "customer_name": "Maya Chen",
            "ticket_id": "TICK-1842",
            "day1_memories": [{"title": "leaked"}],
            "stored_memory_ids": ["local-123"],
        }
    )

    assert result["customer_name"] == ""
    assert result["ticket_id"] == ""
    assert result["day1_memories"] == []
    assert "stored_memory_ids" not in result
