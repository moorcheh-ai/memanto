from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from memanto.cli.migrate.mappers import map_okf
from memanto.cli.migrate.okf_loader import load_okf_bundle

EXAMPLE_DIR = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "migrations"
    / "langgraph_checkpoints_to_okf"
)


def _load_run_demo():
    pytest.importorskip("langgraph")
    sys.path.insert(0, str(EXAMPLE_DIR))
    spec = importlib.util.spec_from_file_location("lg_okf_run_demo", EXAMPLE_DIR / "run_demo.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_langgraph_checkpoint_demo_round_trips_through_memanto_okf(tmp_path):
    run_demo = _load_run_demo()

    result = run_demo.run(tmp_path)

    assert result["validation"]["passed"] is True
    assert result["conversion"]["deduped_memories"] == 6

    okf_path = tmp_path / "okf_bundle"
    rows = map_okf(load_okf_bundle(okf_path))
    assert len(rows) == 6
    assert any("Tuesday mornings around 11:00 UTC" in row["content"] for row in rows)
    assert any(row["source"] == "langgraph-checkpoint" for row in rows)
