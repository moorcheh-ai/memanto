import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from seed_graphiti import build_offline_export, load_fixture


def test_export_shape():
    export = build_offline_export(load_fixture())
    assert export["source"] == "graphiti"
    assert export["group_id"] == "mira-travel-agent"
    assert len(export["episodes"]) >= 12
    assert len(export["entities"]) >= 10
    assert len(export["edges"]) >= 12
    assert export["invalidated"]
    veg = next(e for e in export["edges"] if e["uuid"] == "e-veg")
    assert veg["invalid_at"]
