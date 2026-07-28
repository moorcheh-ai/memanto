#!/usr/bin/env python3
"""
Zep/Graphiti memory export → OKF bundle converter for Memanto.

Converts a Zep memory export (JSON) into an OKF markdown bundle that can be
imported losslessly via `memanto migrate okf ./okf_bundle`.

Zep stores agent memory as:
  - facts: extracted subject-predicate-object statements
  - entities: nodes in a temporal knowledge graph
  - relations: typed edges between entities with validity windows
  - messages: raw conversation turns (optional, high-volume)

This adapter preserves all structured metadata (timestamps, scores, entity
types, relation episodes) in OKF frontmatter + supporting-data footers so
nothing is lost in the migration.

Usage:
    python convert.py [--input zep_export.json] [--output ./okf_bundle]
    python convert.py --from-api --zep-url http://localhost:8000 --user-id <id>

The --from-api mode fetches live memory from a running Zep instance via its
REST API (no SDK dependency required).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_zep_export(path: str | Path) -> dict[str, Any]:
    """Load a Zep export JSON file."""
    p = Path(path)
    if not p.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def fetch_from_api(zep_url: str, user_id: str) -> dict[str, Any]:
    """Fetch memory from a live Zep instance via REST API."""
    import urllib.request

    base = zep_url.rstrip("/")
    result: dict[str, Any] = {"facts": [], "entities": [], "relations": []}

    endpoints = {
        "facts": f"{base}/api/v2/users/{user_id}/memory",
        "graph": f"{base}/api/v2/users/{user_id}/graph",
    }

    for key, url in endpoints.items():
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                if key == "facts":
                    result["facts"] = data.get("facts", [])
                    result["messages"] = data.get("messages", [])
                elif key == "graph":
                    result["entities"] = data.get("nodes", data.get("entities", []))
                    result["relations"] = data.get("edges", data.get("relations", []))
        except Exception as e:
            print(f"Warning: could not fetch {key} from {url}: {e}", file=sys.stderr)

    return result


def _sanitize_filename(text: str, max_len: int = 60) -> str:
    """Create a filesystem-safe filename from text."""
    safe = "".join(c if c.isalnum() or c in "-_ " else "" for c in text.lower())
    safe = safe.strip().replace(" ", "_")
    return safe[:max_len] or "memory"


def _format_timestamp(ts: Any) -> str:
    """Normalize a timestamp to ISO 8601 UTC."""
    if not ts:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    s = str(ts).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return str(ts)


def _confidence_from_score(score: Any) -> float:
    """Map a Zep relevance score to a 0-1 confidence value."""
    if score is None:
        return 0.8
    try:
        s = float(score)
        return max(0.1, min(1.0, s))
    except (TypeError, ValueError):
        return 0.8


def convert_facts(facts: list[dict[str, Any]]) -> list[str]:
    """Convert Zep facts to OKF markdown entries."""
    entries = []
    for i, fact in enumerate(facts):
        text = fact.get("fact", fact.get("text", fact.get("content", "")))
        if not text:
            continue

        created = _format_timestamp(fact.get("created_at", fact.get("valid_at")))
        confidence = _confidence_from_score(fact.get("score", fact.get("confidence")))
        fact_type = fact.get("type", "fact")

        tags = ["zep-import", "fact"]
        if fact.get("category"):
            tags.append(fact["category"])
        if fact.get("group"):
            tags.append(f"group={fact['group']}")

        # Build supporting data footer
        footer_parts = []
        if fact.get("uuid"):
            footer_parts.append(f"- Zep UUID: {fact['uuid']}")
        if fact.get("valid_at"):
            footer_parts.append(f"- Valid from: {fact['valid_at']}")
        if fact.get("invalid_at"):
            footer_parts.append(f"- Invalidated: {fact['invalid_at']}")
        if fact.get("episode_refs"):
            footer_parts.append(f"- Episodes: {len(fact['episode_refs'])} references")

        footer = ""
        if footer_parts:
            footer = "\n\n## Supporting data\n\n" + "\n".join(footer_parts)

        entry = f"""---
type: {fact_type}
title: "{text[:80].replace(chr(34), chr(39))}"
description: "Migrated from Zep memory"
tags: [{', '.join(tags)}]
timestamp: "{created}"
x_memanto:
  confidence: {confidence}
  source: zep
  source_ref: "{fact.get('uuid', f'fact-{i}')}"
  provenance: imported
---

{text}{footer}
"""
        entries.append(entry)
    return entries


def convert_entities(entities: list[dict[str, Any]]) -> list[str]:
    """Convert Zep graph entities to OKF markdown entries."""
    entries = []
    for i, entity in enumerate(entities):
        name = entity.get("name", entity.get("summary", f"entity-{i}"))
        summary = entity.get("summary", entity.get("description", ""))
        entity_type = entity.get("type", entity.get("label", "entity"))

        if not name or name.startswith("entity-"):
            continue

        created = _format_timestamp(entity.get("created_at"))
        tags = ["zep-import", "entity", f"type={entity_type}"]

        footer_parts = []
        if entity.get("uuid"):
            footer_parts.append(f"- Zep UUID: {entity['uuid']}")
        if entity.get("group"):
            footer_parts.append(f"- Group: {entity['group']}")
        if entity.get("attributes"):
            attrs = entity["attributes"]
            if isinstance(attrs, dict):
                for k, v in list(attrs.items())[:10]:
                    footer_parts.append(f"- {k}: {v}")

        footer = ""
        if footer_parts:
            footer = "\n\n## Supporting data\n\n" + "\n".join(footer_parts)

        content = summary if summary else f"Entity: {name} (type: {entity_type})"

        entry = f"""---
type: fact
title: "Entity: {name[:70].replace(chr(34), chr(39))}"
description: "Knowledge graph entity from Zep"
tags: [{', '.join(tags)}]
timestamp: "{created}"
x_memanto:
  confidence: 0.9
  source: zep
  source_ref: "{entity.get('uuid', f'entity-{i}')}"
  provenance: imported
---

{content}{footer}
"""
        entries.append(entry)
    return entries


def convert_relations(relations: list[dict[str, Any]]) -> list[str]:
    """Convert Zep graph relations to OKF markdown entries."""
    entries = []
    for i, rel in enumerate(relations):
        source = rel.get("source", rel.get("source_node", ""))
        target = rel.get("target", rel.get("target_node", ""))
        rel_type = rel.get("type", rel.get("relation_type", rel.get("fact", "related_to")))

        if isinstance(source, dict):
            source = source.get("name", str(source))
        if isinstance(target, dict):
            target = target.get("name", str(target))

        if not source and not target:
            continue

        text = f"{source} → {rel_type} → {target}"
        created = _format_timestamp(rel.get("created_at", rel.get("valid_at")))

        tags = ["zep-import", "relation"]
        if rel.get("group"):
            tags.append(f"group={rel['group']}")

        footer_parts = []
        if rel.get("uuid"):
            footer_parts.append(f"- Zep UUID: {rel['uuid']}")
        if rel.get("valid_at"):
            footer_parts.append(f"- Valid from: {rel['valid_at']}")
        if rel.get("invalid_at"):
            footer_parts.append(f"- Invalidated: {rel['invalid_at']}")
        if rel.get("episodes"):
            footer_parts.append(f"- Derived from {len(rel['episodes'])} episodes")

        footer = ""
        if footer_parts:
            footer = "\n\n## Supporting data\n\n" + "\n".join(footer_parts)

        entry = f"""---
type: relationship
title: "{text[:80].replace(chr(34), chr(39))}"
description: "Knowledge graph relation from Zep"
tags: [{', '.join(tags)}]
timestamp: "{created}"
x_memanto:
  confidence: 0.85
  source: zep
  source_ref: "{rel.get('uuid', f'relation-{i}')}"
  provenance: imported
---

{text}{footer}
"""
        entries.append(entry)
    return entries


def build_okf_bundle(
    data: dict[str, Any], output_dir: str | Path, include_messages: bool = False
) -> Path:
    """Convert a full Zep export into an OKF bundle directory."""
    out = Path(output_dir)
    memories_dir = out / "memories"
    memories_dir.mkdir(parents=True, exist_ok=True)

    all_entries: list[str] = []

    facts = data.get("facts", [])
    entities = data.get("entities", data.get("nodes", []))
    relations = data.get("relations", data.get("edges", []))

    all_entries.extend(convert_facts(facts))
    all_entries.extend(convert_entities(entities))
    all_entries.extend(convert_relations(relations))

    if include_messages:
        messages = data.get("messages", [])
        msg_entries = convert_messages(messages)
        all_entries.extend(msg_entries)

    if not all_entries:
        print("Warning: no memories found in export", file=sys.stderr)

    # Write entries grouped by type for browsability
    fact_entries = [e for e in all_entries if "type: fact" in e.split("---")[1]]
    rel_entries = [e for e in all_entries if "type: relationship" in e.split("---")[1]]
    other_entries = [
        e
        for e in all_entries
        if "type: fact" not in e.split("---")[1]
        and "type: relationship" not in e.split("---")[1]
    ]

    file_count = 0
    for entries, prefix in [
        (fact_entries, "facts"),
        (rel_entries, "relations"),
        (other_entries, "memories"),
    ]:
        if not entries:
            continue
        # Group into files of ~20 entries each for manageable file sizes
        chunk_size = 20
        for chunk_idx in range(0, len(entries), chunk_size):
            chunk = entries[chunk_idx : chunk_idx + chunk_size]
            filename = f"{prefix}_{chunk_idx // chunk_size + 1:03d}.md"
            filepath = memories_dir / filename
            # Use OKF entry delimiter between entries in the same file
            content = "\n<!-- okf-entry -->\n".join(chunk)
            filepath.write_text(content, encoding="utf-8")
            file_count += 1

    # Write index
    index_content = f"""---
type: index
title: "Zep → Memanto Migration"
description: "Migrated {len(all_entries)} memories from Zep"
timestamp: "{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}"
---

# Zep Memory Migration

- **Facts:** {len(fact_entries)}
- **Relations:** {len(rel_entries)}
- **Other:** {len(other_entries)}
- **Total:** {len(all_entries)}
- **Files:** {file_count}

Import with: `memanto migrate okf {out}`
"""
    (out / "index.md").write_text(index_content, encoding="utf-8")

    return out


def convert_messages(messages: list[dict[str, Any]]) -> list[str]:
    """Convert Zep conversation messages to OKF entries (optional, high-volume)."""
    entries = []
    for i, msg in enumerate(messages):
        content = msg.get("content", msg.get("text", ""))
        if not content or len(content) < 10:
            continue

        role = msg.get("role", "unknown")
        created = _format_timestamp(msg.get("created_at", msg.get("timestamp")))

        entry = f"""---
type: event
title: "Conversation turn ({role})"
description: "Migrated conversation message from Zep"
tags: [zep-import, conversation, role={role}]
timestamp: "{created}"
x_memanto:
  confidence: 0.7
  source: zep
  source_ref: "{msg.get('uuid', f'msg-{i}')}"
  provenance: imported
---

{content[:2000]}
"""
        entries.append(entry)
    return entries


def main():
    parser = argparse.ArgumentParser(
        description="Convert Zep memory export to OKF bundle for Memanto"
    )
    parser.add_argument(
        "--input", "-i", default="zep_export.json", help="Path to Zep export JSON"
    )
    parser.add_argument(
        "--output", "-o", default="./okf_bundle", help="Output OKF bundle directory"
    )
    parser.add_argument(
        "--include-messages",
        action="store_true",
        help="Include raw conversation messages (high volume)",
    )
    parser.add_argument(
        "--from-api",
        action="store_true",
        help="Fetch from live Zep instance instead of file",
    )
    parser.add_argument("--zep-url", default="http://localhost:8000", help="Zep server URL")
    parser.add_argument("--user-id", help="Zep user ID (required with --from-api)")

    args = parser.parse_args()

    if args.from_api:
        if not args.user_id:
            print("Error: --user-id required with --from-api", file=sys.stderr)
            sys.exit(1)
        print(f"Fetching memory from Zep at {args.zep_url} for user {args.user_id}...")
        data = fetch_from_api(args.zep_url, args.user_id)
    else:
        print(f"Loading Zep export from {args.input}...")
        data = load_zep_export(args.input)

    facts = len(data.get("facts", []))
    entities = len(data.get("entities", data.get("nodes", [])))
    relations = len(data.get("relations", data.get("edges", [])))
    messages = len(data.get("messages", []))
    print(f"Found: {facts} facts, {entities} entities, {relations} relations, {messages} messages")

    out = build_okf_bundle(data, args.output, include_messages=args.include_messages)
    print(f"\nOKF bundle written to: {out}/")
    print(f"\nImport into Memanto with:")
    print(f"  memanto migrate okf {out}")


if __name__ == "__main__":
    main()
