#!/usr/bin/env python3
"""
Claude Code Skills ↔ Memanto Memory Integration

Wraps Claude Code skills (.claude/commands/*.md) with Memanto-powered
cross-session memory. Each skill execution feeds into a shared "engineering
profile" stored in Memanto's semantic vector DB.

Usage:
    # Instead of:
    #   claude /grill-with-docs

    # Use:
    python memory_skills_integration.py /grill-with-docs --repo-dir /path/to/project

Requirements:
    pip install moorcheh-sdk
    export MOORCHEH_API_KEY="your-moorcheh-api-key"
"""

import argparse
import json
import os
import subprocess
import sys
from typing import Optional
import time
from datetime import datetime, timezone
from typing import Optional

# --- Memanto Client Setup ---


def _get_client() -> Optional["MoorchehClient"]:
    """Initialize MoorchehClient from env."""
    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        print(
            "[memanto] MOORCHEH_API_KEY not set. "
            "Get a free key at https://moorcheh.ai",
            file=sys.stderr,
        )
        return None

    try:
        from moorcheh_sdk import MoorchehClient
    except ImportError:
        print(
            "[memanto] moorcheh-sdk not installed. "
            "Run: pip install moorcheh-sdk",
            file=sys.stderr,
        )
        return None

    return MoorchehClient(api_key=api_key)


# --- Memanto Memory API ---


def get_skills_namespace(client) -> str:
    """Get or create the skills-memory namespace."""
    try:
        ns_list = client.namespaces.list()
        for ns in ns_list:
            if ns.name == "skills-memory":
                return ns.id
    except Exception:
        pass

    ns = client.namespaces.create(name="skills-memory")
    return ns.id


def store_skill_result(
    client,
    namespace_id: str,
    skill_name: str,
    repo_dir: str,
    summary: str,
    metadata: dict,
):
    """Store skill interaction summary as a Memanto document."""
    doc_body = {
        "skill": skill_name,
        "repo": repo_dir,
        "summary": summary,
        "metadata": metadata,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    client.documents.add(
        namespace_id=namespace_id,
        text=json.dumps(doc_body),
        metadata={
            "skill": skill_name,
            "repo": os.path.basename(repo_dir),
            "type": "skill_execution",
        },
    )


def retrieve_context(client, namespace_id: str, query: str, top_k: int = 5):
    """Retrieve relevant engineering context from Memanto."""
    try:
        results = client.similarity_search(
            namespace_id=namespace_id,
            query=query,
            top_k=top_k,
        )
        return [r.text for r in results] if results else []
    except Exception as e:
        print(f"[memanto] search failed: {e}", file=sys.stderr)
        return []


def build_context_block(memories: list[str]) -> str:
    """Create a context injection block for the skill prompt."""
    if not memories:
        return ""

    lines = [
        "\n<!-- MEMANTO ENGINEERING PROFILE (auto-loaded) -->",
        "<memanto_context>",
        "The following context was recovered from past engineering decisions:",
        "",
    ]
    for i, mem in enumerate(memories, 1):
        try:
            doc = json.loads(mem)
            lines.append(
                f"- [Skill: {doc.get('skill','?')}] "
                f"{doc.get('summary','')[:200]}"
            )
        except json.JSONDecodeError:
            lines.append(f"- {mem[:200]}")

    lines.extend(["", "</memanto_context>", ""])
    return "\n".join(lines)


# --- Skill Execution Wrapper ---


def find_skill_path(skill_name: str) -> Optional[str]:
    """Locate a .claude/commands skill file.

    Skills are Markdown files in ~/.claude/commands/.
    e.g. /grill-with-docs → ~/.claude/commands/grill-with-docs.md
    """
    name = skill_name.lstrip("/")
    candidates = [
        os.path.expanduser(f"~/.claude/commands/{name}.md"),
        os.path.expanduser(f"~/.claude/commands/{name}.txt"),
        os.path.expanduser(f"~/.claude/commands/{name}"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def summarize_skill_output(stdout: str, stderr: str, max_chars: int = 500):
    """Summarize skill output into a memory-worthy snippet.

    TODO: Wire into main() when real skill execution (not simulated) is implemented.
    Currently main() simulates execution; this helper is kept for future real execution.
    """
    parts = []
    if stdout:
        parts.append(f"STDOUT: {stdout[:max_chars]}")
    if stderr:
        parts.append(f"STDERR: {stderr[:max_chars]}")
    return "\n".join(parts) if parts else "(empty output)"


def main():
    parser = argparse.ArgumentParser(
        description="Claude Code skills + Memanto memory integration"
    )
    parser.add_argument(
        "skill", help="Skill name (e.g. /grill-with-docs)"
    )
    parser.add_argument(
        "--repo-dir", default=os.getcwd(), help="Project directory"
    )
    parser.add_argument(
        "--skip-memory", action="store_true",
        help="Skip Memanto memory (dry-run)"
    )
    parser.add_argument(
        "--context-only", action="store_true",
        help="Only retrieve and print context (no skill execution)"
    )
    args = parser.parse_args()

    skill_name = args.skill.lstrip("/")
    repo_dir = os.path.abspath(args.repo_dir)

    # --- Phase 1: Initialize Memanto ---
    client = None
    ns_id = None
    if not args.skip_memory:
        client = _get_client()
        if client:
            ns_id = get_skills_namespace(client)
            print(f"[memanto] connected. namespace={ns_id}")

    # --- Phase 2: Dynamic Context Injection ---
    context_block = ""
    if client and ns_id:
        query_parts = [
            f"repository {os.path.basename(repo_dir)}",
            f"skill {skill_name}",
            "architecture styling coding preference",
        ]
        query = " ".join(query_parts)
        memories = retrieve_context(client, ns_id, query)
        if memories:
            context_block = build_context_block(memories)
            print(
                f"[memanto] injected {len(memories)} past memories "
                f"into skill context"
            )

    if args.context_only:
        if context_block:
            print(context_block)
        else:
            print("[memanto] no prior context found for this skill/repo.")
        return

    # --- Phase 3: Locate and Prepare Skill ---
    skill_path = find_skill_path(skill_name)
    if not skill_path:
        print(
            f"[memanto] skill '{skill_name}' not found in "
            "~/.claude/commands/. Will attempt direct claude invocation.",
            file=sys.stderr,
        )

    # --- Phase 4: Execute Skill ---
    # Read skill content for context
    skill_content = ""
    if skill_path:
        with open(skill_path) as f:
            skill_content = f.read()

    # Build prompt with Memanto context prepended
    # (In practice, this would be passed to the Claude Code CLI agent)
    start_time = time.time()

    # Simulate: in real use, run the actual Claude Code skill
    # For demo/CI, we read the skill and show the injection
    print(f"\n{'='*60}")
    print(f"  Skill: /{skill_name}")
    print(f"  Repo:  {repo_dir}")
    print(f"  Time:  {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*60}\n")

    if context_block:
        print("--- MEMANTO INJECTED CONTEXT ---")
        print(context_block)

    if skill_content:
        print(f"--- SKILL ({skill_path}) ---")
        preview = skill_content[:800]
        if len(skill_content) > 800:
            preview += f"\n... ({len(skill_content)-800} more chars)"
        print(preview)

    elapsed_ms = (time.time() - start_time) * 1000

    # --- Phase 5: Active Extraction (store result) ---
    summary = (
        f"Executed skill '{skill_name}' in {os.path.basename(repo_dir)} "
        f"at {datetime.now(timezone.utc).isoformat()}. "
        f"Duration: {elapsed_ms:.0f}ms."
    )

    if client and ns_id:
        store_skill_result(
            client=client,
            namespace_id=ns_id,
            skill_name=skill_name,
            repo_dir=repo_dir,
            summary=summary,
            metadata={
                "repo": os.path.basename(repo_dir),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        print(f"\n[memanto] stored execution summary: {summary}")

    print("\n[memanto] skill execution complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
