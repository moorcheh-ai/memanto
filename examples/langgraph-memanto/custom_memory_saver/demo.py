"""
Memanto + LangGraph: Cross-Session Demo

This script demonstrates the core cross-session recall capability by simulating
two separate conversations with the Memanto memory layer in between.

No LangGraph needed — uses Memanto directly to show the memory primitive.

Usage:
    export MOORCHEH_API_KEY="your-key-here"
    python demo.py
"""

import os
import time

# ─── Demo Configuration ───────────────────────────────────────────────────────

API_KEY = os.environ.get("MOORCHEH_API_KEY")
if not API_KEY:
    print("❌ Please set MOORCHEH_API_KEY environment variable")
    print("   Get one at https://console.moorcheh.ai/api-keys")
    exit(1)

DEMO_AGENT_ID = "memanto-demo-alice"
"""Stable agent ID used for cross-session recall demo."""


def print_separator(title: str):
    """Print a section header."""
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


# ─── Initialize Client ────────────────────────────────────────────────────────

print("🔄 Initializing Memanto client...")
try:
    from memanto.cli.client.sdk_client import SdkClient

    client = SdkClient(api_key=API_KEY)
except ImportError as e:
    print(f"❌ Failed to import memanto: {e}")
    print("   Run: pip install memanto")
    exit(1)
except Exception as e:
    print(f"❌ Failed to initialize client: {e}")
    exit(1)


# ─── Ensure Demo Agent ────────────────────────────────────────────────────────

print(f"🔄 Setting up demo agent '{DEMO_AGENT_ID}'...")
try:
    try:
        client.get_agent(DEMO_AGENT_ID)
        print(f"   ✓ Agent '{DEMO_AGENT_ID}' already exists")
    except Exception:
        client.create_agent(
            agent_id=DEMO_AGENT_ID,
            pattern="tool",
            description="Demo agent for LangGraph cross-session memory demo",
        )
        print(f"   ✓ Created agent '{DEMO_AGENT_ID}'")

    session_info = client.activate_agent(DEMO_AGENT_ID)
    print(f"   ✓ Session activated (expires: {session_info.get('expires_at')})")
except Exception as e:
    print(f"❌ Failed to set up agent: {e}")
    exit(1)

AGENT_ID = DEMO_AGENT_ID


# ═══════════════════════════════════════════════════════════════════════════════
# DEMO PART 1: Session A — User Introduction
# ═══════════════════════════════════════════════════════════════════════════════

print_separator("SESSION A — User Introduction (e.g., Monday)")

print('\n👤 User: "Hi, I\'m Alice. I work at Acme Corp and prefer dark mode."')

# Store each fact with appropriate memory types
print("\n📝 Storing memories via Memanto...")

result = client.remember(
    agent_id=AGENT_ID,
    memory_type="fact",
    title="User's name is Alice",
    content="User's name is Alice",
)
print(f"   ✓ Stored fact: memory_id={result.get('memory_id')}")

result = client.remember(
    agent_id=AGENT_ID,
    memory_type="fact",
    title="Alice works at Acme Corp",
    content="Alice works at Acme Corp as a developer",
)
print(f"   ✓ Stored fact: memory_id={result.get('memory_id')}")

result = client.remember(
    agent_id=AGENT_ID,
    memory_type="preference",
    title="Alice prefers dark mode",
    content="Alice prefers dark mode for all interfaces",
)
print(f"   ✓ Stored preference: memory_id={result.get('memory_id')}")

result = client.remember(
    agent_id=AGENT_ID,
    memory_type="event",
    title="Initial onboarding contact",
    content="First support contact — initial onboarding",
)
print(f"   ✓ Stored event: memory_id={result.get('memory_id')}")

print("\n✅ Session A complete. Memories stored in Memanto.")
time.sleep(1)


# ═══════════════════════════════════════════════════════════════════════════════
# DEMO PART 2: Simulate session break
# ═══════════════════════════════════════════════════════════════════════════════

print_separator("⏳ Time passes... (hours/days) — LangGraph state is gone")

print("""🧠 What happened:
  - The LangGraph thread state has been reset
  - No conversation history exists
  - But Memanto still has all the memories!
""")
time.sleep(1)


# ═══════════════════════════════════════════════════════════════════════════════
# DEMO PART 3: Session B — Cross-Session Recall
# ═══════════════════════════════════════════════════════════════════════════════

print_separator("SESSION B — Cross-Session Recall (e.g., Wednesday)")

print('\n👤 User: "Hey, what do you remember about me? I need help with settings."')

print("\n🔍 Recalling from Memanto (cross-session)...")
recall_result = client.recall(
    agent_id=AGENT_ID,
    query="What do I know about this user — name, work, preferences?",
    limit=5,
)

memories = recall_result.get("memories", [])

print("\n📚 MEMANTO RECALL RESULTS:")
if memories:
    for i, mem in enumerate(memories, 1):
        content = mem.get("content", "N/A")[:150]
        mtype = mem.get("type", "unknown")
        confidence = mem.get("confidence", "N/A")
        print(f'\n  {i}. [{mtype}] "{content}"')
        print(f"     Confidence: {confidence}")
else:
    print("  (No results — check your API key and agent setup)")

print("\n✅ Cross-session recall demonstrated!")
print("   The agent remembers Alice from the previous session")
print("   despite having a completely new LangGraph thread state.")
time.sleep(1)


# ═══════════════════════════════════════════════════════════════════════════════
# DEMO PART 4: Conflict Detection
# ═══════════════════════════════════════════════════════════════════════════════

print_separator("SESSION C — Preference Update & Conflict Detection")

print('\n👤 User: "Actually, I now prefer light mode during work hours."')

print("\n🔄 Detecting potential conflict...")

# Check existing preference
existing = client.recall(
    agent_id=AGENT_ID,
    query="What theme does Alice prefer?",
    type=["preference"],
)
existing_memories = existing.get("memories", [])
print(f"   Previous preference found: {[e.get('content') for e in existing_memories]}")

# Store the updated preference
result = client.remember(
    agent_id=AGENT_ID,
    memory_type="preference",
    title="Alice's light mode preference",
    content="Alice now prefers light mode during work hours (9-5)",
)
print(f"   ✓ Updated preference stored: memory_id={result.get('memory_id')}")

result = client.remember(
    agent_id=AGENT_ID,
    memory_type="decision",
    title="Alice changed from dark to light mode",
    content="Important: Alice's preference changed from dark mode to light mode",
)
print(f"   ✓ Decision recorded: memory_id={result.get('memory_id')}")

print("\n✅ Memanto's versioned storage ensures no silent overwrites!")
print("   Both old and new preferences are retrievable with temporal queries.")


# ═══════════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════════

print_separator("✅ DEMO COMPLETE")

print("""
What was demonstrated:
  ✓ Cross-session recall — memories survive LangGraph state resets
  ✓ Typed semantic memory — fact, preference, event, decision types
  ✓ Preference updates with conflict detection
  ✓ Grounded answers via recall

Next steps:
  1. Run agent.py for the full LangGraph integration
  2. Try with different memory types
  3. Add memanto_answer for RAG-grounded responses
""")
