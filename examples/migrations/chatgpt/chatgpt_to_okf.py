#!/usr/bin/env python3
import json
import os
import argparse
from datetime import datetime, timezone

def reconstruct_conversation(mapping):
    """Reconstruct a linear conversation from ChatGPT's node mapping."""
    # Find the root node (parent is null)
    root = None
    for node_id, node in mapping.items():
        if not node.get("parent"):
            root = node_id
            break
    
    if not root:
        return []

    # Traverse the primary path (first child)
    messages = []
    current = root
    while current:
        node = mapping[current]
        msg = node.get("message")
        if msg and msg.get("author") and msg.get("content"):
            role = msg["author"].get("role")
            parts = msg["content"].get("parts", [])
            text = "".join([p for p in parts if isinstance(p, str)])
            if role in ("user", "assistant") and text.strip():
                messages.append(f"**{role.capitalize()}**: {text}")
        
        children = node.get("children", [])
        current = children[0] if children else None

    return messages

def export_to_okf(input_path, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"Reading ChatGPT export from {input_path}...")
    with open(input_path, "r", encoding="utf-8") as f:
        conversations = json.load(f)
    
    count = 0
    for i, conv in enumerate(conversations):
        title = conv.get("title") or f"Conversation {i+1}"
        create_time = conv.get("create_time")
        mapping = conv.get("mapping", {})
        
        messages = reconstruct_conversation(mapping)
        if not messages:
            continue
            
        body = "\n\n".join(messages)
        
        dt = datetime.fromtimestamp(create_time, tz=timezone.utc) if create_time else datetime.now(timezone.utc)
        timestamp_str = dt.isoformat()
        
        # Sanitize filename
        safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip()
        if not safe_title:
            safe_title = "conversation"
        filename = f"{safe_title.replace(' ', '_')}_{i}.md"
        filepath = os.path.join(output_dir, filename)
        
        frontmatter = f"""---
title: "{title}"
type: "artifact"
tags:
  - "chatgpt-export"
timestamp: "{timestamp_str}"
x_memanto:
  source: "chatgpt"
---
"""
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(frontmatter + body)
            
        count += 1
        
    print(f"Successfully exported {count} conversations to OKF bundle at '{output_dir}'.")
    print(f"You can now migrate them into Memanto using:")
    print(f"  memanto migrate okf {output_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert ChatGPT conversations.json to a Memanto OKF bundle.")
    parser.add_argument("--input", required=True, help="Path to ChatGPT conversations.json")
    parser.add_argument("--output", required=True, help="Output directory for OKF bundle")
    args = parser.parse_args()
    
    export_to_okf(args.input, args.output)
