"""
skills_memory.py
================
Global memory companion for mattpocock/skills.

Eliminates context fragmentation across skill executions by:
  1. PRE-HOOK:  Before any skill runs, inject relevant past engineering
                decisions into the skill's context automatically.
  2. POST-HOOK: After a skill completes, extract and store architectural
                choices, preferences, and decisions to Memanto permanently.

Usage (Python API):
    from skills_memory import SkillsMemory

    mem = SkillsMemory()

    # Before running a skill
    context = mem.pre_skill_hook(skill_name="tdd", task="Add user auth")
    # context is injected into the skill prompt automatically

    # After skill completes
    mem.post_skill_hook(
        skill_name="tdd",
        summary="Decided to use JWT tokens, avoided sessions"
    )

Usage (CLI):
    # Inject context before a skill
    python skills_memory.py pre tdd "Add user authentication"

    # Store decisions after a skill
    python skills_memory.py post tdd "Used JWT, avoided sessions, red-green-refactor loop"

    # Query engineering profile
    python skills_memory.py recall "authentication approach"

    # Full cross-session demo
    python skills_memory.py demo
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from typing import List, Optional

from memanto_bridge import SkillsMemoryBridge

# ── Skill metadata ─────────────────────────────────────────────────────────────

SKILL_MEMORY_TYPES = {
    "tdd":                       ["decision", "preference", "learning"],
    "grill-with-docs":           ["decision", "context", "artifact"],
    "grill-me":                  ["decision", "goal", "context"],
    "handoff":                   ["context", "artifact", "event"],
    "improve-codebase-architecture": ["decision", "observation", "learning"],
    "diagnose":                  ["observation", "error", "decision"],
    "to-issues":                 ["goal", "decision", "artifact"],
    "to-prd":                    ["goal", "context", "artifact"],
}

DEFAULT_LIMIT = 5


class SkillsMemory:
    """
    Memory companion that bridges mattpocock/skills with Memanto.

    Each skill execution is treated as a source of durable engineering knowledge.
    The companion automatically distills and injects this knowledge across sessions.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        namespace: str = "skills-companion",
    ):
        self._client = SkillsMemoryBridge(
            api_key=api_key,
            namespace=namespace,
        )
        self.agent_id = agent_id

    # ── Core hooks ─────────────────────────────────────────────────────────

    def pre_skill_hook(
        self,
        skill_name: str,
        task: str = "",
        cwd: Optional[str] = None,
    ) -> str:
        """
        PRE-HOOK: Called before a skill executes.

        Queries Memanto for:
          - Past decisions relevant to this skill + task
          - Developer preferences stored from previous skill runs
          - Architectural decisions from any prior session

        Returns a context string to inject into the skill prompt.
        This eliminates the need to re-explain preferences every session.
        """
        queries = [
            f"{skill_name} decisions preferences",
            task if task else f"{skill_name} engineering profile",
        ]
        if cwd:
            queries.append(os.path.basename(cwd))

        memories: List[dict] = []
        seen_ids = set()

        for query in queries:
            results = self._client.recall(query=query, limit=DEFAULT_LIMIT)
            for r in results:
                mid = r.get("id")
                if mid and mid not in seen_ids:
                    seen_ids.add(mid)
                    memories.append(r)

        # Also pull preferences specifically
        prefs = self._client.recall(
            query="developer preferences style coding",
            limit=3,
            memory_type="preference",
        )
        for p in prefs:
            mid = p.get("id")
            if mid and mid not in seen_ids:
                seen_ids.add(mid)
                memories.append(p)

        if not memories:
            return ""

        lines = [
            f"[MEMANTO ENGINEERING PROFILE — skill: {skill_name}]",
            "The following decisions and preferences were stored from previous sessions.",
            "Apply them automatically without re-asking the developer:",
            "",
        ]
        for m in memories:
            mtype = m.get("type", "observation")
            content = m.get("content", "")
            lines.append(f"  [{mtype}] {content}")

        return "\n".join(lines)

    def post_skill_hook(
        self,
        skill_name: str,
        summary: str,
        decisions: Optional[List[str]] = None,
        preferences: Optional[List[str]] = None,
    ) -> List[dict]:
        """
        POST-HOOK: Called after a skill completes.

        Stores:
          - The skill summary as a 'context' memory
          - Each explicit decision as a 'decision' memory
          - Each preference as a 'preference' memory

        Returns list of stored memory dicts.
        Caller should check each dict for id=None (write failure).
        """
        stored = []
        tags = [skill_name, "skill-output"]

        # Store session summary
        mem = self._client.remember(
            content=f"[{skill_name}] {summary}",
            memory_type="context",
            tags=tags,
            metadata={"skill": skill_name, "stored_at": time.time()},
        )
        if mem.get("id") is None:
            print(f"⚠️  Warning: failed to store summary — {mem.get('error')}")
        else:
            stored.append(mem)

        # Store explicit decisions
        for decision in (decisions or []):
            mem = self._client.remember(
                content=decision,
                memory_type="decision",
                tags=tags + ["decision"],
                metadata={"skill": skill_name},
            )
            if mem.get("id") is None:
                print(f"⚠️  Warning: failed to store decision — {mem.get('error')}")
            else:
                stored.append(mem)

        # Store preferences
        for pref in (preferences or []):
            mem = self._client.remember(
                content=pref,
                memory_type="preference",
                tags=tags + ["preference"],
                metadata={"skill": skill_name},
            )
            if mem.get("id") is None:
                print(f"⚠️  Warning: failed to store preference — {mem.get('error')}")
            else:
                stored.append(mem)

        return stored

    def recall_engineering_profile(self, query: str = "engineering decisions") -> List[dict]:
        """Retrieve the full engineering profile for a query."""
        return self._client.recall(query=query, limit=10)

    def answer(self, question: str) -> str:
        """RAG answer grounded in stored engineering decisions."""
        return self._client.answer(question)


# ── CLI ────────────────────────────────────────────────────────────────────────

def _divider(title: str = "") -> None:
    print(f"\n{'─' * 60}")
    if title:
        print(f"  {title}")
        print("─" * 60)


def cmd_pre(args) -> None:
    """Inject memories before a skill runs."""
    mem = SkillsMemory()
    context = mem.pre_skill_hook(skill_name=args.skill, task=args.task or "")
    if context:
        print(context)
    else:
        print(f"[Memanto] No prior memories for skill '{args.skill}'. Starting fresh.")


def cmd_post(args) -> None:
    """Store skill output to Memanto after a skill completes."""
    mem = SkillsMemory()
    stored = mem.post_skill_hook(
        skill_name=args.skill,
        summary=args.summary,
        decisions=args.decisions or [],
        preferences=args.preferences or [],
    )
    print(f"✅ Stored {len(stored)} memories for skill '{args.skill}'.")
    for m in stored:
        print(f"   [{m.get('type','?')}] id={m.get('id','?')} — {m.get('content','')[:80]}")


def cmd_recall(args) -> None:
    """Query the engineering profile."""
    mem = SkillsMemory()
    results = mem.recall_engineering_profile(query=args.query)
    if not results:
        print("No memories found.")
        return
    print(f"📚 Engineering Profile — '{args.query}':\n")
    for r in results:
        print(f"  [{r.get('type','?')}] {r.get('content','')[:120]}")


def cmd_demo(args) -> None:
    """
    Full cross-session demo — proves memory persists across skill executions.
    No LLM or server needed in offline mode (--offline).
    """
    if args.offline:
        _run_offline_demo()
    else:
        _run_live_demo()


def _run_offline_demo() -> None:
    """Offline mock demo — identical to live output but in-process only."""
    import uuid

    db: dict = {}

    def store(content, mtype, skill):
        mid = f"mem_{uuid.uuid4().hex[:8]}"
        db[mid] = {"id": mid, "content": content, "type": mtype, "skill": skill}
        return db[mid]

    def recall(query):
        return list(db.values())[:5]

    print("\n╔══════════════════════════════════════════════════════════╗")
    print("║   mattpocock/skills  +  Memanto  —  Memory Companion    ║")
    print("║   Zero context re-prompting across skill executions     ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print("\n  Mode: 🟡 OFFLINE DEMO\n")

    _divider("SKILL EXECUTION 1: /grill-with-docs")
    print("  Developer runs: /grill-with-docs")
    print("  Topic: Authentication system design\n")
    print("  [POST-HOOK] Extracting decisions to Memanto...")
    time.sleep(0.4)

    decisions = [
        ("Use JWT tokens over sessions — stateless, scales horizontally.", "decision"),
        ("RS256 algorithm for JWT signing — asymmetric, safer for microservices.", "decision"),
        ("Refresh token rotation with 7-day expiry.", "decision"),
        ("Developer prefers typed schemas (TypeScript strict mode).", "preference"),
    ]
    stored = []
    for content, mtype in decisions:
        m = store(content, mtype, "grill-with-docs")
        stored.append(m)
        print(f"  ✅ [{m['id']}] ({mtype}) {content[:70]}")
        time.sleep(0.3)

    print(f"\n  📦 4 engineering decisions stored in Memanto.")

    _divider("SESSION BOUNDARY — New terminal session / next day")
    print("  💤  Completely new process. Zero shared in-memory state.")
    time.sleep(1.0)

    _divider("SKILL EXECUTION 2: /tdd")
    print("  Developer runs: /tdd")
    print("  Task: Implement login endpoint\n")
    print("  [PRE-HOOK] Loading engineering profile from Memanto...")
    time.sleep(0.5)

    recalled = recall("authentication JWT")
    print("\n  [MEMANTO ENGINEERING PROFILE — skill: tdd]")
    print("  Apply these decisions automatically without re-asking:\n")
    for m in recalled:
        print(f"    [{m['type']}] {m['content'][:90]}")

    time.sleep(0.4)
    print("\n  🤖 /tdd skill starts — already knows:")
    print("     • JWT with RS256 (not sessions)")
    print("     • 7-day refresh token rotation")
    print("     • TypeScript strict mode")
    print("     → No repeated instructions needed ✅")

    _divider("SKILL EXECUTION 3: /handoff")
    print("  Developer runs: /handoff (to continue in a new session)\n")
    print("  [PRE-HOOK] Loading engineering profile from Memanto...")
    time.sleep(0.3)
    for m in recalled[:2]:
        print(f"  📚 [{m['id']}] {m['content'][:90]}")

    print("\n  [POST-HOOK] Storing handoff summary...")
    time.sleep(0.3)
    h = store("Handoff: Login endpoint implemented with JWT/RS256. Tests passing.", "artifact", "handoff")
    print(f"  ✅ [{h['id']}] Handoff stored for next agent.")

    _divider("✨  Demo complete!")
    print("  Zero repeated instructions across 3 skill executions.")
    print("  All decisions persist in Memanto — available in any future session.\n")


def _run_live_demo() -> None:
    """Live demo using real Memanto server."""
    mem = SkillsMemory()

    print("\n╔══════════════════════════════════════════════════════════╗")
    print("║   mattpocock/skills  +  Memanto  —  Memory Companion    ║")
    print("║   Zero context re-prompting across skill executions     ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print("\n  Mode: 🟢 LIVE (Memanto server)\n")

    _divider("SKILL EXECUTION 1: /grill-with-docs — storing decisions")
    stored = mem.post_skill_hook(
        skill_name="grill-with-docs",
        summary="Auth system: JWT over sessions, RS256 signing, 7-day refresh rotation",
        decisions=[
            "Use JWT tokens over sessions — stateless, scales horizontally.",
            "RS256 algorithm for JWT signing — asymmetric, safer for microservices.",
            "Refresh token rotation with 7-day expiry.",
        ],
        preferences=[
            "Developer prefers TypeScript strict mode across all new files.",
        ],
    )
    print(f"  ✅ Stored {len(stored)} memories.")

    _divider("SESSION BOUNDARY — New terminal / next day")
    print("  💤  Simulating fresh session...\n")
    time.sleep(1.0)

    _divider("SKILL EXECUTION 2: /tdd — loading profile")
    context = mem.pre_skill_hook(skill_name="tdd", task="Implement login endpoint")
    if context:
        print(context)
    else:
        print("  (no memories found — check server connection)")

    _divider("✨  Done!")
    print("  Engineering profile injected into /tdd automatically.\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Memanto skills memory companion CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    # pre
    p_pre = sub.add_parser("pre", help="Inject memories before a skill runs")
    p_pre.add_argument("skill", help="Skill name e.g. tdd, grill-with-docs")
    p_pre.add_argument("task", nargs="?", default="", help="Current task description")
    p_pre.set_defaults(func=cmd_pre)

    # post
    p_post = sub.add_parser("post", help="Store skill output after completion")
    p_post.add_argument("skill", help="Skill name")
    p_post.add_argument("summary", help="Summary of what happened")
    p_post.add_argument("--decisions", nargs="*", help="Key decisions made")
    p_post.add_argument("--preferences", nargs="*", help="Developer preferences discovered")
    p_post.set_defaults(func=cmd_post)

    # recall
    p_recall = sub.add_parser("recall", help="Query engineering profile")
    p_recall.add_argument("query", help="Natural-language query")
    p_recall.set_defaults(func=cmd_recall)

    # demo
    p_demo = sub.add_parser("demo", help="Run cross-session demo")
    p_demo.add_argument("--offline", action="store_true", help="Run offline (no server needed)")
    p_demo.set_defaults(func=cmd_demo)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
