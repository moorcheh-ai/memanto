#!/usr/bin/env python3
"""AI Conversation Migration Demo — ChatGPT & Claude → Memanto → OKF Bundle

Standalone script that demonstrates the full migration pipeline without
requiring a Memanto server. Embeds the mapper logic from mappers.py.

Usage:
    python migrate.py --source chatgpt --export ./sample_data/chatgpt_export.json
    python migrate.py --source claude  --export ./sample_data/claude_export.json
    python migrate.py --demo           # run with sample data
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Console helpers
# ---------------------------------------------------------------------------

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    class _FakeConsole:
        """Minimal console fallback when Rich is not installed."""
        def print(self, *a, **kw):
            """Print arguments as strings."""
            print(*[str(x) for x in a])
        def rule(self, *a, **kw):
            """Print a horizontal rule."""
            print("=" * 60)
    console = _FakeConsole()


def _heading(title: str) -> None:
    """Print a section heading to the console."""
    if HAS_RICH:
        console.rule(f"[bold cyan]{title}[/bold cyan]")
    else:
        print(f"\n{'=' * 60}\n  {title}\n{'=' * 60}")

def _info(msg: str) -> None:
    """Print an informational message."""
    console.print(f"  ... {msg}")

def _ok(msg: str) -> None:
    """Print a success message."""
    if HAS_RICH:
        console.print(f"  [bold green]OK[/bold green] {msg}")
    else:
        print(f"  OK  {msg}")


# ---------------------------------------------------------------------------
# Mapper logic (embedded from mappers.py for standalone use)
# ---------------------------------------------------------------------------

def _now_utc():
    """Return the current UTC datetime."""
    return datetime.now(timezone.utc)

def _safe_dt(value):
    """Best-effort parse of a value into a UTC datetime."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OSError, ValueError):
            return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None

def _pick_first_dt(obj, keys):
    """Return the first successfully parsed datetime from *obj* for the given keys."""
    for k in keys:
        v = obj.get(k)
        if v is not None:
            dt = _safe_dt(v)
            if dt:
                return dt
    return None

def _title_from(content):
    """Derive a short title from the first line of content, truncated to 80 chars."""
    first_line = content.split("\n", 1)[0].strip()
    if len(first_line) <= 80:
        return first_line
    return first_line[:77] + "..."

def _format_supporting_data(pairs):
    """Render key-value pairs into a markdown supporting-data block."""
    lines = []
    for k, v in pairs:
        if v is not None and v != "" and v != "None":
            lines.append(f"**{k}:** {v}")
    return "\n".join(lines)

def _attach_footer(content, footer):
    """Append a migration-metadata footer to the content string."""
    if footer:
        return f"{content}\n\n---\n*Migration metadata:*\n{footer}"
    return content


def _walk_chatgpt_mapping(mapping, current_id, max_depth=10000):
    """Walk ChatGPT's tree-structured mapping dict backwards to collect messages."""
    messages = []
    visited = set()
    node_id = current_id
    for _ in range(max_depth):
        if not node_id or node_id in visited:
            break
        visited.add(node_id)
        node = mapping.get(node_id)
        if not node:
            break
        msg = node.get("message")
        if msg:
            author = msg.get("author") or {}
            role = author.get("role") or ""
            content_obj = msg.get("content") or {}
            parts = content_obj.get("parts") or []
            text = " ".join(p for p in parts if isinstance(p, str) and p.strip()).strip()
            if text and role in ("user", "human"):
                messages.append({"text": text, "role": "user", "create_time": msg.get("create_time")})
            elif text and role == "assistant":
                messages.append({"text": text, "role": "assistant", "create_time": msg.get("create_time")})
            elif text and role == "system":
                messages.append({"text": text, "role": "system", "create_time": msg.get("create_time")})
        node_id = node.get("parent")
    messages.reverse()
    return messages


def map_chatgpt(export):
    """Map a ChatGPT data export to Memanto memory payloads."""
    rows = []
    migrated_at = _now_utc()
    conversations = export.get("conversations") or export.get("memories") or []
    if isinstance(conversations, dict):
        conversations = conversations.get("conversations", [])

    for convo in conversations:
        title = (convo.get("title") or "").strip()
        mapping = convo.get("mapping") or {}
        current_node = convo.get("current_node")

        if not mapping or not current_node:
            messages = []
            for msg in convo.get("messages") or convo.get("chat_messages") or []:
                role = ((msg.get("author") or {}).get("role") or msg.get("role") or "").strip()
                content_obj = msg.get("content")
                if isinstance(content_obj, dict):
                    parts = content_obj.get("parts") or []
                    text = " ".join(p for p in parts if isinstance(p, str)).strip()
                elif isinstance(content_obj, str):
                    text = content_obj.strip()
                else:
                    text = (msg.get("text") or "").strip()
                if text and role in ("user", "human"):
                    messages.append({"text": text, "role": "user", "create_time": msg.get("create_time")})
                elif text and role == "assistant":
                    messages.append({"text": text, "role": "assistant", "create_time": msg.get("create_time")})
                elif text and role == "system":
                    messages.append({"text": text, "role": "system", "create_time": msg.get("create_time")})
        else:
            messages = _walk_chatgpt_mapping(mapping, current_node)

        if not messages:
            continue

        content_parts = []
        for i, msg in enumerate(messages, 1):
            role_label = msg['role'].capitalize()
            content_parts.append(f"[{role_label} message {i}]: {msg['text']}")
        content = "\n\n".join(content_parts)
        if not content.strip():
            continue

        created_at = _pick_first_dt(convo, ("create_time", "created_at", "update_time"))
        convo_title = title or _title_from(content)
        footer = _format_supporting_data([
            ("Source", "chatgpt:conversation"),
            ("ChatGPT title", title),
            ("Message count", len(messages)),
            ("Source created_at", created_at.isoformat() if created_at else None),
        ])

        rows.append({
            "title": convo_title,
            "content": _attach_footer(content, footer),
            "type": None,
            "tags": ["chatgpt", "ai-conversation"],
            "confidence": 0.8,
            "source": "chatgpt",
            "source_ref": convo.get("conversation_id") or convo.get("id"),
            "provenance": "imported",
            "created_at": created_at,
            "updated_at": migrated_at,
        })
    return rows


def map_claude(export):
    """Map a Claude data export to Memanto memory payloads."""
    rows = []
    migrated_at = _now_utc()
    conversations = export.get("conversations") or export.get("memories") or []
    if isinstance(conversations, dict):
        conversations = conversations.get("conversations", [])

    for convo in conversations:
        title = (convo.get("name") or convo.get("title") or "").strip()
        chat_messages = convo.get("chat_messages") or convo.get("messages") or []

        human_messages = []
        for msg in chat_messages:
            sender = (msg.get("sender") or msg.get("role") or "").strip()
            text = (msg.get("text") or msg.get("content") or "").strip()
            if text and sender in ("human", "user"):
                human_messages.append({
                    "text": text,
                    "role": "user",
                    "created_at": msg.get("created_at"),
                })
            elif text and sender == "assistant":
                human_messages.append({
                    "text": text,
                    "role": "assistant",
                    "created_at": msg.get("created_at"),
                })

        if not human_messages:
            continue

        content_parts = []
        for i, msg in enumerate(human_messages, 1):
            role_label = msg['role'].capitalize()
            content_parts.append(f"[{role_label} message {i}]: {msg['text']}")
        content = "\n\n".join(content_parts)
        if not content.strip():
            continue

        created_at = _pick_first_dt(convo, ("created_at", "create_time", "updated_at"))
        convo_title = title or _title_from(content)
        footer = _format_supporting_data([
            ("Source", "claude:conversation"),
            ("Claude title", title),
            ("Claude UUID", convo.get("uuid")),
            ("Message count", len(human_messages)),
            ("Source created_at", created_at.isoformat() if created_at else None),
        ])

        rows.append({
            "title": convo_title,
            "content": _attach_footer(content, footer),
            "type": None,
            "tags": ["claude", "ai-conversation"],
            "confidence": 0.8,
            "source": "claude",
            "source_ref": convo.get("uuid") or convo.get("id"),
            "provenance": "imported",
            "created_at": created_at,
            "updated_at": migrated_at,
        })
    return rows


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def load_export(path):
    """Load a JSON export file and normalize it to a memories/conversations dict."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        data = {"memories": data, "conversations": data}
    return data


def map_memories(source, export_data):
    """Dispatch to the appropriate mapper based on source platform."""
    if source == "chatgpt":
        return map_chatgpt(export_data)
    elif source == "claude":
        return map_claude(export_data)
    raise ValueError(f"Unknown source: {source}")


def preview_memories(memories):
    """Display a preview table of mapped memories in the console."""
    if HAS_RICH:
        table = Table(title="Mapped Memories Preview", show_lines=True)
        table.add_column("#", style="dim", width=3)
        table.add_column("Title", max_width=35)
        table.add_column("Type", width=10)
        table.add_column("Source", width=10)
        table.add_column("Confidence", width=10)
        table.add_column("Content (truncated)", max_width=45)

        for i, mem in enumerate(memories[:15], 1):
            content_preview = (mem.get("content") or "")[:120].replace("\n", " ")
            table.add_row(
                str(i),
                mem.get("title", "")[:35],
                mem.get("type") or "(auto)",
                mem.get("source", ""),
                f"{mem.get('confidence', 0):.2f}",
                content_preview + ("..." if len(mem.get("content", "")) > 120 else ""),
            )
        if len(memories) > 15:
            table.add_row("...", f"{len(memories) - 15} more", "", "", "", "")
        console.print(table)
    else:
        for i, mem in enumerate(memories, 1):
            print(f"  {i}. [{mem.get('source')}] {mem.get('title', '')[:50]}")
            print(f"     {mem.get('content', '')[:80]}...")


def export_okf_bundle(memories, output_dir):
    """Export mapped memories as an OKF bundle with manifest and markdown files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "okf_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "memanto-migration",
        "memory_count": len(memories),
        "memories": [],
    }
    memories_dir = output_dir / "memories"
    memories_dir.mkdir(exist_ok=True)

    for i, mem in enumerate(memories):
        mem_id = f"mem_{i:04d}"
        raw_slug = (mem.get("title") or f"memory_{i}")[:50]
        slug = re.sub(r"[^\w\s-]", "", raw_slug).strip().replace(" ", "_")
        slug = slug.lstrip(".")
        if not slug:
            slug = f"memory_{i}"
        md_content = f"""# {mem.get('title', f'Memory {i}')}

**Type:** {mem.get('type') or 'auto-classified'}
**Source:** {mem.get('source', 'unknown')}
**Confidence:** {mem.get('confidence', 0)}
**Tags:** {', '.join(mem.get('tags', []))}
**Created:** {mem.get('created_at', 'unknown')}

---

{mem.get('content', '')}
"""
        md_path = memories_dir / f"{mem_id}_{slug}.md"
        md_path.write_text(md_content, encoding="utf-8")
        manifest["memories"].append({
            "id": mem_id,
            "title": mem.get("title"),
            "type": mem.get("type") or "auto-classified",
            "source": mem.get("source"),
            "file": f"memories/{md_path.name}",
        })

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    return output_dir


def run_recall_test(memories, export_data):
    """Run a basic recall-parity test checking that key facts are preserved."""
    expected_facts = []
    conversations = export_data.get("conversations") or export_data.get("memories") or []
    if isinstance(conversations, dict):
        conversations = conversations.get("conversations", [])

    for convo in conversations:
        if not isinstance(convo, dict):
            continue
        title = convo.get("title") or convo.get("name") or ""
        if title:
            expected_facts.append(title)

        if "mapping" in convo:
            mapping = convo.get("mapping", {})
            current = convo.get("current_node")
            visited = set()
            while current and current not in visited:
                visited.add(current)
                node = mapping.get(current)
                if node:
                    msg = node.get("message")
                    if msg and msg.get("author", {}).get("role") in ("user", "human"):
                        parts = msg.get("content", {}).get("parts", [])
                        text = " ".join(p for p in parts if isinstance(p, str)).strip()
                        if text:
                            expected_facts.append(text[:100])
                    current = node.get("parent")
        else:
            for msg in convo.get("chat_messages") or convo.get("messages") or []:
                if not isinstance(msg, dict):
                    continue
                sender = msg.get("sender") or msg.get("role") or ""
                content_obj = msg.get("content") or {}
                if isinstance(content_obj, str):
                    text = content_obj[:100]
                elif isinstance(content_obj, dict):
                    parts = content_obj.get("parts") or []
                    text = " ".join(p for p in parts if isinstance(p, str)).strip()[:100]
                else:
                    text = (msg.get("text") or "")[:100]
                if text and sender in ("human", "user"):
                    expected_facts.append(text)

    all_content = " ".join(
        (mem.get("content", "") + " " + mem.get("title", "")).lower()
        for mem in memories
    )

    results = {"total": len(expected_facts), "found": 0, "missing": []}
    for fact in expected_facts:
        words = [w.lower() for w in fact.split() if len(w) > 3][:8]
        found = any(word in all_content for word in words)
        if found:
            results["found"] += 1
        else:
            results["missing"].append(fact[:60])

    results["recall_rate"] = results["found"] / max(results["total"], 1)
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    """CLI entry point for the AI conversation migration demo."""
    parser = argparse.ArgumentParser(
        description="AI Conversation Migration Demo: ChatGPT/Claude -> Memanto -> OKF",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              python migrate.py --demo
              python migrate.py --source chatgpt --export ./sample_data/chatgpt_export.json
              python migrate.py --source claude  --export ./sample_data/claude_export.json
        """),
    )
    parser.add_argument("--source", "-s", choices=["chatgpt", "claude"], help="Source platform")
    parser.add_argument("--export", "-e", type=Path, help="Path to export JSON file")
    parser.add_argument("--output", "-o", type=Path, default=Path("./okf_bundle"), help="OKF bundle output dir")
    parser.add_argument("--demo", action="store_true", help="Run with sample data")

    args = parser.parse_args()

    if args.demo:
        sample_dir = Path(__file__).parent / "sample_data"
        if (sample_dir / "chatgpt_export.json").exists():
            args.source = "chatgpt"
            args.export = sample_dir / "chatgpt_export.json"
        else:
            args.source = "claude"
            args.export = sample_dir / "claude_export.json"

    if not args.source or not args.export:
        parser.error("Provide --source and --export, or use --demo")
    if not args.export.exists():
        parser.error(f"Export file not found: {args.export}")

    # Step 1
    _heading("Step 1: Load Export")
    export_data = load_export(args.export)
    convo_count = len(export_data.get("conversations") or export_data.get("memories") or [])
    _ok(f"Loaded {convo_count} conversations from {args.export.name}")

    # Step 2
    _heading("Step 2: Map to Memanto Schema")
    memories = map_memories(args.source, export_data)
    _ok(f"Mapped {len(memories)} memories")
    preview_memories(memories)

    # Step 3
    _heading("Step 3: Import into Memanto")
    _info("Skipped (standalone demo — no Memanto server required)")

    # Step 4
    _heading("Step 4: Export OKF Bundle")
    bundle_dir = export_okf_bundle(memories, args.output)
    _ok(f"OKF bundle exported to {bundle_dir}")

    # Step 5
    _heading("Step 5: Recall-Parity Validation")
    results = run_recall_test(memories, export_data)
    rate = results["recall_rate"]
    status = "PASS" if rate >= 0.8 else "WARN"
    _ok(f"Recall rate: {rate:.1%} ({results['found']}/{results['total']} facts found)")
    if results["missing"]:
        _info(f"Missing: {results['missing'][:3]}...")

    # Done
    _heading("Migration Complete")
    summary_msg = f"{status} - {len(memories)} memories migrated, OKF bundle at {bundle_dir}, recall {rate:.0%}"
    if HAS_RICH:
        console.print(Panel.fit(
            f"[bold green]{status}[/bold green] - {len(memories)} memories migrated, "
            f"OKF bundle at [cyan]{bundle_dir}[/cyan], recall {rate:.0%}",
            border_style="green" if rate >= 0.8 else "yellow",
        ))
    else:
        print(summary_msg)


if __name__ == "__main__":
    main()
