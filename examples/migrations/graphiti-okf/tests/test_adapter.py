from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapter import adapt, classify_edge
from seed_graphiti import build_offline_export, load_fixture


def test_classify_prefers():
    assert classify_edge({"name": "PREFERS", "fact": "x"}) == "preference"


def test_adapt_writes_memories(tmp_path: Path):
    export = build_offline_export(load_fixture())
    okf = tmp_path / "okf"
    summary = adapt(export, okf)
    assert summary["mapped_count"] == 34
    assert len(summary["per_type"]) == 12
    assert (okf / "index.md").exists()
    md_files = list((okf / "memories").rglob("*.md"))
    # exclude index.md files
    real = [p for p in md_files if p.name != "index.md"]
    assert len(real) == 34
    # contradiction tags present
    corpus = "\n".join(p.read_text() for p in real).lower()
    assert "vegetarian" in corpus
    assert "superseded" in corpus or "invalidated" in corpus
