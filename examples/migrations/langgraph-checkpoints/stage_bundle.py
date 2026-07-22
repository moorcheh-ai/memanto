"""Copy an exported OKF bundle into an immutable evidence run directory."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    if not args.source.is_dir():
        raise FileNotFoundError(f"Exported OKF bundle not found: {args.source}")
    if args.destination.exists():
        raise FileExistsError(f"Evidence destination already exists: {args.destination}")
    shutil.copytree(args.source, args.destination)
    print(args.destination.resolve())


if __name__ == "__main__":
    main()
