from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapter import adapt
from seed_graphiti import build_offline_export, load_fixture

FM = re.compile(r"^---\n.*?\nokf_version: \"0\.2\"", re.M | re.S)


def test_root_index_declares_okf_version(tmp_path: Path):
    export = build_offline_export(load_fixture())
    okf = tmp_path / "okf"
    adapt(export, okf)
    text = (okf / "index.md").read_text()
    assert 'okf_version: "0.2"' in text or "okf_version: '0.2'" in text or "okf_version: 0.2" in text
    # every memory has type frontmatter
    for path in (okf / "memories").rglob("*.md"):
        if path.name == "index.md":
            continue
        body = path.read_text()
        assert body.startswith("---")
        assert "\ntype:" in body or body.splitlines()[1].startswith("type:")
