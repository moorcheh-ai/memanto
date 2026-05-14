from __future__ import annotations

import argparse

from graph import run_support_turn


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a single LangGraph + Memanto support turn.")
    parser.add_argument("--agent-id", default="langgraph-support-demo")
    parser.add_argument("--customer-id", default="customer-42")
    parser.add_argument("--session-label", default="day-1")
    parser.add_argument(
        "--message",
        required=True,
        help="The customer message for this turn.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = run_support_turn(
        agent_id=args.agent_id,
        customer_id=args.customer_id,
        session_label=args.session_label,
        message=args.message,
    )

    print("=" * 72)
    print(f"Session: {args.session_label}")
    print(f"Customer: {args.customer_id}")
    print(f"Used LLM: {result.get('used_llm', False)}")
    print("-" * 72)
    print("Message:")
    print(args.message)
    print("-" * 72)
    print("Recalled memory:")
    print(result.get("memory_context", ""))
    print("-" * 72)
    print(f"Persisted memories: {result.get('persisted_count', 0)}")
    print("-" * 72)
    print("Reply:")
    print(result.get("reply", ""))
    print("=" * 72)


if __name__ == "__main__":
    main()
