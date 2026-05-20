import importlib.util
import sys
from pathlib import Path

EXAMPLE_PATH = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "langgraph-memanto"
    / "support_agent.py"
)
README_PATH = EXAMPLE_PATH.with_name("README.md")
DEMO_GIF_PATH = EXAMPLE_PATH.parent / "assets" / "cross-session-demo.gif"


def load_example_module():
    spec = importlib.util.spec_from_file_location(
        "langgraph_memanto_example", EXAMPLE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_file_backend_recalls_memory_from_previous_session(tmp_path):
    module = load_example_module()
    memory_path = tmp_path / "memory.jsonl"
    backend = module.FileMemoryBackend(memory_path)

    backend.remember("acme", "ACME prefers invoice exports as CSV files.")
    runner = module.build_langgraph_runner(backend)

    final_state = runner(
        {
            "customer_id": "acme",
            "message": "How should I export this month's invoices?",
        }
    )

    assert "CSV" in final_state["reply"]
    assert "ACME prefers invoice exports" in final_state["reply"]
    assert final_state["writeback"].startswith("file-")


def test_graph_state_starts_without_memory_but_reply_uses_recalled_memory(tmp_path):
    module = load_example_module()
    backend = module.FileMemoryBackend(tmp_path / "memory.jsonl")
    backend.remember("globex", "Globex wants brief replies and CSV attachments.")

    initial_state = {
        "customer_id": "globex",
        "message": "Send this month's invoice export.",
    }

    assert "recalled_memory" not in initial_state

    final_state = module.build_langgraph_runner(backend)(initial_state)

    assert "recalled_memory" in final_state
    assert "CSV" in final_state["reply"]


def test_seed_and_ask_cli_flow_with_file_backend(tmp_path, capsys):
    module = load_example_module()
    memory_path = tmp_path / "memory.jsonl"

    seed_exit = module.main(
        [
            "--backend",
            "file",
            "--memory-path",
            str(memory_path),
            "seed",
            "--customer-id",
            "initech",
            "--fact",
            "Initech prefers CSV invoice exports.",
        ]
    )
    ask_exit = module.main(
        [
            "--backend",
            "file",
            "--memory-path",
            str(memory_path),
            "ask",
            "--customer-id",
            "initech",
            "--message",
            "Which format should I use?",
        ]
    )

    output = capsys.readouterr().out
    assert seed_exit == 0
    assert ask_exit == 0
    assert "Use CSV for this export." in output


def test_readme_links_demo_gif_required_by_bounty():
    readme = README_PATH.read_text(encoding="utf-8")

    assert "./assets/cross-session-demo.gif" in readme
    assert DEMO_GIF_PATH.exists()
    assert DEMO_GIF_PATH.read_bytes().startswith(b"GIF")
