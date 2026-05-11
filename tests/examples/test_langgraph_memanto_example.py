from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

EXAMPLE_DIR = Path(__file__).resolve().parents[2] / "examples" / "langgraph-memanto"


def load_example_module(name: str):
    spec = importlib.util.spec_from_file_location(name, EXAMPLE_DIR / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_in_memory_client_recalls_across_sessions() -> None:
    memory = load_example_module("memanto_memory")

    client = memory.InMemoryMemantoClient()
    agent_id = "test-langgraph-agent"
    profile = {
        "customer": "Avery",
        "product": "Memanto-backed LangGraph support bots",
        "deadline": "Friday demo",
        "preference": "short answers with implementation checklists",
    }

    memory_id = memory.remember_profile(client, agent_id=agent_id, profile=profile)
    recalled = memory.recall_profile(client, agent_id=agent_id, customer="Avery")
    rendered = memory.render_recalled_memories(recalled)

    assert memory_id == "dry-1"
    assert len(recalled) == 1
    assert "Friday demo" in rendered
    assert "implementation checklists" in rendered


def test_readme_contains_required_bounty_evidence() -> None:
    readme = (EXAMPLE_DIR / "README.md").read_text()

    assert "Cross-session recall" in readme
    assert "30-second demo GIF/video" in readme
    assert "run_full_demo.py --dry-run" in readme
    assert "run_seed_session.py" in readme
    assert "run_recall_session.py" in readme
