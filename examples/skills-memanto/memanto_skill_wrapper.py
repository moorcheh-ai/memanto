"""
Memanto + Developer Skills Integration

Memanto acts as a global, active memory companion across different
developer skill executions (mattpocock/skills ecosystem).

Instead of treating each CLI command as an isolated event, this wrapper:
1. Captures skill inputs/outputs
2. Distills architectural decisions, codebase quirks, and preferences
3. Injects relevant past context when new skills are invoked
4. Builds a growing knowledge graph of the developer's engineering choices

Usage:
    python memanto_skill_wrapper.py --skill /grill-with-docs --args "explain the auth flow"
    python memanto_skill_wrapper.py --execute "npx /tdd --framework vitest --watch"
"""

import os
import sys
import json
import subprocess
import argparse
from datetime import datetime
from pathlib import Path

# Memanto SDK
try:
    from memanto import MemantoClient, MemantoBrain
    MEMANTO_AVAILABLE = True
except ImportError:
    MEMANTO_AVAILABLE = False
    print("⚠️  Memanto SDK not installed. Running in dry-run mode (no persistence).")
    print("   Install with: pip install memanto")

# ── Configuration ─────────────────────────────────────────────────────

MEMANTO_API_KEY = os.environ.get("MEMANTO_API_KEY", "")
MEMANTO_BRAIN_ID = os.environ.get("MEMANTO_BRAIN_ID", "developer-skills-brain")
HISTORY_FILE = Path.home() / ".memanto" / "skill_history.json"

# ── Memory Manager ────────────────────────────────────────────────────


class SkillMemoryManager:
    """Manages memory across developer skill executions."""

    def __init__(self):
        self.client = None
        if MEMANTO_AVAILABLE and MEMANTO_API_KEY:
            self.client = MemantoClient(api_key=MEMANTO_API_KEY)
        self.local_history = self._load_local_history()

    def _load_local_history(self) -> list[dict]:
        """Load local fallback history."""
        if HISTORY_FILE.exists():
            return json.loads(HISTORY_FILE.read_text())
        return []

    def _save_local_history(self):
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        HISTORY_FILE.write_text(json.dumps(self.local_history, indent=2))

    def get_relevant_context(self, skill_name: str, query: str) -> str:
        """Retrieve relevant context from past skill executions."""
        context_parts = []

        # Try Memanto first
        if self.client:
            try:
                memories = self.client.query(
                    brain_id=MEMANTO_BRAIN_ID,
                    query=f"Context relevant to: {skill_name} - {query}",
                    limit=5,
                )
                if memories:
                    context_parts.append("=== Past Context (from Memanto) ===")
                    for m in memories:
                        context_parts.append(f"- {m.get('content', str(m))[:300]}")
            except Exception:
                pass

        # Fallback to local history
        if not context_parts and self.local_history:
            related = [
                h for h in self.local_history[-20:]
                if any(w in h.get("query", "").lower() for w in query.lower().split()[:3])
            ]
            if related:
                context_parts.append("=== Past Context (local history) ===")
                for r in related[-3:]:
                    context_parts.append(f"- [{r.get('skill')}]: {r.get('output', '')[:200]}")

        return "\n".join(context_parts)

    def store_skill_execution(
        self, skill: str, query: str, output: str, metadata: dict = None
    ):
        """Store a skill execution result as a memory."""
        memory = {
            "timestamp": datetime.now().isoformat(),
            "skill": skill,
            "query": query[:500],
            "output": output[:1000],
            "metadata": metadata or {},
            "workdir": os.getcwd(),
        }

        # Store in local history
        self.local_history.append(memory)
        if len(self.local_history) > 100:
            self.local_history = self.local_history[-100:]
        self._save_local_history()

        # Store in Memanto
        if self.client:
            try:
                # Extract key decisions for more durable storage
                key_decisions = self._extract_key_decisions(skill, query, output)

                for decision in key_decisions:
                    self.client.store(
                        brain_id=MEMANTO_BRAIN_ID,
                        content=decision,
                        metadata={
                            "type": "engineering_decision",
                            "skill": skill,
                            "timestamp": memory["timestamp"],
                        },
                    )

                # Also store the full execution
                self.client.store(
                    brain_id=MEMANTO_BRAIN_ID,
                    content=json.dumps({
                        "summary": f"Executed {skill} for: {query[:100]}",
                        "key_output": output[:500],
                    }),
                    metadata={
                        "type": "skill_execution",
                        "skill": skill,
                        "timestamp": memory["timestamp"],
                    },
                )
                print(f"  💾 Context stored in Memanto brain '{MEMANTO_BRAIN_ID}'")
            except Exception as e:
                print(f"  ⚠️  Memanto store failed: {e}")

    def _extract_key_decisions(self, skill: str, query: str, output: str) -> list[str]:
        """Extract engineering decisions from skill output."""
        decisions = []
        text = (query + " " + output).lower()

        decision_patterns = [
            "architecture", "pattern", "design", "decision",
            "use this", "recommend", "prefer", "instead of",
            "best practice", "standard", "convention",
        ]

        for pattern in decision_patterns:
            if pattern in text:
                # Find the sentence containing the decision
                sentences = (query + ". " + output).split(".")
                for sentence in sentences:
                    if pattern in sentence.lower() and len(sentence) > 20:
                        decisions.append(
                            f"[{skill}] {sentence.strip()[:200]} "
                            f"(archived by memanto)"
                        )
                        break

        if not decisions:
            decisions.append(
                f"[{skill}] Executed query: {query[:100]} "
                f"(output length: {len(output)} chars)"
            )

        return decisions

    def get_summary(self) -> dict:
        """Get a summary of all stored memories."""
        return {
            "total_executions": len(self.local_history),
            "skills_used": list(set(h["skill"] for h in self.local_history)),
            "last_execution": self.local_history[-1] if self.local_history else None,
            "memanto_connected": self.client is not None,
            "brain_id": MEMANTO_BRAIN_ID,
        }


# ── Skill Executor ────────────────────────────────────────────────────


def run_skill(skill_command: str, args_list: list[str]) -> tuple[str, int]:
    """Execute a skill command and capture its output."""
    full_command = [skill_command] + args_list
    print(f"  🚀 Executing: {' '.join(full_command)}")

    try:
        result = subprocess.run(
            full_command,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = result.stdout + result.stderr
        return output, result.returncode
    except FileNotFoundError:
        return f"Error: Command not found: {skill_command}", 1
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 120s", 1
    except Exception as e:
        return f"Error: {e}", 1


# ── Main ──────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Memanto + Developer Skills Integration Wrapper"
    )
    parser.add_argument(
        "--skill", "-s",
        help="Skill command to execute (e.g., /grill-with-docs)"
    )
    parser.add_argument(
        "--args", "-a", nargs="*", default=[],
        help="Arguments to pass to the skill"
    )
    parser.add_argument(
        "--execute", "-e",
        help="Full command string to execute (alternative to --skill + --args)"
    )
    parser.add_argument(
        "--query", "-q",
        help="Natural language description of the task (for memory context)"
    )
    parser.add_argument(
        "--summary", action="store_true",
        help="Show memory summary and exit"
    )
    parser.add_argument(
        "--clear", action="store_true",
        help="Clear local memory history"
    )

    args = parser.parse_args()

    manager = SkillMemoryManager()

    # Show summary
    if args.summary:
        summary = manager.get_summary()
        print(json.dumps(summary, indent=2, default=str))
        return

    # Clear history
    if args.clear:
        if HISTORY_FILE.exists():
            HISTORY_FILE.unlink()
        print("🗑️  Local memory history cleared.")
        return

    # Determine skill command
    if args.execute:
        parts = args.execute.split()
        skill_name = parts[0]
        skill_args = parts[1:]
    elif args.skill:
        skill_name = args.skill
        skill_args = args.args
    else:
        # Interactive mode
        skill_name = input("Skill command: ")
        skill_args = input("Arguments: ").split()
        if not skill_args:
            skill_args = []

    query = args.query or " ".join(skill_args) or skill_name

    # Get relevant context
    context = manager.get_relevant_context(skill_name, query)
    if context:
        print(f"\n📖 Memanto context loaded:")
        print(context)
        print()

    # Execute the skill
    output, exit_code = run_skill(skill_name, skill_args)
    print(f"\n📤 Output (exit code: {exit_code}):")
    print(output[:2000])  # Truncate for display

    # Store the result
    manager.store_skill_execution(
        skill=skill_name,
        query=query,
        output=output,
        metadata={"exit_code": exit_code},
    )

    print(f"\n✅ Execution complete. Memanto memory updated.")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
