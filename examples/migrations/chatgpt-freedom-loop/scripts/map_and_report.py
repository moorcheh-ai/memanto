#!/usr/bin/env python3
"""Offline map ChatGPT export → migration report + OKF sample (no API key)."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[4]

# Prefer this checkout over any older installed memanto package
import sys
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from memanto.cli.migrate.chatgpt_mapper import load_chatgpt_export, map_chatgpt

DATA = ROOT / "data" / "conversations.json"
REPORT = ROOT / "reports" / "migration_summary.md"
OKF = ROOT / "okf_sample"


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (s[:48] or "memory")


def write_okf(rows: list[dict]) -> None:
    memories = OKF / "memories"
    if memories.exists():
        for p in memories.rglob("*"):
            if p.is_file():
                p.unlink()
    for t in ("preference", "decision", "observation", "fact"):
        (memories / t).mkdir(parents=True, exist_ok=True)

    index_lines = [
        "---",
        "okf_version: \"0.1\"",
        "title: ChatGPT Freedom Loop Sample",
        f"generated: {datetime.now(timezone.utc).isoformat()}",
        "source: chatgpt",
        "---",
        "",
        "# ChatGPT → Memanto OKF Sample",
        "",
        "Human-inspectable portable memories liberated from a ChatGPT export.",
        "",
        "## Memories",
        "",
    ]

    for i, row in enumerate(rows):
        mtype = row.get("type") or "fact"
        if mtype not in ("preference", "decision", "observation", "fact"):
            mtype = "fact"
        title = row.get("title") or f"memory-{i}"
        slug = _slug(title)
        path = memories / mtype / f"{slug}.md"
        created = row.get("created_at")
        updated = row.get("updated_at")
        created_s = created.isoformat() if hasattr(created, "isoformat") else str(created or "")
        updated_s = updated.isoformat() if hasattr(updated, "isoformat") else str(updated or "")
        tags = row.get("tags") or []
        body = row.get("content") or ""
        fm = [
            "---",
            f"title: {json.dumps(title)}",
            f"type: {mtype}",
            f"created: {created_s}",
            f"updated: {updated_s}",
            f"tags: {json.dumps(tags)}",
            "x_memanto:",
            f"  source: {row.get('source')}",
            f"  source_ref: {json.dumps(row.get('source_ref'))}",
            f"  provenance: {row.get('provenance')}",
            f"  confidence: {row.get('confidence')}",
            "---",
            "",
            body,
            "",
        ]
        path.write_text("\n".join(fm), encoding="utf-8")
        index_lines.append(f"- [{mtype}] [{title}](memories/{mtype}/{path.name})")

    (OKF / "index.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")


def main() -> None:
    if not DATA.exists():
        from generate_sample_export import main as gen

        gen()

    export = load_chatgpt_export(DATA)
    rows = map_chatgpt(export)
    by_type = Counter((r.get("type") or "auto") for r in rows)

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Migration Summary — ChatGPT Freedom Loop",
        "",
        f"- Generated: `{datetime.now(timezone.utc).isoformat()}`",
        f"- Source file: `{DATA}`",
        f"- Source conversations: **{len(export.get('conversations', []))}**",
        f"- Mapped memories: **{len(rows)}**",
        "",
        "## Type breakdown",
        "",
        "| Type | Count |",
        "|------|------:|",
    ]
    for k, v in sorted(by_type.items()):
        lines.append(f"| {k} | {v} |")
    lines += [
        "",
        "## Fidelity notes",
        "",
        "- Temporal timestamps preserved from ChatGPT message `create_time`",
        "- `source_ref` format: `{conversation_id}:{message_id}`",
        "- Branching edits linearized via first-child path",
        "- Multimodal parts emit text + `[image]` markers",
        "",
        "## Next (live Memanto)",
        "",
        "```bash",
        "memanto migrate chatgpt --file ./data/conversations.json --dry-run --report",
        "memanto migrate chatgpt --file ./data/conversations.json",
        "memanto memory export --okf ./okf_live",
        "```",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    write_okf(rows)
    print(f"Mapped {len(rows)} memories")
    print(f"Wrote {REPORT}")
    print(f"Wrote OKF sample under {OKF}")


if __name__ == "__main__":
    main()
