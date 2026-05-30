"""Mattpocock Skills Adapter - CLI wrappers for mattpocock/skills."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from skill_memory import _SKILL_TAG_MAP, extract_skill_name, post_hook, pre_hook
from memory_backend import get_backend

SKILLS_MANIFEST = {
    "engineering": [
        {"name": "diagnose", "description": "Diagnose bugs and issues in codebase"},
        {"name": "grill-with-docs", "description": "Grill plan against domain model and docs"},
        {"name": "triage", "description": "Triage and prioritize issues"},
        {"name": "improve-codebase-architecture", "description": "Improve codebase architecture"},
        {"name": "tdd", "description": "Test-driven development workflow"},
        {"name": "to-issues", "description": "Convert plans to GitHub issues"},
        {"name": "to-prd", "description": "Convert ideas to product requirements"},
        {"name": "zoom-out", "description": "Zoom out and see the big picture"},
        {"name": "prototype", "description": "Rapid prototyping"},
        {"name": "setup-matt-pocock-skills", "description": "Setup mattpocock skills"},
    ],
    "productivity": [
        {"name": "caveman", "description": "Simple task management"},
        {"name": "grill-me", "description": "Interview-style planning"},
        {"name": "handoff", "description": "Create handoff document for next session"},
        {"name": "write-a-skill", "description": "Write a new Claude Code skill"},
    ],
}


def _wrapper_script(skill_name: str, adapter_path: str) -> str:
    """Generate a shell wrapper script for a skill."""
    return f"""#!/usr/bin/env bash
# Memanto-aware wrapper for /{skill_name}
set -euo pipefail
SKILL_NAME="{skill_name}"
USER_INPUT="$*"
CONTEXT=$(python3 "{adapter_path}" recall "$SKILL_NAME" "$USER_INPUT" 2>/dev/null || true)
if [ -n "$CONTEXT" ]; then
    export MEMANTO_SKILL_CONTEXT="$CONTEXT"
    echo "$CONTEXT"
    echo "---"
fi
echo "[Memanto] Skill /$SKILL_NAME invoked with memory context"
echo "[Memanto] After skill completes, run: python3 {adapter_path} store $SKILL_NAME <output>"
"""


def generate_wrappers(output_dir: Path | str | None = None) -> list[Path]:
    """Generate shell wrapper scripts for all skills."""
    output_dir = Path(output_dir) if output_dir else Path(__file__).parent / "wrappers"
    output_dir.mkdir(parents=True, exist_ok=True)
    adapter_path = str(Path(__file__).resolve())
    generated = []
    for bucket, skills in SKILLS_MANIFEST.items():
        for skill in skills:
            name = skill["name"]
            wrapper_path = output_dir / f"memanto-{name}"
            content = _wrapper_script(name, adapter_path)
            wrapper_path.write_text(content, encoding="utf-8")
            wrapper_path.chmod(0o755)
            generated.append(wrapper_path)
    return generated


def list_skills() -> list[dict[str, str]]:
    """Return all available skills with descriptions."""
    skills = []
    for bucket, bucket_skills in SKILLS_MANIFEST.items():
        for skill in bucket_skills:
            skills.append({
                "name": skill["name"],
                "bucket": bucket,
                "description": skill["description"],
                "tags": _SKILL_TAG_MAP.get(skill["name"], []),
            })
    return skills


def run_with_memory(skill_name: str, user_input: str) -> dict[str, Any]:
    """Run a skill with Memanto memory injection and extraction."""
    context = pre_hook(user_input, skill_name)
    return {
        "skill_name": skill_name,
        "injected_context": context,
        "message": f"Injected {len(context)} chars of memory context.",
    }


def store_output(skill_name: str, output_text: str, user_input: str = "") -> dict[str, Any]:
    """Post-hook: store engineering signals from skill output."""
    memory_ids = post_hook(user_input, output_text, skill_name)
    return {
        "skill_name": skill_name,
        "stored_count": len(memory_ids),
        "memory_ids": memory_ids,
    }


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: mattpocock_adapter.py <command> [args]")
        print("Commands: generate, list, recall, store, run")
        sys.exit(1)
    command = sys.argv[1]
    if command == "generate":
        wrappers = generate_wrappers()
        print(f"Generated {len(wrappers)} wrapper scripts in ./wrappers/")
    elif command == "list":
        skills = list_skills()
        print(f"{len(skills)} mattpocock/skills available:")
        for s in skills:
            tags = ", ".join(s["tags"]) if s["tags"] else "-"
            print(f"  /{s['name']:30s} [{s['bucket']:12s}] tags: {tags}")
    elif command == "recall":
        if len(sys.argv) < 4:
            print("Usage: recall <skill_name> <query>")
            sys.exit(1)
        skill_name = sys.argv[2]
        query = " ".join(sys.argv[3:])
        context = pre_hook(query, skill_name)
        if context:
            print(context)
    elif command == "store":
        if len(sys.argv) < 4:
            print("Usage: store <skill_name> <output_text>")
            sys.exit(1)
        skill_name = sys.argv[2]
        output = " ".join(sys.argv[3:])
        result = store_output(skill_name, output)
        print(f"Stored {result['stored_count']} engineering memories")
    elif command == "run":
        if len(sys.argv) < 4:
            print("Usage: run <skill_name> <prompt>")
            sys.exit(1)
        skill_name = sys.argv[2]
        prompt = " ".join(sys.argv[3:])
        result = run_with_memory(skill_name, prompt)
        print(json.dumps(result, indent=2))
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
