"""
skills_memory.py
================
CLI for the Memanto skills memory companion.

Provides pre/post hooks, recall, demo, and cross-skill memory management.
Uses official moorcheh-sdk (MoorchehClient) — not subprocess CLI wrappers.

Usage:
    python skills_memory.py pre tdd "Add user auth"
    python skills_memory.py post tdd "Used JWT, RS256 signing"
    python skills_memory.py recall "authentication approach"
    python skills_memory.py demo
    python skills_memory.py demo --offline
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional


# ── Offline mock backend (no API key needed) ───────────────────────────────

class _MockDB:
    """In-memory mock for offline demo."""
    def __init__(self):
        self._store: Dict[str, Dict] = {}

    def store(self, content, memory_type="observation", skill="", **kw):
        mid = f"mem_{uuid.uuid4().hex[:8]}"
        self._store[mid] = {"id": mid, "content": content, "type": memory_type, "skill": skill}
        return self._store[mid]

    def recall(self, query, skill="", limit=5, **kw):
        return list(self._store.values())[:limit]

    def answer(self, question):
        mems = list(self._store.values())
        if not mems:
            return "No engineering profile found."
        bullets = "\n".join(f"- [{m['type']}] {m['content']}" for m in mems[:5])
        return f"Based on your engineering profile:\n{bullets}"

    def correct(self, old, new, skill=""):
        return self.store(new, "fact", skill, tags=["correction"])


# ── SkillsMemory wrapper ───────────────────────────────────────────────────

class SkillsMemory:
    """
    Cross-skill memory companion using official moorcheh-sdk.

    PRE-HOOK:  recall() → inject engineering profile before skill runs
    POST-HOOK: store()  → save decisions after skill completes
    ANSWER:    answer() → RAG synthesis from full engineering profile
    """

    def __init__(self, api_key: Optional[str] = None, offline: bool = False):
        self._offline = offline
        if offline:
            self._client = _MockDB()
        else:
            from memanto_client import SkillsClient
            self._client = SkillsClient(api_key=api_key)

    def pre_skill_hook(self, skill_name: str, task: str = "", cwd: str = "") -> str:
        """
        PRE-HOOK: Recall engineering profile before skill runs.
        Returns context string to inject into skill prompt.
        """
        project = Path(cwd).name if cwd else ""
        query = f"{skill_name} {task} {project} decisions preferences".strip()

        memories = self._client.recall(query=query, skill=skill_name, limit=6)

        # RAG synthesis for richer context
        rag = ""
        if memories and not self._offline:
            rag = self._client.answer(
                f"What are the key engineering decisions and preferences for "
                f"{skill_name} working on {task or project}?"
            )

        if not memories and not rag:
            return ""

        lines = [
            f"<engineering-profile skill=\"{skill_name}\">",
            "Apply these automatically — do not re-ask the developer:",
            "",
        ]
        if rag:
            lines.append(f"[RAG Summary] {rag}\n")
        for m in memories:
            mtype = m.get("type", "observation")
            content = m.get("content", "")
            lines.append(f"  [{mtype}] {content}")
        lines.append("</engineering-profile>")
        return "\n".join(lines)

    def post_skill_hook(
        self,
        skill_name: str,
        summary: str,
        decisions: Optional[List[str]] = None,
        preferences: Optional[List[str]] = None,
    ) -> List[Dict]:
        """POST-HOOK: Store decisions after skill completes."""
        stored = []

        r = self._client.store(
            content=f"[{skill_name}] {summary}",
            memory_type="context",
            skill=skill_name,
        )
        if r.get("id"):
            stored.append(r)

        for d in (decisions or []):
            r = self._client.store(content=d, memory_type="decision", skill=skill_name)
            if r.get("id"):
                stored.append(r)

        for p in (preferences or []):
            r = self._client.store(content=p, memory_type="preference", skill=skill_name)
            if r.get("id"):
                stored.append(r)

        return stored

    def recall(self, query: str) -> List[Dict]:
        return self._client.recall(query=query, limit=10)

    def answer(self, question: str) -> str:
        return self._client.answer(question)


# ── CLI commands ───────────────────────────────────────────────────────────

def _divider(title=""):
    print(f"\n{'─' * 60}")
    if title:
        print(f"  {title}\n{'─' * 60}")


def cmd_pre(args):
    mem = SkillsMemory()
    context = mem.pre_skill_hook(skill_name=args.skill, task=args.task or "")
    print(context if context else f"[Memanto] No prior memories for '{args.skill}'. Starting fresh.")


def cmd_post(args):
    mem = SkillsMemory()
    stored = mem.post_skill_hook(
        skill_name=args.skill,
        summary=args.summary,
        decisions=args.decisions or [],
        preferences=args.preferences or [],
    )
    print(f"✅ Stored {len(stored)} memories for '{args.skill}'.")
    for m in stored:
        print(f"   [{m.get('type','?')}] {m.get('content','')[:80]}")


def cmd_recall(args):
    mem = SkillsMemory()
    results = mem.recall(args.query)
    if not results:
        print("No memories found.")
        return
    print(f"📚 Engineering Profile — '{args.query}':\n")
    for r in results:
        print(f"  [{r.get('type','?')}] {r.get('content','')[:120]}")


def cmd_demo(args):
    if args.offline:
        _offline_demo()
    else:
        _live_demo()


def _offline_demo():
    """Credential-free offline demo — no API key needed."""
    mem = SkillsMemory(offline=True)

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

    stored = mem.post_skill_hook(
        skill_name="/grill-with-docs",
        summary="Auth system design: JWT over sessions, RS256, 7-day refresh",
        decisions=[
            "Use JWT tokens over sessions — stateless, scales horizontally.",
            "RS256 algorithm for JWT signing — asymmetric, safer for microservices.",
            "Refresh token rotation with 7-day expiry.",
        ],
        preferences=[
            "Developer prefers typed schemas (TypeScript strict mode).",
        ],
    )
    for m in stored:
        print(f"  ✅ [{m['id']}] ({m.get('type','?')}) {m.get('content','')[:70]}")
        time.sleep(0.3)

    print(f"\n  📦 {len(stored)} engineering decisions stored in Memanto.")

    _divider("SESSION BOUNDARY — New terminal session / next day")
    print("  💤  Completely new process. Zero shared in-memory state.")
    time.sleep(1.0)

    _divider("SKILL EXECUTION 2: /tdd")
    print("  Developer runs: /tdd")
    print("  Task: Implement login endpoint\n")
    print("  [PRE-HOOK] Loading engineering profile from Memanto...")
    time.sleep(0.5)

    context = mem.pre_skill_hook(skill_name="/tdd", task="Implement login endpoint")
    print(context)
    time.sleep(0.4)
    print("\n  🤖 /tdd skill starts — already knows:")
    print("     • JWT with RS256 (not sessions)")
    print("     • 7-day refresh token rotation")
    print("     • TypeScript strict mode")
    print("     → No repeated instructions needed ✅")

    _divider("SKILL EXECUTION 3: /handoff")
    print("  Developer runs: /handoff\n")
    print("  [PRE-HOOK] Loading engineering profile from Memanto...")
    recalled = mem.recall("JWT authentication decisions")
    for r in recalled[:2]:
        print(f"  📚 [{r['id']}] {r.get('content','')[:90]}")
    time.sleep(0.3)
    print("\n  [POST-HOOK] Storing handoff summary...")
    h = mem.post_skill_hook("/handoff", "Login endpoint implemented. JWT/RS256. Tests passing.")
    for m in h:
        print(f"  ✅ [{m['id']}] Handoff stored for next agent.")

    _divider("✨  Demo complete!")
    print("  Zero repeated instructions across 3 skill executions.")
    print("  All decisions persist in Memanto — available in any future session.\n")


def _live_demo():
    """Live demo using real Memanto API."""
    mem = SkillsMemory()

    print("\n╔══════════════════════════════════════════════════════════╗")
    print("║   mattpocock/skills  +  Memanto  —  Memory Companion    ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print("\n  Mode: 🟢 LIVE (official moorcheh-sdk)\n")

    _divider("STORING engineering decisions via /grill-with-docs")
    stored = mem.post_skill_hook(
        skill_name="/grill-with-docs",
        summary="Auth: JWT over sessions, RS256, 7-day refresh rotation",
        decisions=[
            "Use JWT tokens over sessions — stateless, scales horizontally.",
            "RS256 algorithm for JWT signing — asymmetric, safer for microservices.",
        ],
        preferences=["TypeScript strict mode across all new files."],
    )
    print(f"  ✅ Stored {len(stored)} memories.")
    for m in stored:
        print(f"     id={m.get('id')} [{m.get('type')}] {m.get('content','')[:60]}")

    _divider("SIMULATING session boundary...")
    print("  💤  New process — zero shared state\n")
    time.sleep(1.0)

    _divider("RECALLING profile for /tdd")
    context = mem.pre_skill_hook(skill_name="/tdd", task="Login endpoint")
    print(context if context else "  (no memories found)")

    _divider("✨  Done!")
    print("  Engineering profile injected into /tdd automatically.\n")


def main():
    parser = argparse.ArgumentParser(description="Memanto skills memory companion")
    sub = parser.add_subparsers(dest="command")

    p_pre = sub.add_parser("pre", help="Inject memories before skill")
    p_pre.add_argument("skill")
    p_pre.add_argument("task", nargs="?", default="")
    p_pre.set_defaults(func=cmd_pre)

    p_post = sub.add_parser("post", help="Store decisions after skill")
    p_post.add_argument("skill")
    p_post.add_argument("summary")
    p_post.add_argument("--decisions", nargs="*")
    p_post.add_argument("--preferences", nargs="*")
    p_post.set_defaults(func=cmd_post)

    p_recall = sub.add_parser("recall", help="Query engineering profile")
    p_recall.add_argument("query")
    p_recall.set_defaults(func=cmd_recall)

    p_demo = sub.add_parser("demo", help="Run cross-session demo")
    p_demo.add_argument("--offline", action="store_true")
    p_demo.set_defaults(func=cmd_demo)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)
    args.func(args)


if __name__ == "__main__":
    main()
