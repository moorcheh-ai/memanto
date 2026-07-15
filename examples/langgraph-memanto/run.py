#!/usr/bin/env python3
"""
run.py  –  LangGraph + Memanto Cross-Session Memory Demo
=========================================================

Demonstrates the core bounty requirement:
  Session A  (--session research)  Agent learns facts → stores in Memanto
  Session B  (--session recall)    NEW process, agent recalls without being told

Usage:
    # Session A: agent researches and stores memories
    python run.py --session research

    # Session B: completely new run, agent recalls from Session A
    python run.py --session recall

    # Interactive chat (auto-recalls on every message)
    python run.py --session chat

    # Mock mode (no server or LLM needed — for Asciinema recording)
    python run.py --mock
"""

import argparse
import os
import sys
import uuid

BANNER = """
╔══════════════════════════════════════════════════════════╗
║      LangGraph  +  Memanto  –  Permanent Agent Brain     ║
║   Session A stores  →  Session B recalls  (any time)     ║
╚══════════════════════════════════════════════════════════╝"""


# ── Mock mode (offline, no LLM/server) ────────────────────────────────────────


def run_mock():
    """Fully offline demo — record this for Asciinema."""
    import time
    import uuid as _uuid

    db = {}

    def store(content, mtype="fact"):
        mid = f"mem_{_uuid.uuid4().hex[:8]}"
        db[mid] = {"id": mid, "content": content, "type": mtype}
        return mid

    def recall(query):
        return list(db.values())[:3]

    print(BANNER)
    print("\n  Mode: 🟡 MOCK (offline — safe to record)\n")

    print("─" * 60)
    print("  SESSION A  –  Agent learns and stores facts")
    print("─" * 60)

    user_msg = "I'm researching quantum computing. Focus on error correction."
    print(f"\n  👤 User: {user_msg}")
    time.sleep(0.5)
    print("  🤖 Agent: Starting research on quantum computing error correction...")
    time.sleep(0.4)

    facts = [
        (
            "Quantum error correction requires ~1000 physical qubits per logical qubit.",
            "fact",
        ),
        ("Surface codes are the leading error correction approach in 2025.", "fact"),
        ("User prefers concise bullet-point summaries.", "preference"),
        (
            "User is focused on near-term practical applications, not theory.",
            "preference",
        ),
    ]
    print("\n  [Memanto] Storing memories...")
    stored = []
    for content, mtype in facts:
        mid = store(content, mtype)
        stored.append(mid)
        print(f"  ✅ [{mid}] ({mtype}) {content[:70]}")
        time.sleep(0.35)

    print("\n  📦 Session A complete. 4 memories stored in Memanto.")

    print("\n")
    print("─" * 60)
    print("  SESSION B  –  New process, agent recalls from Session A")
    print("─" * 60)
    print("\n  💤  Simulating new Python process / next day...")
    time.sleep(1.0)

    print("\n  [recall_node] Auto-loading Memanto context at session start...")
    recalled = recall("quantum computing")
    for m in recalled:
        print(f"  📚 [{m['id']}] {m['content'][:90]}")
    time.sleep(0.5)

    user_msg2 = "What were we working on? Give me a summary."
    print(f"\n  👤 User: {user_msg2}")
    time.sleep(0.6)
    print("  🤖 Agent: Based on our previous sessions (recalled from Memanto):")
    print("     • Researching quantum computing error correction")
    print("     • Key finding: ~1000 physical qubits needed per logical qubit")
    print("     • Surface codes are the leading approach")
    print("     • You prefer concise bullet summaries & practical focus")
    time.sleep(0.5)

    print("\n")
    print("─" * 60)
    print("  CONTRADICTION CORRECTION  –  Updating an outdated fact")
    print("─" * 60)
    old_id = stored[0]
    old_fact = "~1000 physical qubits per logical qubit"
    new_fact = "Recent Google research suggests ~100 physical qubits per logical qubit with new codes (2025)."
    print(f"\n  ⚠️  Outdated: {old_fact}")
    print(f"  🔄 Correcting [{old_id}]...")
    time.sleep(0.5)
    import uuid as _u

    new_id = f"mem_{_u.uuid4().hex[:8]}"
    db[new_id] = {
        "id": new_id,
        "content": new_fact,
        "type": "fact",
        "score": 0.99,
        "metadata": {"previous_content": old_fact, "correction": True},
    }
    print(f"  ✅ New corrected memory stored: [{new_id}]")
    print(f"     └─ Old fact preserved in metadata.previous_content of [{new_id}]")

    print(f"\n{'─' * 60}")
    print("  ✨  Demo complete!")
    print("  💾  All memories persist in Memanto — recall them in any future session.")
    print(f"{'─' * 60}\n")


# ── Live mode ──────────────────────────────────────────────────────────────────


def run_live(session_type: str, args):
    from graph import build_graph
    from langchain_core.messages import HumanMessage

    graph = build_graph(
        base_url=args.url,
        api_key=args.api_key,
        agent_id=args.namespace,
        model=args.model,
    )
    session_id = str(uuid.uuid4())[:8]

    scenarios = {
        "research": [
            "I'm researching quantum computing error correction. What should I know?",
            "Remember that I prefer concise bullet-point answers.",
            "Store the key finding: surface codes require ~1000 physical qubits per logical qubit.",
        ],
        "recall": [
            "What have we discussed before? Check your memory.",
            "What are my preferences for how you respond?",
            "Summarise everything you know about my quantum computing research.",
        ],
        "chat": None,  # interactive
    }

    print(BANNER)
    print(f"\n  Session: {session_type.upper()}  |  Namespace: {args.namespace}\n")

    if session_type == "chat":
        print("  Interactive mode. Type 'quit' to exit.\n")
        messages = []
        while True:
            user_input = input("  👤 You: ").strip()
            if user_input.lower() in ("quit", "exit", "q"):
                break
            messages.append(HumanMessage(content=user_input))
            state = {"messages": messages, "session_id": session_id}
            result = graph.invoke(state)
            last = result["messages"][-1]
            print(f"\n  🤖 Agent: {last.content}\n")
            messages = list(result["messages"])
    else:
        prompts = scenarios[session_type]
        messages = []
        for prompt in prompts:
            print(f"  👤 User: {prompt}")
            messages.append(HumanMessage(content=prompt))
            state = {"messages": messages, "session_id": session_id}
            result = graph.invoke(state)
            last = result["messages"][-1]
            print(f"  🤖 Agent: {last.content}\n")
            messages = list(result["messages"])


# ── Entry ──────────────────────────────────────────────────────────────────────


def main():
    p = argparse.ArgumentParser(description="LangGraph + Memanto demo")
    p.add_argument(
        "--mock", action="store_true", help="Offline mode, no server/LLM needed"
    )
    p.add_argument(
        "--session", choices=["research", "recall", "chat"], default="research"
    )
    p.add_argument(
        "--url", default=os.getenv("MEMANTO_BASE_URL", "http://127.0.0.1:8000")
    )
    p.add_argument("--api-key", default=os.getenv("MOORCHEH_API_KEY", ""))
    p.add_argument("--namespace", default="langgraph-agent")
    p.add_argument("--model", default="gpt-4o")
    args = p.parse_args()

    if args.mock:
        run_mock()
        return

    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  OPENAI_API_KEY not set.")

    try:
        run_live(args.session, args)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("💡 Try --mock for offline demo, or ensure 'memanto serve' is running.")
        sys.exit(1)


if __name__ == "__main__":
    main()
