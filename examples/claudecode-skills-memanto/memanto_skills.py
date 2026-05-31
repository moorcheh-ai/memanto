#!/usr/bin/env python3
"""
Memanto Skills Companion for Claude Code

A CLI integration layer that injects persistent cross-session memory 
into modular developer skill workflows, preventing Context Fragmentation.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from memanto.app.utils.errors import AgentAlreadyExistsError
from memanto.cli.client.sdk_client import SdkClient

# Load local environment variables if available
load_dotenv()


def get_client() -> SdkClient:
    """Initialize SdkClient from environment variable."""
    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        print(
            "Error: MOORCHEH_API_KEY environment variable is not set.\n"
            "Please export your Moorcheh API key: export MOORCHEH_API_KEY='mch_...'",
            file=sys.stderr,
        )
        sys.exit(1)
    return SdkClient(api_key=api_key)


def ensure_agent_active(client: SdkClient, agent_id: str) -> None:
    """Ensure the target agent exists and has an active session."""
    try:
        client.create_agent(
            agent_id=agent_id,
            pattern="tool",
            description="Global memory for Claude Code skills",
        )
    except AgentAlreadyExistsError:
        pass
    except Exception:
        # Ignore other duplicate/validation errors, and attempt session activation
        pass

    # Activate agent session for 24 hours
    client.activate_agent(agent_id, duration_hours=24)


def handle_start(args: argparse.Namespace) -> None:
    """
    Handle the start of a skill execution.
    Queries Memanto for relevant past engineering decisions and writes
    them to a local workspace file for the AI agent to consume.
    """
    client = get_client()
    agent_id = args.agent_id or "claudecode-skills"
    
    print(f"[*] Connecting to Memanto (Agent: {agent_id})...")
    ensure_agent_active(client, agent_id)

    # Build search query from task and file path
    query_parts = [args.task]
    if args.file:
        query_parts.append(f"in file {args.file}")
    query = " ".join(query_parts)

    print(f"[*] Querying memory for: '{query}'...")
    
    # Recall memories matching our task
    recall_result = client.recall(
        agent_id=agent_id,
        query=query,
        limit=5,
        min_similarity=0.3,
    )

    memories = recall_result.get("memories", [])
    
    # Format as a beautiful Markdown document
    output_lines = [
        "# 🧠 Memanto Persistent Context\n",
        "This file is dynamically managed by the **Memanto Skills Companion**.",
        "It injects relevant past architectural decisions, codebase preferences, "
        "and guidelines to prevent Context Fragmentation across different sessions.\n",
        "---",
        f"**Active Task:** *{args.task}*",
    ]
    if args.file:
        output_lines.append(f"**Current File Path:** `{args.file}`")
    output_lines.append("")

    if memories:
        output_lines.append("## 🔑 Relevant Architectural Decisions & Preferences found:")
        for idx, mem in enumerate(memories, 1):
            mem_type = mem.get("type", "fact")
            title = mem.get("title", "Untitled Memory")
            content = mem.get("content", "")
            confidence = mem.get("confidence", 1.0)
            tags = mem.get("tags", [])
            tag_str = f" `[{', '.join(tags)}]`" if tags else ""
            
            output_lines.append(
                f"### {idx}. [{mem_type.upper()}] {title} (Confidence: {confidence}){tag_str}\n"
                f"{content}\n"
            )
        print(f"[+] Found {len(memories)} relevant memories. Injecting into workspace...")
    else:
        output_lines.append(
            "## 🆕 Fresh Workspace Context\n"
            "No matching architectural decisions or preferences found in Memanto yet.\n"
            "Feel free to build and make choices! They will be recorded on session end."
        )
        print("[*] No matching memories found. Injecting fresh workspace template...")

    # Write file to the specified out_file
    out_path = Path(args.out_file)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(output_lines), encoding="utf-8")
        print(f"[+] Context successfully injected to: {out_path}")
        print("[!] Tip: Tell your Claude Code agent to read this file before writing code.")
    except Exception as e:
        print(f"[-] Failed to write context file: {e}", file=sys.stderr)
        sys.exit(1)


def handle_end(args: argparse.Namespace) -> None:
    """
    Handle the end of a skill execution.
    Distills and saves the session's key choices and preferences into Memanto.
    """
    client = get_client()
    agent_id = args.agent_id or "claudecode-skills"

    print(f"[*] Connecting to Memanto (Agent: {agent_id})...")
    ensure_agent_active(client, agent_id)

    # Classify the memory type based on content or user tags
    memory_type = "decision"
    tags_list = [t.strip().lower() for t in args.tags.split(",") if t.strip()]
    
    if "preference" in tags_list:
        memory_type = "preference"
    elif "error" in tags_list or "bug" in tags_list:
        memory_type = "error"
    elif "learning" in tags_list:
        memory_type = "learning"

    title = f"Decision: {args.task[:50]}"
    if len(args.task) > 50:
        title += "..."

    print(f"[*] Distilling and storing new memory: '{title}'...")
    
    result = client.remember(
        agent_id=agent_id,
        memory_type=memory_type,
        title=title,
        content=args.summary,
        confidence=args.confidence,
        tags=tags_list,
        source="claudecode-skills",
        provenance="skills_companion",
    )

    print(f"[+] Memory successfully stored in Memanto!")
    print(f"    - Memory ID: {result['memory_id']}")
    print(f"    - Type: {memory_type.upper()}")
    print(f"    - Title: {title}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Memanto Skills Companion for Claude Code - Cross-Session Persistent Memory Layer"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 'start' command
    start_parser = subparsers.add_parser(
        "start",
        help="Query Memanto for relevant context and inject it into the local workspace.",
    )
    start_parser.add_argument("--task", required=True, help="Description of the active task.")
    start_parser.add_argument("--file", help="Path to the file being edited or reviewed.")
    start_parser.add_argument(
        "--agent-id",
        default="claudecode-skills",
        help="Memanto agent/namespace ID to query (default: claudecode-skills).",
    )
    start_parser.add_argument(
        "--out-file",
        default=".claude/skills_memory.md",
        help="Path where the context Markdown file will be written (default: .claude/skills_memory.md).",
    )

    # 'end' command
    end_parser = subparsers.add_parser(
        "end",
        help="Distill and save session decisions and engineering preferences to Memanto.",
    )
    end_parser.add_argument(
        "--task", required=True, help="Description of the task that was completed."
    )
    end_parser.add_argument(
        "--summary",
        required=True,
        help="Summary of architectural decisions, preferences, or learnings to remember.",
    )
    end_parser.add_argument(
        "--confidence",
        type=float,
        default=0.9,
        help="Confidence score from 0.0 to 1.0 (default: 0.9).",
    )
    end_parser.add_argument(
        "--tags",
        default="",
        help="Comma-separated list of tags (e.g. 'auth,jwt,preference').",
    )
    end_parser.add_argument(
        "--agent-id",
        default="claudecode-skills",
        help="Memanto agent/namespace ID to store memory in (default: claudecode-skills).",
    )

    args = parser.parse_args()

    if args.command == "start":
        handle_start(args)
    elif args.command == "end":
        handle_end(args)


if __name__ == "__main__":
    main()
