"""Tests for the ChatGPT account-export migration adapter."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from memanto.cli.migrate.chatgpt_export import (
    export_chatgpt_memories,
    load_conversations,
)
from memanto.cli.migrate.mappers import MAPPERS, map_chatgpt
from memanto.cli.migrate.okf_loader import load_okf_bundle
from memanto.cli.migrate.runner import source_count

FIXTURE = Path(__file__).resolve().parent / "fixtures_chatgpt_conversations.json"


def _fixture_export() -> dict:
    return export_chatgpt_memories(load_conversations(FIXTURE))


def test_load_conversations_returns_array():
    conversations = load_conversations(FIXTURE)
    assert isinstance(conversations, list)
    assert len(conversations) == 5


def test_load_conversations_rejects_non_array(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"mapping": {}}', encoding="utf-8")
    with pytest.raises(ValueError, match="expected a JSON array"):
        load_conversations(bad)


def test_load_conversations_filters_non_dict_entries(tmp_path):
    """Non-object entries in the array must not abort the export."""
    bad = tmp_path / "mixed.json"
    bad.write_text(
        json.dumps([{"id": "conv-a"}, "not-a-dict", None, 42, {"id": "conv-b"}]),
        encoding="utf-8",
    )
    conversations = load_conversations(bad)
    assert [c["id"] for c in conversations] == ["conv-a", "conv-b"]


def test_iso_timestamp_guards_out_of_range_epoch():
    """A corrupt epoch must not raise OverflowError; the raw value survives."""
    import importlib.util

    script = Path(__file__).resolve().parents[1] / "examples/migrations/chatgpt-okf/export_okf.py"
    spec = importlib.util.spec_from_file_location("chatgpt_okf_ts", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    assert module._iso_timestamp(1e20) == "1e+20"
    assert module._iso_timestamp(1710000000).startswith("2024-03-09")


def test_export_extracts_only_active_user_messages():
    export = _fixture_export()
    contents = [m["content"] for m in export["memories"]]
    assert len(contents) == 7
    # Dead branch message must not appear (it is not on the active thread).
    assert "old regenerated draft" not in " ".join(contents)
    # System message must not appear.
    assert "helpful assistant" not in " ".join(contents)
    # Assistant messages must not appear.
    assert "concise approach" not in " ".join(contents)
    # Empty-message conversation contributes nothing.
    assert not any("Empty messages" in m.get("id", "") for m in export["memories"])


def test_export_preserves_conversation_tags_and_timestamps():
    export = _fixture_export()
    trip = [
        m
        for m in export["memories"]
        if any("conversation:Trip planning" == t for t in m["tags"])
    ]
    assert trip
    assert all("chatgpt" in m["tags"] for m in trip)
    assert all(m["created_at"] is not None for m in trip)
    assert all(isinstance(m["id"], str) and ":" in m["id"] for m in trip)


def test_export_emits_chronological_order():
    """Memories within a conversation must be oldest-first (not reversed)."""
    export = _fixture_export()
    conv1 = [
        m
        for m in export["memories"]
        if m["id"].startswith("conv-1:")
    ]
    # conv-1 has node-1 (t=1710000000) then node-3 (t=1710000100).
    times = [m["created_at"] for m in conv1]
    assert times == sorted(times)
    assert conv1[0]["id"] == "conv-1:node-1"
    assert conv1[-1]["id"] == "conv-1:node-3"


def test_map_chatgpt_no_epoch_fallback_for_zero():
    """A 0/None/bool created_at must NOT become 1970-01-01."""
    rows = map_chatgpt(
        {"memories": [{"id": "x:1", "content": "hello", "created_at": 0}]}
    )
    assert rows[0]["created_at"] is None
    rows = map_chatgpt(
        {"memories": [{"id": "x:2", "content": "hello", "created_at": True}]}
    )
    assert rows[0]["created_at"] is None


def test_map_chatgpt_produces_valid_memanto_payloads():
    export = _fixture_export()
    rows = map_chatgpt(export)
    assert len(rows) == 7
    for row in rows:
        assert row["source"] == "chatgpt"
        assert row["provenance"] == "imported"
        assert row["type"] is None  # let the parsing service auto-classify
        assert row["title"]
        assert row["content"]
        assert "chatgpt" in row["tags"]
        assert isinstance(row["updated_at"], datetime)
        assert row["updated_at"].tzinfo is not None
        # conv-5:c-1 is the bool `create_time: true` fixture: a malformed
        # timestamp must map to None rather than a bogus 1970 datetime.
        if row["source_ref"] == "conv-5:c-1":
            assert row["created_at"] is None
        else:
            assert row["created_at"].tzinfo is not None
        assert 0.0 <= row["confidence"] <= 1.0


def test_map_chatgpt_source_ref_roundtrip():
    rows = map_chatgpt(_fixture_export())
    refs = {row["source_ref"] for row in rows}
    assert refs == {
        "conv-1:node-1",
        "conv-1:node-3",
        "conv-2:t-2",
        "conv-2:t-4",
        "conv-4:b-1",
        "conv-4:b-3",
        "conv-5:c-1",
    }


def test_map_chatgpt_handles_empty_export():
    assert map_chatgpt({"memories": []}) == []
    assert map_chatgpt({}) == []


def test_map_chatgpt_skips_empty_content():
    export = {"memories": [{"id": "x", "content": "  "}, {"id": "y", "content": ""}]}
    assert map_chatgpt(export) == []


def test_chatgpt_registered_in_mappers():
    assert MAPPERS["chatgpt"] is map_chatgpt


def test_source_count_chatgpt():
    export = _fixture_export()
    assert source_count("chatgpt", export) == len(export["memories"])


def test_exported_at_preserved_or_defaulted():
    export = export_chatgpt_memories([], exported_at="2026-08-26T00:00:00+00:00")
    assert export["exported_at"] == "2026-08-26T00:00:00+00:00"
    export2 = export_chatgpt_memories([])
    assert export2["exported_at"]


def test_export_serializable():
    export = _fixture_export()
    # The mapper must be able to consume whatever the exporter produced.
    json.dumps(export, ensure_ascii=False)
    assert isinstance(export["memories"], list)


def test_okf_bundle_roundtrip(tmp_path):
    """The examples/migrations/chatgpt-okf generator must feed memanto migrate okf."""
    import importlib.util

    script = Path(__file__).resolve().parents[1] / "examples/migrations/chatgpt-okf/export_okf.py"
    spec = importlib.util.spec_from_file_location("chatgpt_okf_export", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    write_okf_bundle = module.write_okf_bundle

    export = _fixture_export()
    out = tmp_path / "bundle"
    written = write_okf_bundle(export, out)
    assert len(written) == 4  # one file per conversation with exported memories

    from memanto.cli.migrate.mappers import map_okf

    bundle = load_okf_bundle(out)
    rows = map_okf(bundle)
    assert len(rows) == 7  # every memory round-trips losslessly
    contents = " ".join(r["content"] for r in rows)
    assert "allergic to peanuts" in contents


def test_okf_groups_by_conversation_id_not_title(tmp_path):
    """Two same-titled conversations must not cross-contaminate one file."""
    import importlib.util

    script = Path(__file__).resolve().parents[1] / "examples/migrations/chatgpt-okf/export_okf.py"
    spec = importlib.util.spec_from_file_location("chatgpt_okf_export2", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    export = {
        "memories": [
            {"id": "conv-a:1", "content": "memory A", "tags": ["chatgpt", "conversation:Untitled"]},
            {"id": "conv-b:1", "content": "memory B", "tags": ["chatgpt", "conversation:Untitled"]},
        ]
    }
    out = tmp_path / "bundle2"
    written = module.write_okf_bundle(export, out)
    assert len(written) == 2  # two separate files, not merged
    blobs = [p.read_text(encoding="utf-8") for p in written]
    assert any("memory A" in b for b in blobs)
    assert any("memory B" in b for b in blobs)


def test_okf_safe_component_neutralizes_path_traversal(tmp_path):
    """Malicious conversation ids must never escape the output directory."""
    import importlib.util

    script = Path(__file__).resolve().parents[1] / "examples/migrations/chatgpt-okf/export_okf.py"
    spec = importlib.util.spec_from_file_location("chatgpt_okf_export3", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    safe = module._safe_component("../../etc/passwd")
    assert "/" not in safe and ".." not in safe
    assert safe  # non-empty fallback

    export = {
        "memories": [
            {"id": "../../../evil:1", "content": "x", "tags": ["chatgpt", "conversation:Hijack"]}
        ]
    }
    out = tmp_path / "bundle3"
    written = module.write_okf_bundle(export, out)
    assert len(written) == 1
    # The file must live strictly inside the output memories dir.
    assert written[0].parent == (out / "memories")


def test_okf_handles_string_tags():
    """String tags must be normalized to a list, not iterated char-by-char."""
    import importlib.util

    script = Path(__file__).resolve().parents[1] / "examples/migrations/chatgpt-okf/export_okf.py"
    spec = importlib.util.spec_from_file_location("chatgpt_okf_export4", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    doc = module._render_mem_to_okf({"content": "hello", "tags": "chatgpt,conversation:X"})
    assert "tags" in doc
    # The rendered frontmatter must contain the full tag string as one entry.
    assert "- chatgpt,conversation:X" in doc


def test_okf_render_is_v02_layout():
    """Bundle frontmatter must follow OKF v0.2 (generated-at metadata)."""
    import importlib.util

    script = Path(__file__).resolve().parents[1] / "examples/migrations/chatgpt-okf/export_okf.py"
    spec = importlib.util.spec_from_file_location("chatgpt_okf_export5", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    doc = module._render_mem_to_okf(
        {
            "content": "prefer dark mode",
            "created_at": 1710000000,
            "source": "chatgpt",
        },
    )
    # v0.2 layout: okf_version + generated block, no legacy timestamp field.
    assert "okf_version: '0.2'" in doc or 'okf_version: "0.2"' in doc
    assert "generated:" in doc
    assert "by: process:chatgpt" in doc or "by: chatgpt" in doc
    assert "at:" in doc
    assert "timestamp:" not in doc


def test_export_prefers_current_node_over_newest_leaf():
    """When current_node is set, we must follow that branch, not the newest leaf."""
    export = _fixture_export()
    conv4_memories = [
        m for m in export["memories"]
        if m["id"].startswith("conv-4:")
    ]
    # conv-4 has current_node=b-3. The b-4 branch (newer leaf) must NOT appear.
    ids = [m["id"] for m in conv4_memories]
    assert "conv-4:b-4" not in ids, "Newer leaf (b-4) must not be exported when current_node=b-3"
    # b-3's content should appear
    contents = " ".join(m["content"] for m in conv4_memories)
    assert "light mode" in contents, "current_node branch content must be exported"
    # b-1's content should NOT appear (it's a parent, not user message... wait, b-1 is user)
    # Actually b-1 IS a user message on the active branch path, so it should appear
    assert "dark mode in all my apps" in contents, "Parent user message on current_node branch must be included"


def test_export_handles_bool_create_time():
    """A message with create_time=True must not crash or produce a 1970 timestamp."""
    export = _fixture_export()
    conv5 = [m for m in export["memories"] if m["id"].startswith("conv-5:")]
    assert len(conv5) == 1
    # created_at must be None (not 1)
    assert conv5[0]["created_at"] is None, "bool create_time must map to None, not 1"


def test_export_falls_back_to_newest_leaf_when_no_current_node():
    """Without current_node, the original newest-leaf logic must still work."""
    export = _fixture_export()
    conv1 = [m for m in export["memories"] if m["id"].startswith("conv-1:")]
    # conv-1 has no current_node, should pick the newest leaf (node-4 is the end of the chain)
    # node-5 is a dead branch (older), node-4 is the newest leaf
    assert len(conv1) == 2
    assert "concise PR summaries" in conv1[0]["content"]
    assert "Python 3.12" in conv1[1]["content"]
