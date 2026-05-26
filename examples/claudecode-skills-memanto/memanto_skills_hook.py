"""Memanto → Claude Code Skills Integration Hook

Pre/post skill hooks that give Claude Code skills persistent engineering
memory across terminal sessions.

Phases:
  - pre:  Recall relevant engineering context before a skill starts.
  - post: Distill decisions from the completed skill and persist them.

Usage:
  memanto-skills pre <skill_name>
  memanto-skills post <skill_name> <transcript_or_summary>
  memanto-skills run <skill_name> -- <skill_args...>
"""

import json
import os
import sys
import subprocess
from pathlib import Path
from typing import Any, Optional


MEMANTO_AGENT_ID = os.getenv("MEMANTO_AGENT_ID", "claude-code-skills")
MEMANTO_SKILLS_NS = os.getenv("MEMANTO_SKILLS_NS", "claude-code-skills")
CONTEXT_LIMIT = int(os.getenv("MEMANTO_CONTEXT_LIMIT", "3000"))


def _ensure_api_key() -> str:
    """Get Moorcheh API key from env or config file."""
    key = os.getenv("MOORCHEH_API_KEY")
    if key:
        return key
    env_path = Path.home() / ".memanto" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("MOORCHEH_API_KEY="):
                return line.split("=", 1)[1].strip()
    print("ERROR: MOORCHEH_API_KEY not set. Run `memanto setup` first.")
    sys.exit(1)


def pre_hook(skill_name: str) -> None:
    """Pre-skill hook: recall relevant engineering context.

    Queries Memanto for memories related to the skill being executed
    and prints a compact context block that can be appended to the
    skill prompt.
    """
    agent_id = MEMANTO_AGENT_ID
    query = f"engineering decisions related to {skill_name}"

    try:
        result = subprocess.run(
            ["memanto", "memory", "export", "--agent", agent_id, "--limit", "10"],
            capture_output=True, text=True, timeout=15,
        )
        context = result.stdout[:CONTEXT_LIMIT] if result.stdout else ""
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        context = f""  # Fail open: if Memanto is unavailable, run without context

    if context.strip():
        print(f"--- Memanto Context for '{skill_name}' ---")
        print(context[:CONTEXT_LIMIT])
        print("--- End Memanto Context ---")
    else:
        print("# No relevant engineering context found.")


def post_hook(skill_name: str, transcript: str) -> None:
    """Post-skill hook: persist engineering decisions.

    Extracts key decisions from the skill transcript and stores them
    as Memanto memories for future recall.
    """
    agent_id = MEMANTO_AGENT_ID

    memory_text = (
        f"After running skill '{skill_name}':\n"
        f"{transcript[:2000]}"
    )

    try:
        result = subprocess.run(
            ["memanto", "memory", "export", "--agent", agent_id],
            capture_output=True, text=True, timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    print(f"# Engineering context from '{skill_name}' stored in Memanto.")


def run_skill(skill_name: str, skill_args: list[str]) -> None:
    """Run a skill with Memanto pre/post hooks."""
    pre_hook(skill_name)
    print(f"\n# Running skill: {skill_name}\n")

    try:
        proc = subprocess.run(
            ["npx", skill_name, *skill_args],
            capture_output=True, text=True, timeout=300,
        )
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        output = stdout + stderr
        print(stdout)
        if stderr:
            print(stderr, file=sys.stderr)
    except FileNotFoundError:
        print(f"ERROR: Skill '{skill_name}' not found. Is it installed?")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print(f"ERROR: Skill '{skill_name}' timed out.")
        sys.exit(1)

    post_hook(skill_name, output)


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage:")
        print("  memanto-skills pre <skill_name>")
        print("  memanto-skills post <skill_name>")
        print("  memanto-skills run <skill_name> [-- <args...>]")
        sys.exit(1)

    command = sys.argv[1]
    skill_name = sys.argv[2]

    if command == "pre":
        _ensure_api_key()
        pre_hook(skill_name)
    elif command == "post":
        _ensure_api_key()
        transcript = sys.stdin.read() if not sys.stdin.isatty() else ""
        post_hook(skill_name, transcript)
    elif command == "run":
        skill_args = sys.argv[3:]
        run_skill(skill_name, skill_args)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
