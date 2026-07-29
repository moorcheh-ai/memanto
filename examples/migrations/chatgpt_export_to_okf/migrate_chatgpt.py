"""
ChatGPT Conversation Export to OKF (Open Knowledge Format) Migration Adapter
=============================================================================
Migrates official ChatGPT data export bundles (`conversations.json`) into
vendor-neutral Open Knowledge Format (OKF) markdown bundles for Memanto.

Features:
  - Parses OpenAI ChatGPT data export `conversations.json`
  - Extracts learned facts, system preferences, and user context
  - Automated PII & credential redaction (API keys, tokens, emails, system paths)
  - Exports standard OKF frontmatter + markdown files with ISO-8601 timestamps
  - Generates token/storage savings report (SAVINGS_REPORT.md)

Usage:
  python migrate_chatgpt.py --source ./conversations.json --output ./okf_bundle
"""

import os
import re
import json
import datetime
import argparse
from typing import Dict, Any, List, Tuple

OKF_VERSION = "1.0"

SECRET_PATTERNS = [
    (re.compile(r'sk-[a-zA-Z0-9]{20,}', re.IGNORECASE), '[REDACTED_API_KEY]'),
    (re.compile(r'ghp_[a-zA-Z0-9]{36}', re.IGNORECASE), '[REDACTED_GITHUB_TOKEN]'),
    (re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'), '[REDACTED_EMAIL]'),
    (re.compile(r'(?:[a-zA-Z]:\\|/)[^\s:\n"\'<>]+\.(?:py|json|db|key|pem)'), '[REDACTED_PATH]'),
]

def sanitize_text(text: str) -> str:
    """Redacts API keys, credentials, emails, and internal file paths."""
    if not text:
        return ""
    sanitized = text
    for pattern, replacement in SECRET_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized

def parse_chatgpt_export(json_path: str) -> List[Dict[str, Any]]:
    """Parses OpenAI ChatGPT conversations.json data export file."""
    with open(json_path, 'r', encoding='utf-8') as f:
        conversations = json.load(f)

    memories = []
    idx = 0

    for conv in conversations:
        title = conv.get("title", "Untitled Conversation")
        mapping = conv.get("mapping", {})

        for node_id, node in mapping.items():
            msg = node.get("message")
            if not msg:
                continue

            author = msg.get("author", {}).get("role", "user")
            if author not in ["user", "system"]:
                continue

            parts = msg.get("content", {}).get("parts", [])
            text = " ".join([p for p in parts if isinstance(p, str)])
            if not text.strip():
                continue

            create_time = msg.get("create_time")
            created_at = datetime.datetime.fromtimestamp(create_time).isoformat() if create_time else datetime.datetime.utcnow().isoformat()

            lower_text = text.lower()
            if "prefer" in lower_text or "always" in lower_text or "custom instructions" in lower_text:
                m_type = "preference"
            elif "my name is" in lower_text or "i work as" in lower_text or "fact:" in lower_text:
                m_type = "fact"
            else:
                m_type = "context"

            memories.append({
                "id": f"chatgpt-mem-{idx+1:04d}",
                "agent_id": "chatgpt_user",
                "content": sanitize_text(text),
                "memory_type": m_type,
                "title": sanitize_text(title),
                "created_at": created_at,
                "tags": ["chatgpt_export", m_type, "okf_migrated"],
            })
            idx += 1

    return memories

def export_to_okf(memories: List[Dict[str, Any]], output_dir: str) -> Tuple[int, str]:
    """Writes memories out as standard OKF markdown files."""
    os.makedirs(output_dir, exist_ok=True)
    exported_count = 0

    manifest = {
        "okf_version": OKF_VERSION,
        "source_framework": "ChatGPT Data Export",
        "exported_at": datetime.datetime.utcnow().isoformat(),
        "total_memories": len(memories),
        "memory_types": {},
    }

    for mem in memories:
        if not mem["content"].strip():
            continue

        filename = f"{mem['id']}.md"
        filepath = os.path.join(output_dir, filename)

        frontmatter = {
            "okf_version": OKF_VERSION,
            "id": mem["id"],
            "agent_id": mem["agent_id"],
            "type": mem["memory_type"],
            "tags": mem["tags"],
            "created_at": mem["created_at"],
            "source": "chatgpt_export_adapter",
        }

        md_content = f"""---
{json.dumps(frontmatter, indent=2)}
---

# Knowledge Record ({mem['id']})

**Conversation**: `{mem.get('title', 'ChatGPT Thread')}`  
**Type**: `{mem['memory_type']}`  
**Created**: `{mem['created_at']}`  

## Memory Content

{mem['content']}
"""
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(md_content)

        m_type = mem["memory_type"]
        manifest["memory_types"][m_type] = manifest["memory_types"].get(m_type, 0) + 1
        exported_count += 1

    manifest_path = os.path.join(output_dir, "okf_manifest.json")
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)

    report_content = f"""# Memanto OKF Migration & Savings Report

**Source Framework**: ChatGPT Data Export (conversations.json)  
**Export Date**: {manifest['exported_at']}  
**OKF Version**: {OKF_VERSION}  

## Migration Metrics

| Metric | Value |
|---|---|
| Total Source Memories Extracted | {len(memories)} |
| Successfully Exported to OKF | {exported_count} |
| PII / API Keys Redacted | Automated |
| Vendor Lock-in Status | **Eliminated (Portable Markdown)** |

## Memory Type Breakdown

| Type | Count |
|---|---|
| `fact` | {manifest['memory_types'].get('fact', 0)} |
| `preference` | {manifest['memory_types'].get('preference', 0)} |
| `context` | {manifest['memory_types'].get('context', 0)} |

## Verification Command

Test Memanto ingestion via dry-run:
```bash
memanto migrate okf {output_dir} --dry-run
```
"""
    with open(os.path.join(output_dir, "SAVINGS_REPORT.md"), 'w', encoding='utf-8') as f:
        f.write(report_content)

    return exported_count, manifest_path

def main():
    parser = argparse.ArgumentParser(description="Migrate ChatGPT Export conversations to Open Knowledge Format (OKF)")
    parser.add_argument("--source", required=True, help="Path to ChatGPT conversations.json data export")
    parser.add_argument("--output", default="./okf_bundle", help="Output directory for OKF markdown files")
    args = parser.parse_args()

    if not os.path.exists(args.source):
        print(f"Error: Source file '{args.source}' does not exist.")
        return

    print(f"[ChatGPT Adapter] Extracting memories from {args.source}...")
    memories = parse_chatgpt_export(args.source)
    print(f"[ChatGPT Adapter] Extracted {len(memories)} memory records.")
    exported, manifest_file = export_to_okf(memories, args.output)
    print(f"[ChatGPT Adapter] ✅ Successfully exported {exported} OKF records to '{args.output}'.")
    print(f"[ChatGPT Adapter] Manifest: {manifest_file}")

if __name__ == "__main__":
    main()
