#!/usr/bin/env python3
"""
Run the LangGraph Customer Support Agent with Memanto Persistent Memory.

Usage:
    python run_agent.py --customer cust-123 --message "My payment failed"
    python run_agent.py  # Interactive mode
"""

import os
import argparse
from dotenv import load_dotenv

load_dotenv()

from agent import create_agent


def main():
    parser = argparse.ArgumentParser(description="LangGraph + Memanto Customer Support Agent")
    parser.add_argument("--message", "-m", type=str, help="Customer message/ticket")
    parser.add_argument("--customer", "-c", type=str, default="cust-001", help="Customer ID")
    parser.add_argument("--ticket", "-t", type=str, default=None, help="Ticket ID")
    parser.add_argument("--session", "-s", type=str, default="default", help="Session ID")
    parser.add_argument("--model", type=str, default="gpt-4o-mini", help="LLM model")
    parser.add_argument("--scope-id", type=str, default="customer-support", help="Memanto scope")
    args = parser.parse_args()

    print("🎧 LangGraph + Memanto Customer Support Agent")
    print("=" * 50)

    print(f"🔧 Initializing agent (scope: {args.scope_id})...")
    agent = create_agent(
        scope_id=args.scope_id,
        model=args.model,
    )
    print("✅ Agent ready!\n")

    if args.message:
        ticket_id = args.ticket or f"TKT-{hash(args.message) % 10000:04d}"
        _run_ticket(agent, args.message, args.customer, ticket_id, args.session)
    else:
        print("Enter customer messages (Ctrl+C to exit):\n")
        ticket_counter = 1
        while True:
            try:
                customer = input("👤 Customer ID: ").strip() or f"cust-{ticket_counter:03d}"
                message = input("💬 Message: ").strip()
                if not message:
                    continue
                ticket_id = f"TKT-{ticket_counter:04d}"
                _run_ticket(agent, message, customer, ticket_id, args.session)
                ticket_counter += 1
                print()
            except (KeyboardInterrupt, EOFError):
                print("\n👋 Shift ended!")
                break


def _run_ticket(agent, message: str, customer_id: str, ticket_id: str, session_id: str):
    """Process a single support ticket through the agent."""
    print(f"\n🎫 Ticket {ticket_id} from {customer_id}")
    print(f"💬 \"{message}\"")
    print("-" * 40)

    result = agent.invoke({
        "ticket_id": ticket_id,
        "customer_id": customer_id,
        "message": message,
        "severity": "",
        "category": "",
        "customer_history": [],
        "similar_issues": [],
        "investigation_notes": [],
        "resolution": "",
        "follow_up": "",
        "session_id": session_id,
    })

    # Show triage
    severity = result.get("severity", "unknown")
    category = result.get("category", "unknown")
    print(f"\n📊 Triage: {severity.upper()} / {category}")

    # Show recalled customer history
    history = result.get("customer_history", [])
    if history:
        print(f"📜 Recalled {len(history)} customer memories from previous sessions:")
        for m in history[:3]:
            print(f"   - [{m.get('type', '?').upper()}] {m.get('content', '')[:60]}...")

    # Show similar issues
    similar = result.get("similar_issues", [])
    if similar:
        print(f"🔍 Found {len(similar)} similar past issues:")
        for m in similar[:3]:
            print(f"   - [{m.get('type', '?').upper()}] {m.get('content', '')[:60]}...")

    # Show resolution
    resolution = result.get("resolution", "")
    if resolution:
        print(f"\n✅ Resolution:\n{resolution[:500]}")

    # Show follow-up
    follow_up = result.get("follow_up", "")
    if follow_up:
        print(f"\n📩 Follow-up:\n{follow_up[:300]}")


if __name__ == "__main__":
    main()
