"""Auto-setup for CLAUDE.md integration.

Adds Memanto memory hooks to your project's CLAUDE.md file.
"""

from __future__ import annotations

import os
from pathlib import Path


MEMANTO_SECTION = """
## Memory (Memanto)

After completing any skill, capture memories:
```bash
python .claude/memanto-hook.py capture --skill <skill-name> --summary "What was decided and learned"
```

Before starting any skill, inject relevant context:
```bash
python .claude/memanto-hook.py inject --skill <skill-name>
```

### Environment Variables

```bash
export MOORCHEH_API_KEY=mch_xxxxxxxxxxxxxx  # Get at https://console.moorcheh.ai/api-keys
export MEMANTO_AGENT_ID=claudecode-myproject  # Unique per project
```

### Memory Types

- `decision` — Architectural choices (e.g., "Use PostgreSQL over MongoDB")
- `preference` — Coding style (e.g., "Prefer functional over OOP")
- `fact` — Codebase knowledge (e.g., "API uses JWT auth")
- `pattern` — Recurring patterns (e.g., "All services follow Repository pattern")
"""


def setup_claude_md(project_dir: str = ".") -> bool:
    """Add Memanto memory hooks to CLAUDE.md.

    Args:
        project_dir: Path to the project root

    Returns:
        True if setup was successful
    """
    claude_md_path = Path(project_dir) / "CLAUDE.md"

    if not claude_md_path.exists():
        print(f"⚠️  No CLAUDE.md found at {claude_md_path}")
        print("   Create one first, then run this script.")
        return False

    content = claude_md_path.read_text()

    if "Memory (Memanto)" in content:
        print("✅ CLAUDE.md already has Memanto section.")
        return True

    # Add the Memanto section
    content += MEMANTO_SECTION
    claude_md_path.write_text(content)

    print(f"✅ Added Memanto section to {claude_md_path}")
    return True


def setup_hook_script(project_dir: str = ".") -> bool:
    """Copy the hook script to .claude/ directory.

    Args:
        project_dir: Path to the project root

    Returns:
        True if setup was successful
    """
    claude_dir = Path(project_dir) / ".claude"
    claude_dir.mkdir(exist_ok=True)

    hook_path = claude_dir / "memanto-hook.py"

    # Get the hook source
    import claudecode_memanto.hook as hook_module

    hook_source = Path(hook_module.__file__).read_text()
    hook_path.write_text(hook_source)

    print(f"✅ Installed hook script to {hook_path}")
    return True


if __name__ == "__main__":
    import sys

    project_dir = sys.argv[1] if len(sys.argv) > 1 else "."

    print("🧠 Setting up Memanto for Claude Code...")
    print("=" * 50)

    setup_claude_md(project_dir)
    setup_hook_script(project_dir)

    print("\n📝 Next steps:")
    print("1. Get a Moorcheh API key: https://console.moorcheh.ai/api-keys")
    print("2. Set MOORCHEH_API_KEY in your environment")
    print("3. Set MEMANTO_AGENT_ID to a unique project name")
    print("4. Start using skills — memories will be captured automatically!")
