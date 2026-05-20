#!/usr/bin/env bash
# Dump every memory stored for the current project's Memanto agent.
# Useful as the bounty submission artifact (or just for debugging).

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${HERE}/../../.." && pwd)"

python3 - "${PROJECT_ROOT}" <<'PY'
import os
import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent if __file__ != "<stdin>"
        else Path(sys.argv[1]) / "examples" / "claudecode-skills-memanto" / "hooks"),
)

# Walk up to find the hooks dir from current invocation
hooks_dir = Path.home() / ".claude" / "hooks" / "memanto"
if not hooks_dir.exists():
    print(f"Hooks dir not found at {hooks_dir} — did you run install.sh?")
    sys.exit(1)
sys.path.insert(0, str(hooks_dir))

from _memanto_common import derive_agent_id, load_env  # type: ignore

project_root = Path(sys.argv[1])
agent_id, project_name = derive_agent_id(project_root)

api_key = load_env()
if not api_key:
    print("MOORCHEH_API_KEY not set (looked in ~/.claude/hooks/memanto/.env).")
    sys.exit(1)

from memanto.cli.client.sdk_client import SdkClient
client = SdkClient(api_key=api_key)

print(f"\nProject: {project_name}")
print(f"Agent:   {agent_id}\n")

# Pull every memory by paging
all_memories = []
for query in ["", "convention", "decision", "preference", "error", "context"]:
    try:
        result = client.recall(agent_id=agent_id, query=query or "*", limit=100)
        for m in result.get("memories", []):
            if m.get("memory_id") and m.get("memory_id") not in {x.get("memory_id") for x in all_memories}:
                all_memories.append(m)
    except Exception as exc:
        print(f"  recall failed for query={query!r}: {exc}")

print(f"Found {len(all_memories)} memories:\n")
for i, m in enumerate(all_memories, 1):
    print(f"[{i}] ({m.get('type')}, conf={m.get('confidence', 0):.2f}) {m.get('title')}")
    content = m.get("content", "")
    if len(content) > 200:
        content = content[:197] + "..."
    print(f"    → {content}")
    tags = m.get("tags") or []
    if tags:
        print(f"    tags: {', '.join(tags[:5])}")
    print()
PY
