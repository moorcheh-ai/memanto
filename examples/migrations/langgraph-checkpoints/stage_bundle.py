"""Copy an exported OKF bundle into an immutable evidence run directory."""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path


def normalize_exported_markdown(bundle: Path) -> None:
    """Normalize Memanto's generated Markdown for portable committed evidence."""
    for path in bundle.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        text = re.sub(
            r"(?m)^((?:> )?- OKF source: )(.*)$",
            lambda match: match.group(1) + match.group(2).replace("\\", "/"),
            text,
        )
        if path.name == "overview.md" and path.parent.name == "metrics":
            lines = text.splitlines(keepends=True)
            in_fence = False
            for index, line in enumerate(lines):
                if not in_fence:
                    fence = line.rstrip("\r\n")
                    if not fence.startswith("```"):
                        continue
                    if fence == "```":
                        ending = line[len(fence) :]
                        lines[index] = f"```text{ending}"
                    in_fence = True
                elif line.rstrip("\r\n") == "```":
                    in_fence = False
            text = "".join(lines)
        if path.parent.name == "sessions":
            text = re.sub(r"(?m)^### ", "## ", text)
        path.write_text(text, encoding="utf-8")


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
    normalize_exported_markdown(args.destination)
    print(args.destination.resolve())


if __name__ == "__main__":
    main()
