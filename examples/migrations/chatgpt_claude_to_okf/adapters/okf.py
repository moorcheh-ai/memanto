"""Write an OKF bundle (Open Knowledge Format, Google Cloud spec-aligned)
in the layout the Memanto CLI consumes:

    bundle/
    ├── index.md                      # navigation for the whole bundle
    ├── memories/
    │   ├── index.md
    │   └── <type>/
    │       ├── index.md
    │       └── <slug>.md             # frontmatter + body per memory
    ├── sessions/                     # per-conversation provenance logs
    └── metrics/
        └── overview.md               # counts + ASCII visualization

Each memory file carries OKF frontmatter: type, title, description, tags,
timestamp, resource, and x_memanto (confidence, provenance, source, type) —
the exact fields `memanto migrate okf` reads back.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections import Counter
from pathlib import Path

FRONTMATTER_FIELDS = ("type", "title", "description", "tags", "timestamp", "resource", "x_memanto")


def _fmt_frontmatter(memory: dict) -> str:
    lines = ["---"]
    for key in FRONTMATTER_FIELDS:
        value = memory.get(key)
        if value is None or value == "":
            continue
        if key == "tags":
            lines.append(f"tags: {json.dumps(value, ensure_ascii=False)}")
        elif key == "x_memanto":
            inner = ", ".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in value.items())
            lines.append(f"x_memanto:\n  {{{inner}}}")
        else:
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines)


def _slug(s: str, max_len: int = 48) -> str:
    import re
    s = re.sub(r"[^a-z0-9\u00c0-\u1ef9]+", "-", s.lower()).strip("-")
    return s[:max_len].rstrip("-") or "memory"


def _plural(text: str, count: int) -> str:
    if count == 1:
        return text.replace(" memories", " memory")
    return text


def _type_index(types: list[str], counts: Counter) -> str:
    lines = ["# Memories by type", ""]
    for t in sorted(set(types)):
        lines.append(f"- [{t}/]({t}/) — {counts.get(t, 0)}")
    return "\n".join(lines) + "\n"


def write_bundle(memories: list[dict], sessions: list[dict], stats: dict,
                 out_dir: str | Path, bundle_name: str = "okf-bundle") -> dict:
    """Write the bundle atomically: build in a temp dir, then swap into place.

    The previous bundle at out_dir is only replaced after the new one has been
    fully written — a failure mid-write never destroys the existing bundle, and
    the final directory is guaranteed clean (no stale files from earlier runs).
    """
    out = Path(out_dir)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{out.name}.tmp-", dir=out.parent))
    rollback: Path | None = None
    try:
        result = _write_bundle_contents(memories, sessions, stats, tmp, bundle_name)
        if out.exists():
            # Move the previous bundle aside instead of deleting it: if the
            # replacement fails, the prior valid bundle is restored.
            rollback = out.parent / f".{out.name}.old-{os.getpid()}"
            if rollback.exists():
                shutil.rmtree(rollback)
            os.replace(out, rollback)
        try:
            os.replace(tmp, out)
        except BaseException:
            if rollback is not None and not out.exists():
                os.replace(rollback, out)
            raise
        if rollback is not None:
            shutil.rmtree(rollback, ignore_errors=True)
        # _write_bundle_contents wrote into the temp dir — report the final,
        # live path, not the (now gone) temp location.
        result["bundle_dir"] = str(out)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return result


def _write_bundle_contents(memories: list[dict], sessions: list[dict], stats: dict,
                           out: Path, bundle_name: str) -> dict:
    memories_dir = out / "memories"
    sessions_dir = out / "sessions"
    metrics_dir = out / "metrics"
    for d in (memories_dir, sessions_dir, metrics_dir):
        d.mkdir(parents=True, exist_ok=True)

    by_type: dict[str, list[dict]] = {}
    for m in memories:
        by_type.setdefault(m["type"], []).append(m)

    counts = Counter(m["type"] for m in memories)
    type_files = {}

    # "index.md" is reserved: each type dir writes its own index, so a memory
    # whose slug collides with it must be disambiguated, never overwritten.
    used: set[str] = {"index.md"}
    for mem_type, items in by_type.items():
        tdir = memories_dir / mem_type
        tdir.mkdir(exist_ok=True)
        type_files[mem_type] = []
        for m in items:
            slug = _slug(m["title"])
            fname = f"{slug}.md"
            if fname in used:
                # 48-char slug truncation can collide — disambiguate instead
                # of silently overwriting an existing memory file.
                base, n = fname[:-3], 2
                while f"{base}-{n}.md" in used:
                    n += 1
                fname = f"{base}-{n}.md"
            used.add(fname)
            path = tdir / fname
            body = m["content"] + "\n"
            if m.get("resource"):
                body += f"\n<!-- source: {m['resource']} -->\n"
            path.write_text(_fmt_frontmatter(m) + "\n\n" + body, encoding="utf-8")
            type_files[mem_type].append(fname)
        (tdir / "index.md").write_text(
            _plural(f"# {mem_type}\n\n{len(items)} memories\n", len(items)), encoding="utf-8")

    (memories_dir / "index.md").write_text(_type_index(by_type.keys(), counts), encoding="utf-8")

    # sessions: provenance log per conversation
    session_files = []
    used_sessions: set[str] = set()
    for s in sessions:
        slug = _slug(s["title"])[:40]
        # digest of the FULL session id — first-8-char prefixes can collide
        digest = hashlib.md5(str(s["id"]).encode("utf-8")).hexdigest()[:8]
        fname = f"{slug}-{digest}.md"
        if fname in used_sessions:
            base, n = fname[:-3], 2
            while f"{base}-{n}.md" in used_sessions:
                n += 1
            fname = f"{base}-{n}.md"
        used_sessions.add(fname)
        lines = [
            f"# {s['title']}",
            "",
            f"- source: {s['source']}",
            f"- turns: {s['turns']}",
            f"- memories extracted: {len(s['memories'])}",
            f"- breakdown: {dict(Counter(s['memories']))}",
            "",
            "## Unmatched turns (junk / no memory signal)",
            "",
        ]
        for u in s.get("unmatched", []):
            lines.append(f"- {u[:140]}")
        (sessions_dir / fname).write_text("\n".join(lines) + "\n", encoding="utf-8")
        session_files.append(fname)

    # metrics overview with ASCII bars
    metrics = ["# Metrics", ""]
    if stats.get("total") is not None:
        metrics.append(f"- total memories: {stats['total']}")
        metrics.append(f"- conversations processed: {stats.get('conversations', 0)}")
        metrics.append(f"- turns processed: {stats.get('turns', 0)}")
        metrics.append("")
        metrics.append("## By type")
        metrics.append("")
        maxc = max(counts.values()) if counts else 1
        for t in sorted(counts, key=lambda x: -counts[x]):
            bar = "█" * max(1, round(counts[t] / maxc * 20))
            metrics.append(f"{t:<14} {bar} {counts[t]}")
    (metrics_dir / "overview.md").write_text("\n".join(metrics) + "\n", encoding="utf-8")

    # root index
    idx = [
        f"# {bundle_name}",
        "",
        "Portable memory bundle (OKF). Migrate with:",
        "",
        "```bash",
        "memanto migrate okf . --dry-run",
        "memanto migrate okf . --agent my-agent",
        "```",
        "",
        f"Total memories: {len(memories)}",
        "",
        "- [memories/](memories/)",
        "- [sessions/](sessions/)",
        "- [metrics/](metrics/)",
        "",
    ]
    (out / "index.md").write_text("\n".join(idx) + "\n", encoding="utf-8")

    return {
        "bundle_dir": str(out),
        "memories": len(memories),
        "by_type": dict(counts),
        "type_files": type_files,
        "sessions": len(session_files),
    }
