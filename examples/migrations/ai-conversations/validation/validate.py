#!/usr/bin/env python3
"""Validation: golden Q&A pairs + recall parity for migrated conversations.

Usage:
    python validation/validate.py --source chatgpt --export ../sample_data/chatgpt_export.json
    python validation/validate.py --source claude  --export ../sample_data/claude_export.json
    python validation/validate.py --validate-okf  --okf-dir ../okf_bundle
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Embedded mapper (same as migrate.py — standalone, no memanto package needed)
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
    return first_line[:77] + "..." if len(first_line) > 80 else first_line

def _format_supporting_data(pairs):
    """Render key-value pairs into a markdown supporting-data block."""
    lines = []
    for k, v in pairs:
        if v is not None and v != "":
            lines.append(f"**{k}:** {v}")
    return "\n".join(lines)

def _attach_footer(content, footer):
    """Append a migration-metadata footer to the content string."""
    return f"{content}\n\n---\n*Migration metadata:*\n{footer}" if footer else content

def _walk_chatgpt_mapping(mapping, current_id, max_depth=200):
    """Walk ChatGPT's tree-structured mapping dict backwards to collect messages."""
    messages, visited, node_id = [], set(), current_id
    for _ in range(max_depth):
        if not node_id or node_id in visited:
            break
        visited.add(node_id)
        node = mapping.get(node_id)
        if not node:
            break
        msg = node.get("message")
        if msg:
            role = (msg.get("author") or {}).get("role", "")
            parts = (msg.get("content") or {}).get("parts", [])
            text = " ".join(p for p in parts if isinstance(p, str) and p.strip()).strip()
            if text and role in ("user", "human"):
                messages.append({"text": text, "role": "user", "create_time": msg.get("create_time")})
        node_id = node.get("parent")
    messages.reverse()
    return messages

def map_chatgpt(export):
    """Map a ChatGPT data export to memory payloads for validation."""
    rows, migrated_at = [], _now_utc()
    conversations = export.get("conversations") or export.get("memories") or []
    if isinstance(conversations, dict):
        conversations = conversations.get("conversations", [])
    for convo in conversations:
        title = (convo.get("title") or "").strip()
        mapping, current_node = convo.get("mapping") or {}, convo.get("current_node")
        if not mapping or not current_node:
            messages = []
            for msg in convo.get("messages") or convo.get("chat_messages") or []:
                role = ((msg.get("author") or {}).get("role") or msg.get("role") or "").strip()
                content_obj = msg.get("content") or {}
                if isinstance(content_obj, str):
                    text = content_obj.strip()
                elif isinstance(content_obj, dict):
                    parts = content_obj.get("parts") or []
                    text = " ".join(p for p in parts if isinstance(p, str)).strip()
                else:
                    text = str(content_obj).strip() if content_obj else ""
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
        footer = _format_supporting_data([
            ("Source", "chatgpt:conversation"),
            ("ChatGPT title", title),
            ("Message count", len(messages)),
            ("Source created_at", created_at.isoformat() if created_at else None),
        ])
        rows.append({
            "title": title or _title_from(content),
            "content": _attach_footer(content, footer),
            "type": None, "tags": ["chatgpt", "ai-conversation"],
            "confidence": 0.8, "source": "chatgpt",
            "source_ref": convo.get("conversation_id") or convo.get("id"),
            "provenance": "imported",
            "created_at": created_at, "updated_at": migrated_at,
        })
    return rows

def map_claude(export):
    """Map a Claude data export to memory payloads for validation."""
    rows, migrated_at = [], _now_utc()
    conversations = export.get("conversations") or export.get("memories") or []
    if isinstance(conversations, dict):
        conversations = conversations.get("conversations", [])
    for convo in conversations:
        title = (convo.get("name") or convo.get("title") or "").strip()
        chat_messages = convo.get("chat_messages") or convo.get("messages") or []
        human_messages = []
        for msg in chat_messages:
            sender = (msg.get("sender") or msg.get("role") or "").strip()
            content_obj = msg.get("content") or {}
            if isinstance(content_obj, str):
                text = content_obj.strip()
            elif isinstance(content_obj, dict):
                parts = content_obj.get("parts") or []
                text = " ".join(p for p in parts if isinstance(p, str)).strip()
            else:
                text = (msg.get("text") or "").strip()
            if text and sender in ("human", "user"):
                human_messages.append({"text": text, "role": "user", "created_at": msg.get("created_at")})
            elif text and sender == "assistant":
                human_messages.append({"text": text, "role": "assistant", "created_at": msg.get("created_at")})
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
        footer = _format_supporting_data([
            ("Source", "claude:conversation"),
            ("Claude title", title),
            ("Claude UUID", convo.get("uuid")),
            ("Message count", len(human_messages)),
            ("Source created_at", created_at.isoformat() if created_at else None),
        ])
        rows.append({
            "title": title or _title_from(content),
            "content": _attach_footer(content, footer),
            "type": None, "tags": ["claude", "ai-conversation"],
            "confidence": 0.8, "source": "claude",
            "source_ref": convo.get("uuid") or convo.get("id"),
            "provenance": "imported",
            "created_at": created_at, "updated_at": migrated_at,
        })
    return rows


# ---------------------------------------------------------------------------
# Golden Q&A pairs
# ---------------------------------------------------------------------------

GOLDEN_FACTS = {
    "chatgpt": {
        "FastAPI REST API": ["FastAPI", "todo app", "project structure", "SQLAlchemy", "async", "dependency injection"],
        "React TypeScript": ["Redux Toolkit", "Zustand", "state management", "TypeScript"],
        "Docker Compose": ["React", "FastAPI", "PostgreSQL", "hot-reloading", "uvicorn"],
    },
    "claude": {
        "Python Design Patterns": ["Strategy pattern", "real-world example", "Observer pattern", "backend system"],
        "Database Query Optimization": ["PostgreSQL", "queries", "slow", "EXPLAIN ANALYZE", "Seq Scan"],
        "System Design": ["URL shortener", "bit.ly", "system design interview", "analytics", "click counts"],
    },
}


def check_golden_facts(memories, golden):
    """Check that golden facts from source exports are preserved in memories."""
    all_content = " ".join(
        (mem.get("content", "") + " " + mem.get("title", "")).lower()
        for mem in memories
    )
    results = {}
    for section, keywords in golden.items():
        found = [kw for kw in keywords if kw.lower() in all_content]
        missing = [kw for kw in keywords if kw.lower() not in all_content]
        results[section] = {
            "found": len(found), "missing": len(missing),
            "total": len(keywords), "rate": len(found) / max(len(keywords), 1),
            "missing_keywords": missing,
        }
    return results


def validate_okf_bundle(bundle_dir):
    """Validate an OKF bundle directory for structural correctness."""
    issues = []
    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.exists():
        issues.append("Missing manifest.json")
        return {"valid": False, "issue_count": 1, "issues": issues}

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if "okf_version" not in manifest:
        issues.append("manifest.json missing okf_version")
    if "memory_count" not in manifest:
        issues.append("manifest.json missing memory_count")

    memories = manifest.get("memories", [])
    if manifest.get("memory_count", 0) != len(memories):
        issues.append(f"memory_count mismatch: {manifest.get('memory_count')} vs {len(memories)}")

    for mem in memories:
        mem_rel = mem.get("file", "")
        mem_file = (bundle_dir / mem_rel).resolve()
        if not str(mem_file).startswith(str(bundle_dir.resolve())):
            issues.append(f"Unsafe path in memory file: {mem_rel}")
        elif not mem_file.exists():
            issues.append(f"Missing memory file: {mem_rel}")
        else:
            content = mem_file.read_text(encoding="utf-8")
            if len(content) < 50:
                issues.append(f"Memory {mem.get('id')} too short ({len(content)} chars)")

    return {"valid": len(issues) == 0, "issue_count": len(issues), "issues": issues}


def main():
    """CLI entry point for the migration validation script."""
    parser = argparse.ArgumentParser(description="Validate AI conversation migration")
    parser.add_argument("--source", "-s", choices=["chatgpt", "claude"])
    parser.add_argument("--export", "-e", type=Path)
    parser.add_argument("--validate-okf", action="store_true")
    parser.add_argument("--okf-dir", type=Path, default=Path("./okf_bundle"))
    args = parser.parse_args()

    if args.validate_okf:
        print("\n=== OKF Bundle Validation ===")
        results = validate_okf_bundle(args.okf_dir)
        if results["valid"]:
            print("  PASS - OKF bundle is valid")
        else:
            print(f"  FAIL - {results['issue_count']} issues:")
            for issue in results["issues"]:
                print(f"    - {issue}")
        sys.exit(0 if results["valid"] else 1)

    if not args.source or not args.export:
        parser.error("Provide --source and --export")

    with open(args.export, encoding="utf-8") as f:
        export_data = json.load(f)
    if isinstance(export_data, list):
        export_data = {"memories": export_data, "conversations": export_data}

    memories = map_chatgpt(export_data) if args.source == "chatgpt" else map_claude(export_data)
    golden = GOLDEN_FACTS[args.source]
    golden_results = check_golden_facts(memories, golden)

    print(f"\n=== Golden Fact Recall ({args.source}) ===")
    overall_found, overall_total = 0, 0
    for section, result in golden_results.items():
        status = "PASS" if result["rate"] >= 0.8 else "FAIL"
        print(f"  [{status}] {section}: {result['found']}/{result['total']} keywords found")
        if result["missing_keywords"]:
            print(f"         Missing: {', '.join(result['missing_keywords'])}")
        overall_found += result["found"]
        overall_total += result["total"]

    overall_rate = overall_found / max(overall_total, 1)
    print(f"\n  Overall recall: {overall_rate:.1%} ({overall_found}/{overall_total})")
    print(f"\n  {'PASS' if overall_rate >= 0.8 else 'FAIL'} - Migration {'preserves' if overall_rate >= 0.8 else 'loses'} critical information")
    sys.exit(0 if overall_rate >= 0.8 else 1)


if __name__ == "__main__":
    main()
