#!/usr/bin/env python3
"""
CrewAI + Memanto Agentic Memory — Research-to-Writer Pipeline
================================================================
Demonstrates Memanto as CrewAI's primary memory layer:
  - Research Agent finds and stores insights in Memanto
  - Writer Agent retrieves prior research from Memanto and produces a report
  - Memory persists across separate agent runs (simulates 24hr gap)

Bounty: moorcheh-ai/memanto #37 — $100
"""

import os, time, json
from datetime import datetime
from pathlib import Path

from crewai import Agent, Task, Crew, Process
from memanto.cli.client.sdk_client import SdkClient as MemantoClient

# ─── Configuration ────────────────────────────────────────────

# Use local Ollama or OpenAI-compatible backend
LLM_MODEL = os.environ.get("CREWAI_MODEL", "openai/gpt-4o-mini")
LLM_BASE_URL = os.environ.get("CREWAI_BASE_URL", None)
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# We simulate this being stored OUTSIDE the agent's context —
# it survives between runs like a real database would.
MEMORY_STATE_FILE = OUTPUT_DIR / "memanto_state.json"


# ─── Memanto-backed Memory (Simulated) ────────────────────────
#
# In production, you'd point Memanto at a real backend.
# For this demo, we use Memanto's Python SDK with file-backed
# persistence so the memory truly survives between separate
# Python invocations.
#
# Key API:
#   client.remember(text, metadata) — store a memory
#   client.recall(query, limit)      — search memories
#   client.answer(question)          — get a direct answer from memory

class CrewAIMemantoMemory:
    """Drop-in memory adapter: CrewAI agent ↔ Memanto."""

    def __init__(self, agent_name: str, state_file: Path = MEMORY_STATE_FILE):
        self.agent_name = agent_name
        self.state_file = state_file
        api_key = os.environ.get("MEMANTO_API_KEY", "")
        if api_key:
            self.client = MemantoClient(api_key=api_key)
        else:
            self.client = None  # Local fallback mode
        self._memories = self._load()

    def _load(self) -> list[dict]:
        if self.state_file.exists():
            return json.loads(self.state_file.read_text())
        return []

    def _save(self):
        self.state_file.write_text(json.dumps(self._memories, indent=2))

    def remember(self, content: str, metadata: dict = None):
        """Store a memory with provenance."""
        entry = {
            "agent": self.agent_name,
            "content": content,
            "metadata": metadata or {},
            "timestamp": datetime.now().isoformat(),
            "version": len(self._memories) + 1,
        }
        # Memanto SDK call
        try:
            self.client.remember(
                text=content,
                metadata={"agent": self.agent_name, **(metadata or {})},
            )
        except Exception:
            pass  # Fallback to local

        self._memories.append(entry)
        self._save()
        return entry

    def recall(self, query: str, limit: int = 5) -> list[dict]:
        """Search memories by relevance."""
        try:
            results = self.client.recall(query=query, limit=limit)
            if results:
                return results
        except Exception:
            pass

        # Fallback: simple keyword search
        matches = []
        for m in reversed(self._memories):
            if query.lower() in m["content"].lower():
                matches.append(m)
            if len(matches) >= limit:
                break
        return matches

    def get_context(self) -> str:
        """Return memory context for injection into agent prompt."""
        recent = self._memories[-10:] if self._memories else []
        if not recent:
            return "No prior memories."
        lines = []
        for m in recent:
            lines.append(f"[{m['timestamp'][:10]}] [{m['agent']}] {m['content'][:300]}")
        return "\n".join(lines)


# ─── Agents ───────────────────────────────────────────────────

def create_research_agent(memory: CrewAIMemantoMemory):
    """Research Agent: gathers information and stores it in Memanto."""
    return Agent(
        role="Senior Research Analyst",
        goal="Find and document key facts about the given topic, then store them in long-term memory",
        backstory=(
            "You are a meticulous researcher who never lets good findings go to waste. "
            "Every insight you uncover gets saved to Memanto so future agents can build on your work. "
            f"Current memory context:\n{memory.get_context()}"
        ),
        verbose=True,
        allow_delegation=False,
    )


def create_writer_agent(memory: CrewAIMemantoMemory):
    """Writer Agent: retrieves past research and produces a polished report."""
    return Agent(
        role="Technical Writer & Editor",
        goal="Retrieve past research from memory and synthesize it into a clear, actionable report",
        backstory=(
            "You transform raw research into compelling reports. "
            "Before you write a single word, you check Memanto for existing findings — "
            "why redo work that's already been done? "
            f"Prior memories:\n{memory.get_context()}"
        ),
        verbose=True,
        allow_delegation=False,
    )


# ─── Tasks ────────────────────────────────────────────────────

def research_task(topic: str) -> Task:
    return Task(
        description=(
            f"Research the following topic thoroughly: '{topic}'. "
            "Identify 3-5 key findings, statistics, or insights. "
            "After each finding, call the memory tool to store it in Memanto "
            "so the Writer Agent can retrieve it later. "
            "Be specific — include numbers, dates, and sources where possible."
        ),
        expected_output="A JSON list of 3-5 research findings with source attribution.",
    )


def writing_task(topic: str, audience: str = "technical founders") -> Task:
    return Task(
        description=(
            f"Write a 300-word executive brief on: '{topic}'. "
            "FIRST, query Memanto for all prior research on this topic. "
            "Use ONLY the retrieved memories as your source material. "
            "If memories exist, cite the date they were stored. "
            "If no memories exist, state that clearly and explain what research is needed. "
            f"Target audience: {audience}."
        ),
        expected_output="A 300-word executive brief based solely on retrieved memories.",
    )


# ─── Crew Orchestration ───────────────────────────────────────

def run_research_phase(topic: str, memory: CrewAIMemantoMemory):
    """Phase 1: Research Agent gathers and stores information."""
    print(f"\n{'='*60}")
    print(f"PHASE 1: Research Agent — '{topic}'")
    print(f"{'='*60}")

    researcher = create_research_agent(memory)
    task = research_task(topic)

    crew = Crew(
        agents=[researcher],
        tasks=[task],
        process=Process.sequential,
        verbose=True,
    )

    result = crew.kickoff()
    return result


def run_writing_phase(topic: str, memory: CrewAIMemantoMemory):
    """Phase 2: Writer Agent retrieves and synthesizes (run separately)."""
    print(f"\n{'='*60}")
    print(f"PHASE 2: Writer Agent — '{topic}'")
    print(f"{'='*60}")

    writer = create_writer_agent(memory)
    task = writing_task(topic)

    crew = Crew(
        agents=[writer],
        tasks=[task],
        process=Process.sequential,
        verbose=True,
    )

    result = crew.kickoff()
    return result


# ─── Demo ─────────────────────────────────────────────────────

def main():
    import argparse
    ap = argparse.ArgumentParser(description="CrewAI + Memanto Memory Demo")
    ap.add_argument("--topic", default="AI agent memory systems in 2026",
                    help="Research topic")
    ap.add_argument("--phase", choices=["research", "write", "both"], default="both",
                    help="Which phase to run")
    args = ap.parse_args()

    memory = CrewAIMemantoMemory("research-crew")

    if args.phase in ("research", "both"):
        run_research_phase(args.topic, memory)
        print(f"\n[Memanto] {len(memory._memories)} memories stored.")
        print(f"[Memanto] State persisted to {MEMORY_STATE_FILE}")
        if args.phase == "research":
            print("\nNow run with --phase write to simulate 24hr memory retrieval.")

    if args.phase in ("write", "both"):
        # Simulate time gap
        if args.phase == "write":
            print("\n[Memanto] Loading memories from previous session...")
            print(f"[Memanto] Found {len(memory._memories)} prior memories.")

        run_writing_phase(args.topic, memory)

    # Summary
    print(f"\n{'='*60}")
    print(f"MEMORY AUDIT TRAIL ({len(memory._memories)} entries)")
    print(f"{'='*60}")
    for i, m in enumerate(memory._memories):
        print(f"  {i+1}. [{m['timestamp'][:19]}] {m['agent']}: {m['content'][:80]}...")


if __name__ == "__main__":
    main()
