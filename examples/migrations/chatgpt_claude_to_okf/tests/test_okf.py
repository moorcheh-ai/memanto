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
