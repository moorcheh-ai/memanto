"""
LangChain & LangGraph Memory to OKF (Open Knowledge Format) Migration Adapter.

Bounty #1609: The Great Memory Migration
Author: Prakhar Dewangan
"""

import os
import json
import uuid
import yaml
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

def generate_okf_frontmatter(
    memory_id: str,
    memory_type: str,
    created_at: Optional[str] = None,
    confidence: float = 0.9,
    tags: Optional[List[str]] = None,
    source: str = "langchain"
) -> str:
    """Generates standard YAML frontmatter for OKF 0.2 specification."""
    if not created_at:
        created_at = datetime.now(timezone.utc).isoformat()
    
    metadata = {
        "id": memory_id,
        "type": memory_type,
        "created_at": created_at,
        "confidence": confidence,
        "source": source,
        "provenance": "migrated",
        "tags": tags or ["langchain", "agent-memory"]
    }
    return f"---\n{yaml.dump(metadata, sort_keys=False)}---\n"

def parse_langchain_history(history_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Parses LangChain message history and extracts salient memories.
    Handles standard HumanMessage, AIMessage, and SystemMessage schemas.
    """
    extracted_memories = []
    
    for idx, msg in enumerate(history_data):
        msg_type = msg.get("type", "message")
        content = msg.get("content", "")
        timestamp = msg.get("additional_kwargs", {}).get("timestamp")
        
        if not content or len(content.strip()) < 5:
            continue
            
        mem_type = "fact"
        if "decided" in content.lower() or "chosen" in content.lower():
            mem_type = "decision"
        elif "prefer" in content.lower() or "always" in content.lower():
            mem_type = "preference"
        elif msg_type == "system":
            mem_type = "context"
            
        mem_id = f"mem-lc-{uuid.uuid4().hex[:8]}"
        extracted_memories.append({
            "id": mem_id,
            "type": mem_type,
            "content": content.strip(),
            "created_at": timestamp,
            "tags": ["langchain", msg_type]
        })
        
    return extracted_memories

def export_to_okf_bundle(memories: List[Dict[str, Any]], output_dir: str):
    """Writes memories to an OKF bundle directory."""
    os.makedirs(output_dir, exist_ok=True)
    memories_dir = os.path.join(output_dir, "memories")
    os.makedirs(memories_dir, exist_ok=True)
    
    manifest = {
        "okf_version": "0.2.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "source_framework": "langchain",
        "total_memories": len(memories),
        "generator": "memanto-langchain-migrator"
    }
    with open(os.path.join(output_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        
    for mem in memories:
        frontmatter = generate_okf_frontmatter(
            memory_id=mem["id"],
            memory_type=mem["type"],
            created_at=mem.get("created_at"),
            tags=mem.get("tags")
        )
        filepath = os.path.join(memories_dir, f"{mem['id']}.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(frontmatter + "\n" + mem["content"] + "\n")
            
    print(f"[✓] Successfully exported {len(memories)} memories to OKF bundle at: {output_dir}")

def migrate_langchain_file(input_json_path: str, output_bundle_dir: str):
    """Main migration entrypoint for LangChain JSON history files."""
    if not os.path.exists(input_json_path):
        raise FileNotFoundError(f"Input file {input_json_path} does not exist.")
        
    with open(input_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    messages = data if isinstance(data, list) else data.get("messages", [])
    memories = parse_langchain_history(messages)
    export_to_okf_bundle(memories, output_bundle_dir)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Migrate LangChain / LangGraph memory to OKF bundle.")
    parser.add_argument("--input", "-i", required=True, help="Path to LangChain message history JSON export")
    parser.add_argument("--output", "-o", default="./okf_bundle", help="Output directory for OKF bundle")
    args = parser.parse_args()
    
    migrate_langchain_file(args.input, args.output)