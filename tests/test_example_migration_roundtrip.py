"""End-to-end test for the ChatGPT/Claude migration example.

Covers the Path B showcase requirements without needing a live API or network:
  1. the sample archives are valid, readable source exports,
  2. mapping produces typed memories (not empty, correctly classified),
  3. the OKF bundle exports and round-trips losslessly via the shipped loader,
  4. the golden-Q&A recall check passes (no amnesia).

To keep CI fast and hermetic this runs the in-repo example scripts directly
rather than shelling out.
"""

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]  # <repo>/
EXAMPLE = REPO / "examples" / "migrations" / "chatgpt-claude-memory"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(EXAMPLE / "scripts"))
sys.path.insert(0, str(EXAMPLE))

from memanto.cli.migrate.mappers import map_chatgpt, map_claude  # noqa: E402
from memanto.cli.migrate.okf_loader import load_okf_bundle  # noqa: E402

pytestmark = [
    pytest.mark.skipif(not EXAMPLE.exists(), reason="example not present"),
]


def load(source: str) -> dict:
    with (EXAMPLE / "data" / f"{source}_conversations.json").open() as fh:
        return json.load(fh)


def test_sample_archives_are_readable():
    for source in ("claude", "chatgpt"):
        export = load(source)
        assert "conversations" in export
        assert len(export["conversations"]) > 0


def test_map_yields_typed_memories():
    claude_rows = map_claude(load("claude"))
    chatgpt_rows = map_chatgpt(load("chatgpt"))
    rows = claude_rows + chatgpt_rows
    # 9 claude + 4 chatgpt user-signal turns => 13 typed memories total.
    assert len(claude_rows) == 9
    assert len(chatgpt_rows) == 4
    assert len(rows) == 13
    types = {r["type"] for r in rows}
    assert "preference" in types
    assert "goal" in types
    assert "decision" in types


def test_source_provenance_carried():
    for source, mapper in (("claude", map_claude), ("chatgpt", map_chatgpt)):
        for r in mapper(load(source)):
            assert r["source"] == source
            assert r["provenance"] == "imported"


def test_okf_bundle_roundtrips_losslessly(tmp_path):
    # Build rows the same way run_migration.py does.
    all_rows = map_claude(load("claude")) + map_chatgpt(load("chatgpt"))
    by_type: dict[str, list[dict]] = {}
    for r in all_rows:
        by_type.setdefault(r["type"] or "context", []).append(r)

    from memanto.app.services.okf_export_service import OkfExportService

    # Anchor the exporter's agent-data dir under tmp_path so the bundle stays
    # inside the validated base while keeping the test hermetic.
    service = OkfExportService(exports_dir=tmp_path)
    result = service.write_okf_bundle(
        agent_id="demo-user",
        memories_by_type=by_type,
        output_dir=tmp_path / "out",
    )
    reloaded = load_okf_bundle(Path(result["output_path"]))
    assert len(reloaded["memories"]) == len(all_rows)
    assert result["total_memories"] == 13


def test_golden_qa_recall_after_migration(tmp_path):
    """The migrated bundle must retain every golden fact (no amnesia)."""
    from memanto.app.services.okf_export_service import OkfExportService

    all_rows = map_claude(load("claude")) + map_chatgpt(load("chatgpt"))
    by_type: dict[str, list[dict]] = {}
    for r in all_rows:
        by_type.setdefault(r["type"] or "context", []).append(r)
    service = OkfExportService(exports_dir=tmp_path)
    result = service.write_okf_bundle(
        agent_id="demo-user",
        memories_by_type=by_type,
        output_dir=tmp_path / "bundle",
    )
    bundle = load_okf_bundle(Path(result["output_path"]))
    corpus = "\n".join(
        (m.get("body") or m.get("content") or m.get("title") or "")
        for m in bundle["memories"]
    ).lower()
    golden_terms = [
        "dark",
        "xps",
        "friday",
        "sqlalchemy",
        "tests",
        "azure",
        "webhook",
        "stripe",
    ]
    for term in golden_terms:
        assert term in corpus, f"golden term lost after migration: {term}"
