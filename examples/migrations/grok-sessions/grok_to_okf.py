#!/usr/bin/env python3
"""Convert a Grok Build TUI session (and optional MEMORY.md) into an OKF v0.2 bundle.

Grok stores agent memory on disk: session JSONL, summary.json, goal plans, and
~/.grok/memory/MEMORY.md. This adapter maps those files onto portable markdown
so `memanto migrate okf` can ingest them. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

OKF_VERSION = "0.2"
# Must match memanto.app.constants.VALID_MEMORY_TYPES so migrate okf does not
# fall through to auto-classification.
MEMANTO_TYPES = frozenset(
    {
        "fact",
        "preference",
        "goal",
        "decision",
        "artifact",
        "learning",
        "event",
        "instruction",
        "relationship",
        "context",
        "observation",
        "commitment",
        "error",
    }
)

SECRET_RE = re.compile(
    r"("
    r"mj_live_[A-Za-z0-9]+"
    r"|ot_art_[A-Za-z0-9_-]+"
    r"|eyJ[A-Za-z0-9._-]{20,}"
    r"|sk-[A-Za-z0-9_-]{8,}"
    r"|ak_[A-Za-z0-9_-]{8,}"
    r"|tq_[A-Za-z0-9_-]{8,}"
    r"|fr_agent_[A-Za-z0-9_-]+"
    r"|gho_[A-Za-z0-9]+"
    r"|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    r")",
    re.IGNORECASE,
)
USER_QUERY_RE = re.compile(r"<user_query>\s*(.*?)\s*</user_query>", re.DOTALL)
SLUG_RE = re.compile(r"[^a-z0-9]+")


def redact(text: str) -> str:
    """Replace emails and token-shaped strings with a placeholder."""
    return SECRET_RE.sub("[REDACTED]", text or "")


def slugify(title: str, fallback: str = "memory") -> str:
    """Turn a title into a filesystem-safe slug."""
    s = SLUG_RE.sub("-", title.lower()).strip("-")
    return (s[:80] or fallback).strip("-")


def now_iso() -> str:
    """UTC timestamp with second precision, `Z` suffix."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def public_leaf(path: str | Path | None) -> str:
    """Keep only the last path component so live exports do not leak home dirs."""
    if not path:
        return ""
    name = Path(str(path).replace("\\", "/")).name
    return redact(name)


def yaml_escape(value: str) -> str:
    """Quote a YAML scalar when it contains reserved characters."""
    value = value.replace("\n", " ").replace("\r", " ").strip()
    if any(c in value for c in ":#{}[]&*!|>'\"%@`"):
        return json.dumps(value, ensure_ascii=False)
    return value or '""'


def write_okf_doc(
    path: Path,
    *,
    mem_type: str,
    title: str,
    description: str,
    body: str,
    tags: list[str],
    generated_at: str,
    generated_by: str = "process:grok-to-okf",
    resource: str | None = None,
) -> None:
    """Write one OKF markdown document with redacted front matter and body."""
    if mem_type not in MEMANTO_TYPES:
        mem_type = "observation"
    title = redact(title)
    description = redact(description)
    body = redact(body)
    tags = [redact(t) for t in tags]
    resource = public_leaf(resource) if resource else None
    lines = [
        "---",
        f"type: {mem_type}",
        f"title: {yaml_escape(title)}",
        f"description: {yaml_escape(description)}",
        "tags: [" + ", ".join(yaml_escape(t) for t in tags) + "]",
        "generated:",
        f"  by: {yaml_escape(generated_by)}",
        f"  at: {generated_at}",
    ]
    if resource:
        lines.append(f"resource: {yaml_escape(resource)}")
    lines.extend(
        [
            "x_memanto:",
            f"  type: {mem_type}",
            "  provenance: grok_session_export",
            "  source: grok-build-tui",
            "---",
            "",
            body.strip() or description,
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def extract_text(content) -> str:
    """Flatten Grok JSONL content (string, list of parts, or dict) to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    if isinstance(content, dict):
        return str(content.get("text") or "")
    return ""


def user_queries_from_jsonl(path: Path, limit: int = 40) -> list[str]:
    """Collect operator `<user_query>` lines, skipping compaction dumps."""
    if not path.is_file():
        return []
    found: list[str] = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("synthetic_reason") in {"compaction_meta", "system_reminder"}:
                continue
            if rec.get("type") != "user":
                continue
            text = extract_text(rec.get("content"))
            queries = USER_QUERY_RE.findall(text)
            candidates = queries or ([text] if text and "<user_info>" not in text[:200] else [])
            for q in candidates:
                q = redact(q.strip())
                if len(q) < 8 or q.startswith("<system-reminder>"):
                    continue
                found.append(q[:500])
                if len(found) >= limit:
                    return found
    return found


def parse_memory_md(path: Path) -> list[dict]:
    """Parse MEMORY.md sections into typed memory dicts.

    The first table row after a heading is treated as a header (PT or EN)
    and is not emitted as a fact.
    """
    if not path.is_file():
        return []
    text = redact(path.read_text(encoding="utf-8", errors="replace"))
    section = "general"
    items: list[dict] = []
    seen_table_row = False
    type_for_section = {
        "preferências": "preference",
        "preferences": "preference",
        "mapa de trabalho": "fact",
        "work map": "fact",
        "padrões que voltam": "observation",
        "recurring patterns": "observation",
    }
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("## "):
            section = line[3:].strip().lower()
            seen_table_row = False
            continue
        if line.startswith("|") and set(line.replace("|", "").replace("-", "").replace(":", "").strip()) == set():
            continue
        if line.startswith("|") and "---" not in line:
            cells = [c.strip() for c in line.strip("|").split("|")]
            if not seen_table_row:
                seen_table_row = True
                continue
            if len(cells) >= 2 and cells[0] and cells[1]:
                items.append(
                    {
                        "type": type_for_section.get(section, "fact"),
                        "title": cells[0][:80],
                        "body": f"{cells[0]} → {cells[1]}",
                        "tags": ["memory-md", "map"],
                    }
                )
            continue
        if line.startswith("- "):
            body = line[2:].strip()
            if len(body) < 8:
                continue
            items.append(
                {
                    "type": type_for_section.get(section, "observation"),
                    "title": body[:80],
                    "body": body,
                    "tags": ["memory-md", section.replace(" ", "-")[:40]],
                }
            )
    return items


def load_summary(session_dir: Path) -> dict:
    """Load summary.json, or {} if missing or invalid."""
    p = session_dir / "summary.json"
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def load_goal(session_dir: Path) -> dict:
    """Load goal/state.json, or {} if missing or invalid."""
    p = session_dir / "goal" / "state.json"
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def plan_deviations(session_dir: Path) -> list[str]:
    """Return redacted bullets under `## Deviations` in plan.md."""
    p = session_dir / "goal" / "plan.md"
    if not p.is_file():
        return []
    text = p.read_text(encoding="utf-8", errors="replace")
    if "## Deviations" not in text:
        return []
    tail = text.split("## Deviations", 1)[1]
    items = []
    for line in tail.splitlines():
        if line.startswith("## "):
            break
        if line.startswith("- "):
            items.append(redact(line[2:].strip()))
    return items


def memories_from_session(session_dir: Path, generated_at: str | None = None) -> list[dict]:
    """Map one Grok session directory onto episode/goal/decision/observation records."""
    summary = load_summary(session_dir)
    goal = load_goal(session_dir)
    created = generated_at or (summary.get("created_at") or now_iso())[:32]
    title = redact(summary.get("generated_title") or summary.get("session_summary") or session_dir.name)
    cwd_leaf = public_leaf((summary.get("info") or {}).get("cwd"))
    workspace_bit = f" Workspace leaf: `{cwd_leaf}`." if cwd_leaf else ""
    memories: list[dict] = [
        {
            "type": "event",
            "title": f"Grok session: {title}",
            "body": (
                f"Session `{public_leaf(session_dir)}` ran as `{summary.get('agent_name') or 'grok'}` "
                f"on `{summary.get('current_model_id') or 'unknown-model'}`. "
                f"Messages: {summary.get('num_messages')}. "
                f"Chat turns: {summary.get('num_chat_messages')}.{workspace_bit}"
            ),
            "tags": ["grok", "session", "event"],
            "at": created,
            "resource": "summary.json",
        }
    ]
    obj = redact(str(goal.get("objective") or ""))
    if obj:
        memories.append(
            {
                "type": "goal",
                "title": "Active goal objective (redacted)",
                "body": obj[:800],
                "tags": ["grok", "goal"],
                "at": created,
            }
        )
    for i, dev in enumerate(plan_deviations(session_dir)[:12], 1):
        memories.append(
            {
                "type": "decision",
                "title": f"Plan deviation {i}",
                "body": dev,
                "tags": ["grok", "plan", "deviation"],
                "at": created,
            }
        )
    queries = user_queries_from_jsonl(session_dir / "chat_history.jsonl")
    for i, q in enumerate(queries[:20], 1):
        memories.append(
            {
                "type": "observation",
                "title": f"Operator request {i}: {q[:60]}",
                "body": q,
                "tags": ["grok", "user-query"],
                "at": created,
            }
        )
    return memories


def _emit_bundle(out_dir: Path, memories: list[dict], stamp: str) -> dict:
    """Write indexes and documents into an empty directory. Does not replace `out_dir`."""
    out_dir.mkdir(parents=True, exist_ok=True)
    mem_root = out_dir / "memories"
    mem_root.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    written = 0
    used_slugs: set[str] = set()
    for mem in memories:
        mtype = mem["type"]
        counts[mtype] = counts.get(mtype, 0) + 1
        base = slugify(mem["title"], fallback=mtype)
        slug = base
        n = 2
        while slug in used_slugs:
            slug = f"{base}-{n}"
            n += 1
        used_slugs.add(slug)
        dest = mem_root / mtype / f"{slug}.md"
        write_okf_doc(
            dest,
            mem_type=mtype,
            title=mem["title"],
            description=mem["body"][:180],
            body=mem["body"],
            tags=mem.get("tags") or ["grok"],
            generated_at=mem.get("at") or stamp,
            resource=mem.get("resource"),
        )
        written += 1

    type_links = "\n".join(f"- `{k}`: {v}" for k, v in sorted(counts.items()))
    (out_dir / "index.md").write_text(
        "\n".join(
            [
                "---",
                f'okf_version: "{OKF_VERSION}"',
                "title: Grok Build TUI memory export",
                "generated:",
                "  by: process:grok-to-okf",
                f"  at: {stamp}",
                "---",
                "",
                "# Grok Build TUI → OKF",
                "",
                "Portable memories extracted from Grok Build TUI session files and MEMORY.md.",
                "",
                "## Counts",
                "",
                type_links or "- (empty)",
                "",
                f"Total documents: {written}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (mem_root / "index.md").write_text(
        f"---\nokf_version: \"{OKF_VERSION}\"\ntype: index\n---\n\n# Memories\n\n{type_links or '- (empty)'}\n",
        encoding="utf-8",
    )
    for mtype, n in counts.items():
        (mem_root / mtype / "index.md").write_text(
            f"---\ntype: index\n---\n\n# {mtype}\n\n{n} documents.\n",
            encoding="utf-8",
        )
    return {"written": written, "by_type": counts}


def write_bundle(out_dir: Path, memories: list[dict], generated_at: str | None = None) -> dict:
    """Write a complete bundle, replacing any previous files in `out_dir` atomically."""
    stamp = generated_at or now_iso()
    out_dir = out_dir.resolve()
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="okf-bundle-", dir=str(out_dir.parent)))
    try:
        stats = _emit_bundle(tmp, memories, stamp)
        if out_dir.exists():
            shutil.rmtree(out_dir)
        shutil.copytree(tmp, out_dir)
        return stats
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def collect(
    session: Path | None,
    memory_md: Path | None,
    generated_at: str | None = None,
) -> list[dict]:
    """Gather memories from MEMORY.md and/or a session directory."""
    stamp = generated_at or now_iso()
    memories: list[dict] = []
    if memory_md:
        for item in parse_memory_md(memory_md):
            item.setdefault("at", stamp)
            memories.append(item)
    if session:
        memories.extend(memories_from_session(session, generated_at=stamp if generated_at else None))
    return memories


def main(argv: list[str] | None = None) -> int:
    """CLI entry: `--session` and/or `--memory` into `--out`."""
    p = argparse.ArgumentParser(description="Grok session/MEMORY.md → OKF v0.2")
    p.add_argument("--session", type=Path, help="Path to a Grok session directory")
    p.add_argument("--memory", type=Path, help="Path to MEMORY.md")
    p.add_argument("--out", type=Path, required=True, help="Output OKF bundle directory")
    p.add_argument(
        "--generated-at",
        default=None,
        help="Fixed UTC timestamp for generated.at (keeps checked-in samples stable)",
    )
    args = p.parse_args(argv)
    if not args.session and not args.memory:
        print("provide --session and/or --memory", file=sys.stderr)
        return 2
    memories = collect(args.session, args.memory, generated_at=args.generated_at)
    stats = write_bundle(args.out, memories, generated_at=args.generated_at)
    print(json.dumps({"ok": True, **stats, "out": str(args.out)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
