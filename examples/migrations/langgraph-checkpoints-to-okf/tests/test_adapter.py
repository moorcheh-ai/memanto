"""End-to-end tests for the LangGraph -> OKF migration adapter.

Includes the acceptance test that matters most: the emitted bundle must load
through Memanto's OWN OKF loader and map through their OKF mapper without
dropping records.
"""

import glob
import json
import os
import sys

import pytest
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import adapter  # noqa: E402
import seed_agent  # noqa: E402
import validate  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def pipeline(tmp_path_factory):
    """Rebuild the store and bundle once for the whole test session,
    redirecting every generated artifact into a temp directory."""
    tmp = tmp_path_factory.mktemp("lg")
    seed_agent.DB_PATH = str(tmp / "checkpoints.sqlite")
    adapter.DB_PATH = seed_agent.DB_PATH
    adapter.OUT_DIR = str(tmp / "out")
    adapter.BUNDLE_DIR = str(tmp / "out" / "okf-bundle")
    adapter.SUMMARY_PATH = str(tmp / "out" / "migration_summary.json")
    validate.BUNDLE_DIR = adapter.BUNDLE_DIR
    validate.SUMMARY_PATH = adapter.SUMMARY_PATH
    seed_agent.seed(force=True)
    summary = adapter.run()
    return summary


def test_bundle_documents_valid_frontmatter():
    files = glob.glob(os.path.join(adapter.BUNDLE_DIR, "memories", "*.md"))
    assert len(files) == 11, f"expected 11 OKF docs, got {len(files)}"
    for path in files:
        text = open(path, encoding="utf-8").read()
        assert text.startswith("---\n"), path
        fm = yaml.safe_load(text.split("\n---\n", 1)[0][4:])
        for key in ("type", "title", "resource", "tags", "timestamp", "x_memanto"):
            assert fm.get(key) is not None, f"{path} missing {key}"
        assert fm["resource"].startswith("langgraph-checkpoint://")
        assert fm["x_memanto"]["source"] == "langgraph-checkpoints"
        assert fm.get("thread_id") and fm.get("checkpoint_id")


def test_summary_matches_bundle():
    summary = json.load(open(adapter.SUMMARY_PATH, encoding="utf-8"))
    assert summary["total_memories"] == 11
    assert sum(summary["per_type"].values()) == 11
    assert sum(summary["per_thread"].values()) == 11
    assert set(summary["per_thread"]) == {"alex-travel", "alex-work-policy"}


def test_recall_parity_100pct():
    assert validate.run() is True


def test_loads_through_memantos_own_loader_and_mapper():
    """THE acceptance test: memanto's shipped tooling consumes the bundle."""
    from memanto.cli.migrate.mappers import MAPPERS, type_breakdown
    from memanto.cli.migrate.okf_loader import load_okf_bundle

    export = load_okf_bundle(adapter.BUNDLE_DIR)
    assert len(export["memories"]) == 11, "memanto loader dropped entries"

    rows = MAPPERS["okf"](export)
    assert len(rows) == 11, "memanto mapper dropped rows"

    # losslessness: our extras must survive into their [Supporting data] footer
    assert any("thread_id" in (r["content"] or "") for r in rows)
    assert any(
        "8842-1190" in (r["content"] or "") for r in rows
    )  # loyalty number intact
    assert any("no longer vegetarian" in (r["content"] or "").lower() for r in rows)

    breakdown = type_breakdown(rows)
    assert breakdown.get("preference", 0) >= 4
    print("memanto-side type breakdown:", breakdown)


def test_rerun_is_idempotent():
    before = sorted(os.listdir(os.path.join(adapter.BUNDLE_DIR, "memories")))
    adapter.run()
    after = sorted(os.listdir(os.path.join(adapter.BUNDLE_DIR, "memories")))
    assert before == after


def test_thread_discovery_covers_non_script_threads(tmp_path):
    """Threads not present in the demo SCRIPT must still be discovered and
    migrated; requesting an unknown thread must fail loudly."""
    from langgraph.checkpoint.sqlite import SqliteSaver

    db = str(tmp_path / "extra.sqlite")
    with SqliteSaver.from_conn_string(db) as saver:
        app = seed_agent.build_graph(saver)
        app.invoke(
            {"messages": [{"role": "user", "content": "My home airport is JFK"}]},
            config={"configurable": {"thread_id": "unscripted-thread"}},
        )

    assert "unscripted-thread" in adapter.discover_thread_ids(db)

    old_db = adapter.DB_PATH
    adapter.DB_PATH = db
    try:
        data = adapter.read_thread_memories()
        with pytest.raises(ValueError, match="not present"):
            adapter.read_thread_memories(["does-not-exist"])
    finally:
        adapter.DB_PATH = old_db

    assert "unscripted-thread" in data
    assert any("JFK" in m["text"] for m in data["unscripted-thread"]["memories"])
