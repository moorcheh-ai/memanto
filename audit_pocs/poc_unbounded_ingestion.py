"""Demonstrate memory amplification from unconstrained Markdown ingestion.

This is a standalone model of the loader's ``rglob`` + ``read_text`` loop. It
never imports or changes production code. Use ``--size-mib`` to increase the
fixture size deliberately; the default is suitable for a local smoke test.
"""

from __future__ import annotations

import argparse
import tempfile
import tracemalloc
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size-mib", type=float, default=8.0)
    parser.add_argument("--depth", type=int, default=8)
    args = parser.parse_args()
    if args.size_mib <= 0 or args.depth < 1:
        parser.error("--size-mib must be positive and --depth must be >= 1")

    with tempfile.TemporaryDirectory(prefix="memanto-audit-") as temp_dir:
        root = Path(temp_dir) / "bundle"
        current = root
        for index in range(args.depth):
            current /= f"level-{index}"
        current.mkdir(parents=True)
        payload = "# oversized entry\n" + ("A" * (int(args.size_mib * 1024**2) - 18))
        (current / "deep.md").write_text(payload, encoding="utf-8")

        tracemalloc.start()
        loaded = []
        for file_path in root.rglob("*.md"):
            loaded.append(file_path.read_text(encoding="utf-8"))
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        print(f"fixture_bytes={len(payload.encode('utf-8'))}")
        print(f"files_loaded={len(loaded)}")
        print(f"tracemalloc_peak={peak} bytes")
        print("observation=the entire file is materialized before parsing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
