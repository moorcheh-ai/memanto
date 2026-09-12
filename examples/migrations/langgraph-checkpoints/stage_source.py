"""Snapshot generated source artifacts into one immutable evidence run."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    if not args.database.is_file():
        raise FileNotFoundError(f"Source database not found: {args.database}")
    if not args.bundle.is_dir():
        raise FileNotFoundError(f"Source OKF bundle not found: {args.bundle}")
    staged_database = args.run_dir / "langgraph-checkpoints.sqlite"
    staged_bundle = args.run_dir / "langgraph-okf"
    if staged_database.exists() or staged_bundle.exists():
        raise FileExistsError("Source artifacts are already staged for this run")
    shutil.copy2(args.database, staged_database)
    shutil.copytree(args.bundle, staged_bundle)
    print(staged_database.resolve())
    print(staged_bundle.resolve())


if __name__ == "__main__":
    main()
