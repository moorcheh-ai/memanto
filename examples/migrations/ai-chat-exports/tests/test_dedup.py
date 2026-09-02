import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pathlib import Path

from core.dedup import collect_existing_refs, dedupe_entities
from core.models import MemoryEntity, MemoryType


def _entity(source_ref: str) -> MemoryEntity:
    return MemoryEntity(
        source_type=MemoryType.CONTEXT,
        title=source_ref,
        content="body",
        source_ref=source_ref,
    )


def test_collect_existing_refs_skips_index_and_parses_resource(tmp_path: Path):
    cdir = tmp_path / "memories" / "context"
    cdir.mkdir(parents=True)
    (cdir / "index.md").write_text("# index", encoding="utf-8")
    (cdir / "a.md").write_text(
        "---\ntype: context\nresource: claude://conversation/aaa\n---\n# A\nbody\n",
        encoding="utf-8",
    )
    (cdir / "b.md").write_text(
        "---\nresource: claude://conversation/bbb\n---\n# B\nbody\n",
        encoding="utf-8",
    )
    refs = collect_existing_refs(tmp_path)
    assert refs == {"claude://conversation/aaa", "claude://conversation/bbb"}


def test_dedupe_entities_keeps_new_and_skips_known():
    entities = [
        _entity("claude://conversation/aaa"),
        _entity("claude://conversation/bbb"),
        _entity("claude://conversation/ccc"),
    ]
    keep, skipped = dedupe_entities(entities, {"claude://conversation/aaa"})
    assert [e.source_ref for e in keep] == [
        "claude://conversation/bbb",
        "claude://conversation/ccc",
    ]
    assert [e.source_ref for e in skipped] == ["claude://conversation/aaa"]


def test_dedupe_entities_entity_without_ref_is_kept():
    entity = MemoryEntity(source_type=MemoryType.CONTEXT, title="no-ref", content="x")
    keep, skipped = dedupe_entities([entity], {"anything"})
    assert keep == [entity]
    assert skipped == []
