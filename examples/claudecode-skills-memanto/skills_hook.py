#!/usr/bin/env python3
"""
Memanto Integration Hook for Claude Code Skills
Enables cross-skill active memory retrieval and storage.
"""

import os
import sys
import argparse
from datetime import datetime

# Add the parent directory of 'memanto' package to path to make sure we can import it
# even if it's not installed in system site-packages yet.
current_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

try:
    from memanto.cli.client.sdk_client import SdkClient
    from memanto.app.utils.errors import AgentNotFoundError
except ImportError:
    print("[MEMANTO ERROR] SDK not found. Make sure the script is run inside the memanto workspace or 'memanto' is installed.")
    sys.exit(1)


def get_client():
    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        print("[MEMANTO WARNING] MOORCHEH_API_KEY environment variable is not set.")
        print("                  Active memory companion will be bypassed. Setup your key at https://moorcheh.ai/")
        return None
    try:
        return SdkClient(api_key=api_key)
    except Exception as e:
        print(f"[MEMANTO ERROR] Failed to initialize Memanto client: {e}")
        return None


def ensure_agent(client, agent_id):
    try:
        client.get_agent(agent_id)
    except AgentNotFoundError:
        print(f"[MEMANTO] Agent '{agent_id}' does not exist. Creating default developer profile...")
        try:
            client.create_agent(
                agent_id=agent_id,
                pattern="tool",
                description="Global active memory agent for developer skills."
            )
            print(f"[MEMANTO] Created agent '{agent_id}' successfully.")
        except Exception as e:
            print(f"[MEMANTO ERROR] Failed to create agent '{agent_id}': {e}")
            sys.exit(1)


def handle_start(args):
    client = get_client()
    if not client:
        return

    agent_id = args.agent_id or "claudecode-developer"
    ensure_agent(client, agent_id)

    # Activate session
    try:
        client.activate_agent(agent_id)
    except Exception as e:
        print(f"[MEMANTO ERROR] Failed to activate agent session: {e}")
        return

    print(f"\n[MEMANTO] Querying active memory for task: '{args.task}' (Skill: {args.skill})...")

    # Construct the query combining the skill context and the task
    query = f"Engineering preferences, guidelines, architecture choices, coding conventions, or past decisions related to {args.task} and skill {args.skill}"
    
    try:
        recall_result = client.recall(
            agent_id=agent_id,
            query=query,
            limit=5
        )
        memories = recall_result.get("memories", [])

        if not memories:
            print("[MEMANTO] No existing relevant memories found for this task.")
            return

        print("\n========================================================")
        print("🧠 MEMANTO ACTIVE SYSTEM CONSTRAINTS (INJECTED CONTEXT)")
        print("========================================================")
        print("Based on your past work, please adhere to these guidelines:")
        for idx, mem in enumerate(memories, 1):
            mtype = mem.get("type", "fact")
            content = mem.get("content", "")
            confidence = mem.get("confidence", 1.0)
            print(f"  {idx}. [{mtype.upper()} - Conf: {confidence}] {content}")
        print("========================================================\n")
    except Exception as e:
        print(f"[MEMANTO ERROR] Failed to retrieve memories: {e}")


def handle_end(args):
    client = get_client()
    if not client:
        return

    agent_id = args.agent_id or "claudecode-developer"
    
    # Check if active session exists or activate
    try:
        client.activate_agent(agent_id)
    except Exception as e:
        print(f"[MEMANTO ERROR] Failed to activate agent session: {e}")
        return

    print(f"\n[MEMANTO] Extracted engineering patterns from skill '{args.skill}'. Storing to memory profile...")

    summary_text = args.summary.strip()
    if not summary_text:
        print("[MEMANTO WARNING] Empty summary passed. Skipping memory capture.")
        return

    try:
        # Save a general decision/learning memory
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        title = f"Skill {args.skill} completion on {timestamp}"
        # Use explicitly provided type if given; otherwise infer from summary keywords.
        # Known limitation: keyword inference is approximate — e.g. "I learned to prefer X"
        # will match "prefer" and be stored as "preference" instead of "learning".
        # Pass --memory-type to the CLI to override when the inferred type is wrong.
        if args.memory_type:
            mtype = args.memory_type
        elif "prefer" in summary_text.lower() or "like" in summary_text.lower():
            mtype = "preference"
        elif "learn" in summary_text.lower() or "find out" in summary_text.lower():
            mtype = "learning"
        else:
            mtype = "decision"

        result = client.remember(
            agent_id=agent_id,
            memory_type=mtype,
            title=title,
            content=summary_text,
            confidence=0.95,
            provenance="inferred",
            source="claude_code",
            tags=["claudecode", args.skill, "interactive-session"]
        )
        
        print(f"[MEMANTO] Captured new {mtype} memory successfully. (ID: {result.get('memory_id')})")
    except Exception as e:
        print(f"[MEMANTO ERROR] Failed to store memory: {e}")


def main():
    parser = argparse.ArgumentParser(description="Memanto Integration Hook for Claude Code Developer Skills")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Start command parser
    start_parser = subparsers.add_parser("start", help="Retrieve relevant memories at skill startup")
    start_parser.add_argument("--skill", required=True, help="Name of the skill being executed")
    start_parser.add_argument("--task", required=True, help="The description of the task")
    start_parser.add_argument("--agent-id", help="Custom Memanto agent ID")

    # End command parser
    end_parser = subparsers.add_parser("end", help="Persist architectural outcomes and preferences at skill completion")
    end_parser.add_argument("--skill", required=True, help="Name of the skill that completed")
    end_parser.add_argument("--summary", required=True, help="Summary of decisions, preferences or patterns to save")
    end_parser.add_argument("--agent-id", help="Custom Memanto agent ID")
    end_parser.add_argument(
        "--memory-type",
        choices=["decision", "preference", "learning"],
        default=None,
        help="Explicit memory type to store (default: inferred from summary keywords)"
    )

    args = parser.parse_args()

    if args.command == "start":
        handle_start(args)
    elif args.command == "end":
        handle_end(args)


if __name__ == "__main__":
    main()
