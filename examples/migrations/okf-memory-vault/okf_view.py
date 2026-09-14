"""okf_view.py - Browse and search an OKF memory bundle from the terminal.

A tiny read-only viewer for portable memory: list the vault as a tree, filter
by type or keyword, and read any single memory. The point is that *no special
tool* is needed to read what your agent remembers - just markdown and a few
lines of Python.

Usage:

    python okf_view.py <bundle>              # tree view
    python okf_view.py <bundle> --type fact  # only facts
    python okf_view.py <bundle> --search p95 # keyword search
    python okf_view.py <bundle> --open fact/maya-s-timezone-is-utc-7-pacific
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from okf_bundle import MEMORY_TYPE_ORDER, all_memories, load_bundle


def render_tree(bundle_dir: str | Path, only_type: str | None = None, search: str | None = None) -> str:
    by_type = load_bundle(bundle_dir)
    lines: list[str] = []
    total = 0
    for t in MEMORY_TYPE_ORDER:
        mems = by_type.get(t, [])
        if only_type and t != only_type:
            continue
        if not mems:
            continue
        mems = sorted(mems, key=lambda m: (m.timestamp, m.title))
        if search:
            mems = [m for m in mems if search.lower() in (m.title + "\n" + m.body + "\n" + " ".join(m.tags)).lower()]
        if not mems:
            continue
        lines.append(f"{t}/")
        for m in mems:
            lines.append(f"  {m.slug}.md  «{m.title}»")
            total += 1
    if search:
        lines.insert(0, f"# {total} memories matching '{search}' in {Path(bundle_dir).name}")
    else:
        lines.insert(0, f"# {total} memories in {Path(bundle_dir).name}")
    return "\n".join(lines)


def render_memory(bundle_dir: str | Path, key: str) -> str:
    """Open one memory by '<type>/<slug>' key."""
    mems = all_memories(bundle_dir)
    for m in mems:
        if f"{m.type}/{m.slug}" == key:
            return m.to_markdown().rstrip() + "\n"
    raise KeyError(f"memory not found: {key}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", help="OKF bundle directory")
    parser.add_argument("--type", help="filter by memory type")
    parser.add_argument("--search", help="keyword search across titles, bodies and tags")
    parser.add_argument("--open", help="open one memory by '<type>/<slug>'")
    args = parser.parse_args(argv)

    try:
        if args.open:
            print(render_memory(args.bundle, args.open))
        else:
            print(render_tree(args.bundle, only_type=args.type, search=args.search))
    except (FileNotFoundError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
