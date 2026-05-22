#!/usr/bin/env python3
"""
Run the LangGraph Research Agent with Memanto Persistent Memory.

Usage:
    python run_agent.py                                    # Interactive mode
    python run_agent.py --query "quantum error correction" # Single query
    python run_agent.py --session my-session --query "AI safety"
"""

import os
import argparse
from dotenv import load_dotenv

load_dotenv()

from agent import create_agent


def main():
    parser = argparse.ArgumentParser(description="LangGraph + Memanto Research Agent")
    parser.add_argument("--query", "-q", type=str, help="Research query")
    parser.add_argument("--session", "-s", type=str, default="default", help="Session ID")
    parser.add_argument("--model", "-m", type=str, default="gpt-4o-mini", help="LLM model")
    parser.add_argument("--agent-id", type=str, default="langgraph-research-agent", help="Agent ID")
    parser.add_argument("--scope-id", type=str, default="research", help="Memanto scope ID")
    args = parser.parse_args()

    print("🧠 LangGraph + Memanto Research Agent")
    print("=" * 50)

    # Create the agent
    print(f"🔧 Initializing agent (scope: {args.scope_id})...")
    agent = create_agent(
        agent_id=args.agent_id,
        scope_id=args.scope_id,
        model=args.model,
    )
    print("✅ Agent ready!\n")

    if args.query:
        # Single query mode
        _run_query(agent, args.query, args.session)
    else:
        # Interactive mode
        print("Enter your research queries (Ctrl+C to exit):\n")
        while True:
            try:
                query = input("🔍 > ").strip()
                if not query:
                    continue
                _run_query(agent, query, args.session)
                print()
            except (KeyboardInterrupt, EOFError):
                print("\n👋 Goodbye!")
                break


def _run_query(agent, query: str, session_id: str):
    """Run a single query through the agent."""
    print(f"\n🔍 Researching: {query}")
    print("-" * 40)

    result = agent.invoke({
        "query": query,
        "session_id": session_id,
        "research_notes": [],
        "recalled_memories": [],
        "new_memories": [],
        "final_answer": "",
    })

    # Show recalled memories
    recalled = result.get("recalled_memories", [])
    if recalled:
        print(f"\n🔎 Recalled {len(recalled)} memories from previous sessions:")
        for m in recalled:
            print(f"  - [{m.get('type', '?').upper()}] {m.get('content', '')[:60]}... "
                  f"(conf: {m.get('confidence', 0):.2f})")

    # Show new memories stored
    new = result.get("new_memories", [])
    if new:
        print(f"\n📝 Stored {len(new)} new memories:")

    # Show final answer
    answer = result.get("final_answer", "")
    if answer:
        print(f"\n✅ Answer:\n{answer}")


if __name__ == "__main__":
    main()
