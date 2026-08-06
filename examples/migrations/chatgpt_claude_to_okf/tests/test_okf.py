"""Tests for the OKF bundle writer."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.extract import extract_memories  # noqa: E402
from adapters.okf import write_bundle  # noqa: E402

TURNS = [
    {"role": "user", "text": "I prefer Postgres over MySQL. We decided to migrate to Postgres 16.", "ts": 1},
    {"role": "user", "text": "My wife and I are planning a trip to Da Nang in October.", "ts": 2},
]
CONV = [{"id": "c1", "title": "Migration planning", "source": "chatgpt", "turns": TURNS}]


def test_bundle_layout(tmp_path):
    result = extract_memories(CONV)
    written = write_bundle(result["memories"], result["sessions"], result["stats"], tmp_path)
    assert (tmp_path / "index.md").is_file()
    assert (tmp_path / "memories" / "index.md").is_file()
    assert (tmp_path / "metrics" / "overview.md").is_file()
    assert written["memories"] == len(result["memories"])

    # every memory file exists and has valid frontmatter
    memory_files = list((tmp_path / "memories").rglob("*.md"))
    memory_files = [p for p in memory_files if p.name != "index.md"]
    assert len(memory_files) == len(result["memories"])
    for p in memory_files:
        head = p.read_text(encoding="utf-8").split("---")[1]
        for field in ("type:", "title:", "description:", "x_memanto:"):
            assert field in head, f"{field} missing in {p}"

    # sessions log present
    session_files = list((tmp_path / "sessions").glob("*.md"))
    assert len(session_files) == 1


def test_frontmatter_json_valid(tmp_path):
    import json as _json

    result = extract_memories(CONV)
    write_bundle(result["memories"], result["sessions"], result["stats"], tmp_path)
    for p in (tmp_path / "memories").rglob("*.md"):
        if p.name == "index.md":
            continue
        raw = p.read_text(encoding="utf-8")
        fm = raw.split("---")[1]
        for line in fm.splitlines():
            line = line.strip()
            if not line or line.startswith("x_memanto:"):
                continue
            key, _, val = line.partition(":")
            if key in ("tags",) and val.strip():
                _json.loads(val)  # must parse


def test_index_filename_reserved(tmp_path):
    """A memory whose slug is 'index' must not be overwritten by the type index."""
    turns = [
        {"role": "user", "text": "I prefer Postgres.", "ts": 1},
        {"role": "user", "text": "I prefer keeping an Index of my projects.", "ts": 2},
    ]
    conv = [{"id": "c1", "title": "Indexing", "source": "chatgpt", "turns": turns}]
    result = extract_memories(conv)
    # force a memory whose slug lands on 'index'
    result["memories"][0]["title"] = "Index"
    result["memories"][0]["type"] = "preference"
    write_bundle(result["memories"], result["sessions"], result["stats"], tmp_path)

    tdir = tmp_path / "memories" / "preference"
    index_md = tdir / "index.md"
    assert index_md.is_file() and index_md.read_text(encoding="utf-8").startswith("# preference")
    # the memory is preserved under a disambiguated name
    memory_file = tdir / "index-2.md"
    assert memory_file.is_file(), f"expected disambiguated {memory_file}"
    assert "Index" in memory_file.read_text(encoding="utf-8")


def test_bundle_dir_is_final_path(tmp_path):
    """bundle_dir must point at the live output dir, not the temp swap path."""
    result = extract_memories(CONV)
    written = write_bundle(result["memories"], result["sessions"], result["stats"], tmp_path)
    assert written["bundle_dir"] == str(tmp_path)
    assert Path(written["bundle_dir"]).is_dir()
    assert (Path(written["bundle_dir"]) / "index.md").is_file()


def test_bundle_replaces_previous_cleanly(tmp_path):
    """Regeneration swaps the whole dir — stray/stale files never survive."""
    result = extract_memories(CONV)
    write_bundle(result["memories"], result["sessions"], result["stats"], tmp_path)
    # plant a stale artifact from a hypothetical previous version
    (tmp_path / "stale-file.md").write_text("old", encoding="utf-8")
    (tmp_path / "memories" / "obsolete-type").mkdir(exist_ok=True)
    (tmp_path / "memories" / "obsolete-type" / "old.md").write_text("old", encoding="utf-8")

    # regenerate (fresh memories, no obsolete-type)
    write_bundle(result["memories"], result["sessions"], result["stats"], tmp_path)

    assert not (tmp_path / "stale-file.md").exists(), "stale root file survived"
    assert not (tmp_path / "memories" / "obsolete-type").exists(), "stale type dir survived"
    assert (tmp_path / "index.md").is_file()
    # no temp dirs left behind
    leftovers = list(tmp_path.parent.glob(f".{tmp_path.name}.tmp-*"))
    assert not leftovers, f"temp dirs left: {leftovers}"
