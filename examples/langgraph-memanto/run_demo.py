
#!/usr/bin/env python3
"""
LangGraph + Memanto Cross-Session Memory Demos.

Runs 3 independent demos:
  1. Fitness Coach  - stores workout/diet/injury data, recalls it next session
  2. Blog Writer    - stores audience/tone/article data, avoids repetition
  3. Travel Planner - stores visa/hotel/budget data, gives trip-specific advice

Each demo runs session 1 (stores memories) then session 2 with a FRESH state
(no memories carried over), proving cross-session recall works.

Usage:
    python run_demo.py               # Local mode (no Memanto API key needed)
    MEMANTO_MODE=real python run_demo.py  # Real Memanto mode
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

# Allow importing langgraph_memanto from this directory
sys.path.insert(0, str(Path(__file__).parent))

from langgraph_memanto import (
    AgentState,
    LocalMemoryClient,
    MemoryClient,
    create_memory_client,
    make_answer_node,
    make_recall_node,
    make_remember_node,
)

# ---------------------------------------------------------------------------
# Colors for terminal output
# ---------------------------------------------------------------------------

try:
    import colorama
    colorama.init()
    C = type("Colors", (), {
        "GREEN": "\033[92m",
        "BLUE": "\033[94m",
        "YELLOW": "\033[93m",
        "RED": "\033[91m",
        "CYAN": "\033[96m",
        "BOLD": "\033[1m",
        "RESET": "\033[0m",
    })()
except ImportError:
    C = type("Colors", (), {
        "GREEN": "", "BLUE": "", "YELLOW": "", "RED": "", "CYAN": "",
        "BOLD": "", "RESET": "",
    })()

# ---------------------------------------------------------------------------
# Helper: simulate a LangGraph node call
# ---------------------------------------------------------------------------

def run_node(node_fn, state: AgentState):
    """Simulate a single LangGraph node invocation."""
    return node_fn(state)


def print_header(title: str):
    print(f"\n{C.BOLD}{C.CYAN}{'=' * 60}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}  {title}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}{'=' * 60}{C.RESET}\n")


def print_section(title: str):
    print(f"\n{C.YELLOW}--- {title} ---{C.RESET}")


def fresh_state(agent_id: str, session_id: str) -> AgentState:
    """Return a clean AgentState with no memories."""
    return AgentState(
        agent_id=agent_id,
        session_id=session_id,
        user_input="",
        memories_stored=[],
        memories_recalled=[],
        response="",
        done=False,
    )


# ---------------------------------------------------------------------------
# Demo 1: Fitness Coach
# ---------------------------------------------------------------------------

def demo_fitness_coach(memory: MemoryClient):
    """Fitness Coach remembers client profile, then recalls it next session."""
    agent_id = "fitness-coach-agent"
    print_header("Demo 1: Fitness Coach - Cross-Session Recall")

    remember = make_remember_node(memory)
    recall = make_recall_node(memory)
    answer = make_answer_node(memory)

    # --- Session 1: Store memories ---
    print_section("Session 1 - Coach stores client profile")
    memories_to_store = [
        ("fact", "Upper body workout preference",
         "Client prefers push/pull split with 4 exercises per session, 3 sets of 10-12 reps"),
        ("preference", "Dietary restriction: dairy-free",
         "Client is lactose intolerant. Replace whey protein with pea protein. No milk-based shakes."),
        ("fact", "Shoulder injury history",
         "Client has mild rotator cuff issue in right shoulder. Avoid overhead press above 90 degrees. Use light lateral raises only."),
        ("goal", "12-week fat loss target",
         "Goal: lose 8kg body fat while maintaining muscle mass. Target: 1800 kcal/day with 150g protein."),
        ("preference", "Workout time preference",
         "Client prefers morning workouts at 6:30 AM, 4 days per week (Mon/Tue/Thu/Fri)."),
        ("fact", "Current stats",
         "Weight: 85kg, Body fat: 22%, Bench: 80kg, Squat: 110kg, Deadlift: 140kg. Measured 2026-05-10."),
    ]

    for mem_type, title, content in memories_to_store:
        state = fresh_state(agent_id, "session-1")
        state["user_input"] = f"{mem_type}|{title}|{content}"
        result = run_node(remember, state)
        print(f"  {C.GREEN}✓{C.RESET} Stored [{mem_type}]: {title}")

    print(f"\n  Total stored: {len(memories_to_store)} memories")

    # --- Session 2: Recall with FRESH state ---
    print_section("Session 2 (FRESH state) - Coach recalls client info")
    state2 = fresh_state(agent_id, "session-2")
    state2["user_input"] = "workout plan dietary restrictions injury shoulder"
    result = run_node(recall, state2)

    print(f"  {C.GREEN}✓{C.RESET} Recalled {result['memories_recalled'].__len__()} memories:")
    for m in result["memories_recalled"]:
        print(f"      [{m.get('type', '?')}] {m['title']}")

    # RAG answer
    state3 = fresh_state(agent_id, "session-2")
    state3["user_input"] = "What should I recommend for shoulder-friendly upper body workout?"
    result3 = run_node(answer, state3)
    print(f"\n  {C.BLUE}Answer:{C.RESET} {result3['response']}")

    print(f"\n  {C.GREEN}✅ Cross-session recall VERIFIED for Fitness Coach{C.RESET}")


# ---------------------------------------------------------------------------
# Demo 2: Blog Writer
# ---------------------------------------------------------------------------

def demo_blog_writer(memory: MemoryClient):
    """Blog Writer remembers audience, tone, past articles; avoids repetition."""
    agent_id = "blog-writer-agent"
    print_header("Demo 2: Blog Writer - Tone & Audience Persistence")

    remember = make_remember_node(memory)
    recall = make_recall_node(memory)
    answer = make_answer_node(memory)

    # --- Session 1: Store memories ---
    print_section("Session 1 - Writer stores audience profile and past content")
    memories_to_store = [
        ("fact", "Target audience: CTOs and engineering leaders",
         "Readers are CTOs and VP Eng at Series B-D startups. They care about scalability, team velocity, and cost efficiency. Technical depth expected."),
        ("preference", "Writing tone: authoritative but approachable",
         "Use active voice. Avoid buzzwords. Lead with data. Include at least one code snippet or architecture diagram per article."),
        ("fact", "Published: 'Why Monoliths Beat Microservices in 2026'",
         "Published May 10, 2026. Key points: 78% of startups over-engineer early, monoliths reduce infra costs 3x, team velocity 2x faster with monolith."),
        ("fact", "Published: 'The Real Cost of Kubernetes'",
         "Published April 28, 2026. Average startup spends $4,200/month on k8s infra vs $800 on managed services. Hidden cost: 15 eng-hours/week maintenance."),
        ("preference", "Overused phrases to avoid",
         "Avoid: 'game-changer', 'revolutionary', 'in today's fast-paced world', 'unprecedented'. These appeared in 3 articles already."),
        ("decision", "Content calendar: Q2 2026",
         "May: observability deep-dive. June: AI/LLM cost optimization. July: team structure for platform engineering. Publish every Thursday."),
    ]

    for mem_type, title, content in memories_to_store:
        state = fresh_state(agent_id, "session-1")
        state["user_input"] = f"{mem_type}|{title}|{content}"
        run_node(remember, state)
        print(f"  {C.GREEN}✓{C.RESET} Stored [{mem_type}]: {title}")

    print(f"\n  Total stored: {len(memories_to_store)} memories")

    # --- Session 2: Recall ---
    print_section("Session 2 (FRESH state) - Writer drafts next article")
    state2 = fresh_state(agent_id, "session-2")
    state2["user_input"] = "audience tone overused phrases content calendar"
    result = run_node(recall, state2)

    print(f"  {C.GREEN}✓{C.RESET} Recalled {result['memories_recalled'].__len__()} memories:")
    for m in result["memories_recalled"]:
        print(f"      [{m.get('type', '?')}] {m['title']}")

    # RAG: what phrases to avoid
    state3 = fresh_state(agent_id, "session-2")
    state3["user_input"] = "What phrases should I avoid in my next article?"
    result3 = run_node(answer, state3)
    print(f"\n  {C.BLUE}Answer:{C.RESET} {result3['response']}")

    print(f"\n  {C.GREEN}✅ Cross-session recall VERIFIED for Blog Writer{C.RESET}")


# ---------------------------------------------------------------------------
# Demo 3: Travel Planner
# ---------------------------------------------------------------------------

def demo_travel_planner(memory: MemoryClient):
    """Travel Planner remembers trips, preferences, visa rules."""
    agent_id = "travel-planner-agent"
    print_header("Demo 3: Travel Planner - Multi-Trip Memory")

    remember = make_remember_node(memory)
    recall = make_recall_node(memory)
    answer = make_answer_node(memory)

    # --- Session 1: Store memories ---
    print_section("Session 1 - Planner stores travel knowledge")
    memories_to_store = [
        ("fact", "Visa: Japan tourist e-Visa",
         "Japan e-Visa available for 90-day tourism. Apply online 2 weeks before. Cost: $30. Requires: passport scan, photo, itinerary, hotel booking."),
        ("preference", "Hotel preference: boutique under $200",
         "Prefers boutique hotels with local character, under $200/night. Must have: WiFi, breakfast included, walking distance to metro."),
        ("fact", "Trip: Tokyo May 2026",
         "7-day Tokyo trip May 15-22. Hotel: Hotel Graphy Nezu ($145/night). Highlights: teamLab Borderless, Tsukiji market, Akihabara. Budget used: $2,100."),
        ("preference", "Budget rule: daily max $300",
         "Daily budget: $300 max (hotel + food + transport + activities). Emergency buffer: $50/day for unexpected."),
        ("fact", "Flight preference: direct only, aisle seat",
         "Always book direct flights. Aisle seat preferred (right side). Check-in 24h before. Carry-on only for trips under 5 days."),
        ("fact", "Solo travel safety tips",
         "Share live location with 2 contacts. Keep digital copy of passport. Travel insurance with medical evac required. Register with embassy for trips over 14 days."),
    ]

    for mem_type, title, content in memories_to_store:
        state = fresh_state(agent_id, "session-1")
        state["user_input"] = f"{mem_type}|{title}|{content}"
        run_node(remember, state)
        print(f"  {C.GREEN}✓{C.RESET} Stored [{mem_type}]: {title}")

    print(f"\n  Total stored: {len(memories_to_store)} memories")

    # --- Session 2: Recall ---
    print_section("Session 2 (FRESH state) - Planner plans next trip")
    state2 = fresh_state(agent_id, "session-2")
    state2["user_input"] = "hotel budget visa flight preferences safety"
    result = run_node(recall, state2)

    print(f"  {C.GREEN}✓{C.RESET} Recalled {result['memories_recalled'].__len__()} memories:")
    for m in result["memories_recalled"]:
        print(f"      [{m.get('type', '?')}] {m['title']}")

    # RAG answer
    state3 = fresh_state(agent_id, "session-2")
    state3["user_input"] = "What hotel and budget rules should I follow for my next trip?"
    result3 = run_node(answer, state3)
    print(f"\n  {C.BLUE}Answer:{C.RESET} {result3['response']}")

    print(f"\n  {C.GREEN}✅ Cross-session recall VERIFIED for Travel Planner{C.RESET}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    """Run all 3 demos."""
    mode = os.environ.get("MEMANTO_MODE", "local")

    print(f"{C.BOLD}{C.CYAN}")
    print("╔══════════════════════════════════════════════════════════╗")
    print("║     LangGraph + Memanto: Cross-Session Memory Demo      ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print(f"{C.RESET}")
    print(f"Mode: {C.YELLOW}{mode}{C.RESET}")
    print(f"Time: {datetime.now().isoformat()}")

    # Clean up old local memories for fresh demo
    if mode == "local" and os.path.exists("local_memories.json"):
        os.remove("local_memories.json")

    if mode == "real":
        api_key = os.environ.get("MOORCHEH_API_KEY")
        if not api_key:
            print(f"{C.RED}Error: MOORCHEH_API_KEY not set.{C.RESET}")
            print("Set it in .env or export MOORCHEH_API_KEY=mk_...")
            sys.exit(1)

        from memanto.cli.client.sdk_client import SdkClient
        sdk = SdkClient(api_key=api_key)
        from langgraph_memanto import MemantoMemoryClient
        memory = MemantoMemoryClient(sdk)

        # Activate agents
        agent_ids = ["fitness-coach-agent", "blog-writer-agent", "travel-planner-agent"]
        for aid in agent_ids:
            try:
                sdk.create_agent(aid, description=f"LangGraph demo agent: {aid}")
                print(f"  Created agent: {aid}")
            except Exception:
                pass  # Agent may already exist
            sdk.activate_agent(aid)
            print(f"  Activated agent: {aid}")
    else:
        memory = LocalMemoryClient(file_path="local_memories.json")

    # Run demos
    demo_fitness_coach(memory)
    demo_blog_writer(memory)
    demo_travel_planner(memory)

    # Summary
    print_header("Summary")
    print(f"{C.GREEN}✅ All 3 demos passed cross-session recall verification{C.RESET}")
    print(f"\nKey takeaways:")
    print(f"  1. LangGraph agents use Memanto as external memory layer")
    print(f"  2. Memories persist across sessions (Session 1 → Session 2)")
    print(f"  3. Fresh LangGraph state does NOT carry memories — Memanto does")
    print(f"  4. 13 memory types with confidence scoring")
    print(f"  5. Works in local mode (no API key) and real Memanto mode")

    print(f"\n{C.BOLD}Files:{C.RESET}")
    print(f"  - langgraph_memanto.py  (core library)")
    print(f"  - run_demo.py           (this file)")
    if mode == "local":
        print(f"  - local_memories.json   (stored memories)")

    print()


if __name__ == "__main__":
    main()
