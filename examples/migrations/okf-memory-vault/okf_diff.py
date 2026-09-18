"""okf_diff.py - Human-readable diff for OKF memory bundles.

The Path C pitch: once memory is portable markdown, you can diff it like code.
This utility compares two OKF bundle snapshots (or the same bundle at two git
revisions) and prints:

  * a per-type change summary,
  * added / modified / removed memories with field-level before -> after,
  * a *conflict scan* that flags near-duplicate memories which contradict each
    other (two agents disagreeing, a correction that never got merged, ...).

Usage:

    python okf_diff.py <old_bundle> <new_bundle>
    python okf_diff.py --git <repo_dir> <old_rev> <new_rev> --bundle okf
    python okf_diff.py --json <old_bundle> <new_bundle>

The diff is intentionally markdown-first: it is meant to be read by humans in
a code review, pasted into a PR description, or rendered in a docs site.
"""

from __future__ import annotations

import argparse
import difflib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from okf_bundle import MEMORY_TYPE_ORDER, Memory, all_memories, load_bundle

# ---------------------------------------------------------------------------
# Diff core
# ---------------------------------------------------------------------------


def _mem_key(mem: Memory) -> tuple[str, str]:
    return (mem.type, mem.slug)


def _similar(a: str, b: str, cutoff: float = 0.62) -> bool:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() >= cutoff


def _field_lines(mem: Memory) -> list[str]:
    """Render the comparable fields of a memory as lines."""
    lines = [f"title: {mem.title}"]
    if mem.description:
        lines.append(f"description: {mem.description}")
    if mem.resource:
        lines.append(f"resource: {mem.resource}")
    if mem.tags:
        lines.append(f"tags: {', '.join(mem.tags)}")
    if mem.timestamp:
        lines.append(f"timestamp: {mem.timestamp}")
    if mem.x_memanto:
        lines.append(f"x_memanto: {json.dumps(mem.x_memanto, sort_keys=True)}")
    lines.append("body:")
    lines.extend(f"    {l}" if l else "" for l in mem.body.splitlines())
    return lines


def diff_bundles(old_dir: str | Path, new_dir: str | Path) -> dict:
    """Compute a structured diff between two OKF bundles."""
    old_mems = {_mem_key(m): m for m in all_memories(old_dir)}
    new_mems = {_mem_key(m): m for m in all_memories(new_dir)}

    old_keys, new_keys = set(old_mems), set(new_mems)
    added_keys = sorted(new_keys - old_keys, key=lambda k: MEMORY_TYPE_ORDER.index(k[0]) if k[0] in MEMORY_TYPE_ORDER else 99)
    removed_keys = sorted(old_keys - new_keys, key=lambda k: MEMORY_TYPE_ORDER.index(k[0]) if k[0] in MEMORY_TYPE_ORDER else 99)
    common_keys = sorted(old_keys & new_keys, key=lambda k: MEMORY_TYPE_ORDER.index(k[0]) if k[0] in MEMORY_TYPE_ORDER else 99)

    added = [new_mems[k] for k in added_keys]
    removed = [old_mems[k] for k in removed_keys]

    modified: list[dict] = []
    unchanged = 0
    for k in common_keys:
        old_m, new_m = old_mems[k], new_mems[k]
        if old_m == new_m:
            unchanged += 1
            continue
        old_lines = _field_lines(old_m)
        new_lines = _field_lines(new_m)
        unified = list(
            difflib.unified_diff(old_lines, new_lines, lineterm="", n=2)
        )
        modified.append(
            {
                "type": k[0],
                "slug": k[1],
                "old_title": old_m.title,
                "new_title": new_m.title,
                "diff_lines": unified,
            }
        )

    # --- conflict scan -----------------------------------------------------
    # Near-duplicate titles inside the *new* bundle with different content are
    # the signature of two sources disagreeing. Flag them for human review.
    conflicts: list[dict] = []
    all_new = all_memories(new_dir)
    for i in range(len(all_new)):
        for j in range(i + 1, len(all_new)):
            a, b = all_new[i], all_new[j]
            if a.type != b.type:
                continue
            if _similar(a.title, b.title) and a.slug != b.slug:
                prov_a = a.x_memanto.get("provenance", "unknown")
                prov_b = b.x_memanto.get("provenance", "unknown")
                conflicts.append(
                    {
                        "type": a.type,
                        "a": {"title": a.title, "provenance": prov_a},
                        "b": {"title": b.title, "provenance": prov_b},
                    }
                )

    return {
        "old_bundle": str(old_dir),
        "new_bundle": str(new_dir),
        "counts": {
            "added": len(added),
            "modified": len(modified),
            "removed": len(removed),
            "unchanged": unchanged,
        },
        "added": [
            {"type": m.type, "title": m.title, "provenance": m.x_memanto.get("provenance", "")}
            for m in added
        ],
        "removed": [
            {"type": m.type, "title": m.title, "provenance": m.x_memanto.get("provenance", "")}
            for m in removed
        ],
        "modified": modified,
        "conflicts": conflicts,
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_markdown(diff: dict) -> str:
    lines: list[str] = []
    c = diff["counts"]

    lines.append(f"# OKF bundle diff: `{Path(diff['old_bundle']).name}` → `{Path(diff['new_bundle']).name}`")
    lines.append("")
    lines.append(
        f"**{c['added']} added · {c['modified']} modified · {c['removed']} removed · "
        f"{c['unchanged']} unchanged**"
    )
    if c["added"] == c["modified"] == c["removed"] == 0:
        lines.append("")
        lines.append("_No changes._")
        return "\n".join(lines)

    lines.append("")
    lines.append("## Added")
    if c["added"]:
        for item in diff["added"]:
            prov = f"  _(via {item['provenance']})_" if item["provenance"] else ""
            lines.append(f"- **{item['title']}** `{item['type']}`{prov}")
    else:
        lines.append("_none_")

    lines.append("")
    lines.append("## Modified")
    if c["modified"]:
        for m in diff["modified"]:
            lines.append("")
            lines.append(f"### `{m['type']}/{m['slug']}`")
            if m["old_title"] != m["new_title"]:
                lines.append(f"- old title: {m['old_title']}")
                lines.append(f"- new title: {m['new_title']}")
            lines.append("")
            lines.append("```diff")
            lines.extend(m["diff_lines"])
            lines.append("```")
    else:
        lines.append("")
        lines.append("_none_")

    lines.append("")
    lines.append("## Removed")
    if c["removed"]:
        for item in diff["removed"]:
            prov = f"  _(via {item['provenance']})_" if item["provenance"] else ""
            lines.append(f"- **{item['title']}** `{item['type']}`{prov}")
    else:
        lines.append("_none_")

    lines.append("")
    lines.append("## Potential conflicts (near-duplicate memories)")
    if diff["conflicts"]:
        lines.append("")
        lines.append("> Two memories of the same type look like they may be about the same thing")
        lines.append("> but disagree. **Flag for human review** - this is exactly what a vector")
        lines.append("> store would have silently collapsed.")
        lines.append("")
        for cf in diff["conflicts"]:
            lines.append(
                f"- `{cf['type']}`: **{cf['a']['title']}** "
                f"(_via {cf['a']['provenance']}_) ⟷ **{cf['b']['title']}** "
                f"(_via {cf['b']['provenance']}_)"
            )
    else:
        lines.append("")
        lines.append("_none - the vault is consistent._")

    return "\n".join(lines)


def render_json(diff: dict) -> str:
    return json.dumps(diff, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _extract_git_bundle(repo: str, rev: str, bundle_rel: str) -> Path:
    """Check out a bundle path at a git revision into a temp dir."""
    tmp = Path(tempfile.mkdtemp(prefix="okf-diff-"))
    dest = tmp / rev
    dest.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "-C", repo, "archive", rev, bundle_rel],
        check=True,
        stdout=open(tmp / "bundle.tar", "wb"),
    )
    subprocess.run(
        ["tar", "-xf", str(tmp / "bundle.tar"), "-C", str(dest), "--strip-components=1"],
        check=True,
    )
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("old", nargs="?", help="old OKF bundle directory")
    parser.add_argument("new", nargs="?", help="new OKF bundle directory")
    parser.add_argument("--git", action="store_true", help="compare git revisions")
    parser.add_argument("--repo", default=".", help="git repo (with --git)")
    parser.add_argument("--bundle", default="okf", help="bundle path inside repo (with --git)")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of markdown")
    args = parser.parse_args(argv)

    if args.git:
        if not args.old or not args.new:
            parser.error("--git requires OLD_REV and NEW_REV")
        old_dir = _extract_git_bundle(args.repo, args.old, args.bundle)
        new_dir = _extract_git_bundle(args.repo, args.new, args.bundle)
    else:
        if not args.old or not args.new:
            parser.error("expected OLD_BUNDLE and NEW_BUNDLE directories")
        old_dir, new_dir = Path(args.old), Path(args.new)

    diff = diff_bundles(old_dir, new_dir)
    print(render_json(diff) if args.json else render_markdown(diff))
    return 0


if __name__ == "__main__":
    sys.exit(main())
