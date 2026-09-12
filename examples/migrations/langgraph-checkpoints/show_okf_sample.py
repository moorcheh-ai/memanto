"""Print one exported OKF memory as readable Markdown for the live demo."""

from __future__ import annotations

import argparse
from pathlib import Path


def select_memory_markdown(bundle: Path) -> Path:
    """Select a stable, non-index memory page, preferring a preference memory."""
    memories = bundle / "memories"
    preferred = sorted(
        path
        for path in (memories / "preference").glob("*.md")
        if path.name.casefold() != "index.md"
    )
    candidates = preferred or sorted(
        path
        for path in memories.glob("*/*.md")
        if path.name.casefold() != "index.md"
    )
    if not candidates:
        raise FileNotFoundError(f"No exported OKF memory Markdown found under {memories}")
    return candidates[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()

    sample = select_memory_markdown(args.bundle)
    print(f"Opening portable OKF Markdown: {sample.relative_to(args.bundle)}")
    print()
    print(sample.read_text(encoding="utf-8").rstrip())


if __name__ == "__main__":
    main()
