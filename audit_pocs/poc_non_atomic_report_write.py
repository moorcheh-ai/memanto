"""Demonstrate readers observing a direct-truncation report write."""

from __future__ import annotations

import argparse
import tempfile
import threading
from pathlib import Path


def main() -> int:
    """Demonstrate non-atomic file replacement allowing intermediate empty reads.

    Returns:
        Exit code indicating success (0).
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--size-kib", type=int, default=256)
    args = parser.parse_args()
    if args.size_kib < 1:
        parser.error("--size-kib must be positive")

    with tempfile.TemporaryDirectory(prefix="memanto-audit-") as temp_dir:
        report = Path(temp_dir) / "migrate-report.md"
        old_content = "# complete report\n" + ("old\n" * 100)
        new_content = "# replacement report\n" + ("new\n" * (args.size_kib * 1024 // 4))
        report.write_text(old_content, encoding="utf-8")
        truncated = threading.Event()
        read_complete = threading.Event()
        observed: dict[str, object] = {}

        def reader() -> None:
            """Inspect target file concurrently during the in-place truncation window."""
            truncated.wait()
            raw = report.read_text(encoding="utf-8")
            observed["empty"] = not raw
            try:
                observed["valid"] = raw.startswith("# replacement report\n")
            except AttributeError:
                observed["valid"] = False
            observed["bytes"] = len(raw.encode("utf-8"))
            read_complete.set()

        thread = threading.Thread(target=reader)
        thread.start()
        with report.open("w", encoding="utf-8") as handle:
            handle.truncate(0)
            truncated.set()
            read_complete.wait()
            handle.write(new_content)
            handle.flush()
        thread.join()

        print(f"reader_observed_empty={observed['empty']}")
        print(f"reader_observed_complete_replacement={observed['valid']}")
        print(f"reader_bytes={observed['bytes']}")
        print("observation=direct truncation exposes an intermediate state")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
