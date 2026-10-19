"""Demonstrate bundle ingestion following a link outside its root."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path


def main() -> int:
    """Demonstrate recursive bundle ingestion resolving external symbolic links.

    Returns:
        Exit code indicating success (0) or unavailable link permissions (2).
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-link", action="store_true")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="memanto-audit-") as temp_dir:
        base = Path(temp_dir)
        root = base / "bundle"
        outside = base / "outside-secret.md"
        root.mkdir()
        outside.write_text("# outside\nconfidential fixture\n", encoding="utf-8")
        link = root / "linked.md"
        try:
            link.symlink_to(outside, target_is_directory=False)
        except (OSError, NotImplementedError) as exc:
            print(f"link_creation=unavailable ({exc})")
            return 2 if args.require_link else 0

        candidates = list(root.rglob("*.md"))
        ingested = [path.read_text(encoding="utf-8") for path in candidates]
        escaped = [path for path in candidates if path.resolve().parent != root.resolve()]
        print(f"root={root}")
        print(f"candidate={link}")
        print(f"resolved_candidate={link.resolve()}")
        print(f"outside_content_ingested={'confidential fixture' in ''.join(ingested)}")
        print(f"path_escapes_root={bool(escaped)}")
        print(f"is_windows={os.name == 'nt'} (junctions require directory targets)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
