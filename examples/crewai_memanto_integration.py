#!/usr/bin/env python3
"""
CrewAI + Memanto Integration Example
====================================

This example demonstrates how to integrate Memanto's agentic memory layer
with CrewAI agents for persistent, searchable, cross-agent memory.

USE CASE: "Memory Test" — Research Agent stores findings in Memanto, and
a Writer Agent retrieves them later (even in a separate run), proving
long-term memory persistence across agents and sessions.

PREREQUISITES
-------------
1. Install dependencies:
   pip install memanto crewai

2. Set up Memanto with your Moorcheh API key (get one at https://console.moorcheh.ai/api-keys):
   memanto

   Or set the environment variable:
   export MOORCHEH_API_KEY="your-api-key"

HOW TO RUN
----------
  # Step 1: Research agent stores findings
  python examples/crewai_memanto_integration.py --mode research

  # Step 2 (run hours or days later): Writer agent retrieves and uses those findings
  python examples/crewai_memanto_integration.py --mode write

  # Step 3: Run the full demo (research + write in one session)
  python examples/crewai_memanto_integration.py --mode demo

ARCHITECTURE
------------
  CrewAI Agent ──> CrewAIMemantoMemory ──> Memanto CLI ──> Moorcheh API
                 (remember/recall/answer)   (subprocess)   (semantic DB)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import textwrap
import time
from typing import Optional


# ---------------------------------------------------------------------------
# Memanto Memory Backend for CrewAI
# ---------------------------------------------------------------------------

class CrewAIMemantoMemory:
    """
    A drop-in memory backend that wraps Memanto's remember / recall / answer
    primitives for use with CrewAI agents.

    Each CrewAI agent gets its own Memanto agent namespace so memories are
    scoped per agent. A shared "crew" namespace stores cross-agent context.
    """

    def __init__(self, agent_id: str, crew_namespace: str = "crewai-crew"):
        """
        Args:
            agent_id: Unique Memanto agent ID for this CrewAI agent.
            crew_namespace: Shared namespace for crew-wide memories.
        """
        self.agent_id = agent_id
        self.crew_namespace = crew_namespace
        self._activated = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def activate(self) -> None:
        """Create the Memanto agent if needed and activate its session."""
        try:
            # Try activate first (agent may already exist)
            subprocess.run(
                ["memanto", "agent", "activate", self.agent_id],
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError:
            # Create + auto-activate if it doesn't exist
            subprocess.run(
                ["memanto", "agent", "create", self.agent_id],
                capture_output=True,
                text=True,
                check=True,
            )
        self._activated = True

    def deactivate(self) -> None:
        """End the current session."""
        subprocess.run(
            ["memanto", "agent", "deactivate", self.agent_id],
            capture_output=True,
            text=True,
        )

    # ------------------------------------------------------------------
    # Core Memanto operations
    # ------------------------------------------------------------------

    def remember(
        self,
        content: str,
        memory_type: str = "fact",
        confidence: float = 0.8,
        tags: Optional[list[str]] = None,
        source: Optional[str] = None,
    ) -> bool:
        """Store a memory in this agent's Memanto namespace.

        Args:
            content: The text to remember.
            memory_type: One of fact, decision, instruction, preference,
                         event, learning, observation, goal, commitment,
                         relationship, context, artifact, error.
            confidence: 0.0–1.0 confidence score.
            tags: Optional list of tags for filtering.
            source: Source identifier (defaults to agent_id).

        Returns:
            True on success, False on failure.
        """
        source = source or self.agent_id
        cmd = [
            "memanto", "remember", content,
            "--type", memory_type,
            "--confidence", str(confidence),
            "--source", source,
        ]
        if tags:
            cmd.extend(["--tags", ",".join(tags)])

        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=10)
            return True
        except subprocess.CalledProcessError as exc:
            print(f"[{self.agent_id}] remember failed: {exc.stderr.strip()}", file=sys.stderr)
            return False
        except subprocess.TimeoutExpired:
            print(f"[{self.agent_id}] remember timed out", file=sys.stderr)
            return False

    def recall(self, query: str, limit: int = 5) -> str:
        """Search this agent's memories by semantic similarity.

        Args:
            query: Natural-language search query.
            limit: Max results to return.

        Returns:
            Raw CLI output string, or empty string on failure.
        """
        try:
            result = subprocess.run(
                ["memanto", "recall", query, "--limit", str(limit)],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return ""
        except subprocess.TimeoutExpired:
            return ""

    def answer(self, question: str, limit: int = 5) -> str:
        """Ask a question grounded in this agent's memories (RAG).

        Args:
            question: Natural-language question.
            limit: Number of memories to use as context.

        Returns:
            LLM-generated answer, or empty string on failure.
        """
        try:
            result = subprocess.run(
                ["memanto", "answer", question, "--limit", str(limit)],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return ""
        except subprocess.TimeoutExpired:
            return ""

    # ------------------------------------------------------------------
    # Cross-agent memory operations
    # ------------------------------------------------------------------

    def share_to_crew(self, content: str, memory_type: str = "fact") -> bool:
        """Store a memory in the shared crew namespace for cross-agent access.

        This allows one agent's findings to be retrieved by another agent.
        """
        # Switch to crew namespace, store, switch back
        try:
            subprocess.run(
                ["memanto", "agent", "activate", self.crew_namespace],
                capture_output=True, text=True, check=True,
            )
        except subprocess.CalledProcessError:
            subprocess.run(
                ["memanto", "agent", "create", self.crew_namespace],
                capture_output=True, text=True, check=True,
            )

        cmd = [
            "memanto", "remember", content,
            "--type", memory_type,
            "--source", self.agent_id,
        ]
        ok = True
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=10)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            ok = False

        # Switch back
        subprocess.run(
            ["memanto", "agent", "activate", self.agent_id],
            capture_output=True, text=True,
        )
        return ok

    def recall_from_crew(self, query: str, limit: int = 5) -> str:
        """Search the shared crew namespace."""
        subprocess.run(
            ["memanto", "agent", "activate", self.crew_namespace],
            capture_output=True, text=True,
        )
        result = ""
        try:
            proc = subprocess.run(
                ["memanto", "recall", query, "--limit", str(limit)],
                capture_output=True, text=True, check=True, timeout=10,
            )
            result = proc.stdout.strip()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass

        subprocess.run(
            ["memanto", "agent", "activate", self.agent_id],
            capture_output=True, text=True,
        )
        return result

    # ------------------------------------------------------------------
    # CrewAI integration helpers
    # ------------------------------------------------------------------

    def build_context_for_agent(self, task_description: str) -> str:
        """Build a context block for the CrewAI agent's prompt.

        Retrieves relevant memories from both the agent's own namespace and
        the shared crew namespace, then formats them as context.
        """
        own = self.recall(task_description, limit=3)
        shared = self.recall_from_crew(task_description, limit=2)

        parts = []
        if own:
            parts.append(f"[Personal memory — {self.agent_id}]\n{own}")
        if shared:
            parts.append(f"[Crew memory — shared]\n{shared}")
        return "\n\n".join(parts) if parts else ""


# ---------------------------------------------------------------------------
# CrewAI Agent Definitions
# ---------------------------------------------------------------------------

class ResearchAgent:
    """
    A CrewAI-compatible Research Agent that uses Memanto for persistent memory.

    In a full CrewAI setup you would pass the memory instance via the agent's
    `memory` parameter or use it inside the task execution callback.  This
    example shows the integration pattern directly so you can adapt it to any
    CrewAI workflow.
    """

    def __init__(self, memory: CrewAIMemantoMemory):
        self.memory = memory
        self.memory.activate()

    def run(self, topic: str) -> dict:
        """Research a topic and store key findings in Memanto."""
        print(f"\n{'=' * 60}")
        print(f"ResearchAgent [{self.memory.agent_id}] — researching: {topic}")
        print(f"{'=' * 60}\n")

        # Simulate research (in production, this calls an LLM via CrewAI)
        findings = {
            "topic": topic,
            "key_insight": f"{topic} adoption grew 340% in Q1 2026 driven by enterprise AI budgets doubling year-over-year.",
            "competitors": ["OpenAI", "Anthropic", "Google DeepMind", "Meta AI"],
            "market_size": "$45.2B by 2027 (CAGR 37.8%)",
            "recommendation": "Focus on multi-agent orchestration — the fastest-growing sub-segment at 62% CAGR.",
        }

        # Store each finding as a typed memory
        self.memory.remember(
            f"Research topic: {topic}. {findings['key_insight']}",
            memory_type="fact",
            tags=["research", topic.replace(" ", "-").lower()],
        )
        self.memory.remember(
            f"Competitive landscape for {topic}: {', '.join(findings['competitors'])}",
            memory_type="observation",
            tags=["research", "competitors"],
        )
        self.memory.remember(
            f"Market size for {topic}: {findings['market_size']}",
            memory_type="fact",
            confidence=0.9,
            tags=["research", "market"],
        )
        self.memory.remember(
            f"Strategic recommendation: {findings['recommendation']}",
            memory_type="decision",
            confidence=0.85,
            tags=["research", "strategy"],
        )

        # Share key findings to the crew namespace so Writer agent can access them
        self.memory.share_to_crew(
            f"Research completed on '{topic}': {findings['key_insight']} "
            f"Recommendation: {findings['recommendation']}",
            memory_type="fact",
        )
        self.memory.share_to_crew(
            f"Market data for {topic}: {findings['market_size']}",
            memory_type="fact",
        )

        print("Findings stored in Memanto:\n")
        for key, val in findings.items():
            print(f"  {key}: {val}")

        print("\nAlso shared to crew namespace for cross-agent recall.\n")
        return findings


class WriterAgent:
    """
    A CrewAI-compatible Writer Agent that retrieves research from Memanto
    and produces a document.

    This agent can be run hours or days AFTER the Research Agent — Memanto
    provides persistent memory across sessions.
    """

    def __init__(self, memory: CrewAIMemantoMemory):
        self.memory = memory
        self.memory.activate()

    def run(self, topic: str) -> str:
        """Retrieve research findings from Memanto and write a report."""
        print(f"\n{'=' * 60}")
        print(f"WriterAgent [{self.memory.agent_id}] — retrieving context for: {topic}")
        print(f"{'=' * 60}\n")

        # Recall from own namespace
        print("[1] Recalling from personal memory...")
        own_context = self.memory.recall(topic, limit=5)
        print(f"    Found personal memories: {'yes' if own_context else 'no'}")

        # Recall from shared crew namespace (cross-agent)
        print("[2] Recalling from crew namespace (cross-agent)...")
        crew_context = self.memory.recall_from_crew(topic, limit=5)
        print(f"    Found crew memories: {'yes' if crew_context else 'no'}")

        # Use RAG to get a grounded answer
        print("[3] Asking Memanto RAG for a synthesized answer...")
        rag_answer = self.memory.answer(
            f"Based on all research findings about {topic}, write a concise executive summary "
            f"covering the key insight, market size, competitors, and strategic recommendation."
        )
        print(f"    RAG answer received: {'yes' if rag_answer else 'no'}")

        # Store that the writer used this research
        self.memory.remember(
            f"Generated executive summary on '{topic}' using Memanto-retrieved research. "
            f"Timing: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            memory_type="event",
            tags=["writing", "summary"],
        )

        # Build the report
        report = textwrap.dedent(f"""\
        EXECUTIVE SUMMARY: {topic}
        {'=' * 60}

        {rag_answer if rag_answer else 'No prior research found. Try running with --mode research first.'}

        ---
        Memory provenance: Retrieved from Memanto agentic memory layer.
        Agent: {self.memory.agent_id}
        Crew namespace: {self.memory.crew_namespace}
        Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}
        """)

        print("\n" + report)
        return report


# ---------------------------------------------------------------------------
# How-To: Swap Standard CrewAI Memory for Memanto
# ---------------------------------------------------------------------------

HOW_TO_SWAP = r"""
╔══════════════════════════════════════════════════════════════════════════╗
║          HOW TO SWAP STANDARD CREWAI MEMORY FOR MEMANTO                 ║
╚══════════════════════════════════════════════════════════════════════════╝

1. INSTALL
   pip install memanto crewai

2. CONFIGURE
   export MOORCHEH_API_KEY="your-moorcheh-api-key"
   # (Get a key at https://console.moorcheh.ai/api-keys)

3. IN YOUR CrewAI CODE — two approaches:

   APPROACH A — Use CrewAIMemantoMemory as a wrapper (RECOMMENDED)
   ───────────────────────────────────────────────────────────
   from crewai_memanto_integration import CrewAIMemantoMemory

   # Create memory backend per agent
   memory = CrewAIMemantoMemory(agent_id="my-research-agent")
   memory.activate()

   # Inside your CrewAI agent's task execution:
   def execute_task(self, task):
       # Recall relevant past context before acting
       context = memory.recall(task.description)

       # ... run your LLM logic with context ...

       # Store key outputs for future recall
       memory.remember(
           f"Task '{task.name}' completed. Output: {result}",
           memory_type="fact",
           tags=["task", task.name],
       )


   APPROACH B — Drop-in replacement for CrewAI's built-in memory
   ─────────────────────────────────────────────────────────────
   # If CrewAI exposes a memory interface, wrap Memanto:
   class MemantoCrewAIMemory:
       def __init__(self, agent_id):
           self._m = CrewAIMemantoMemory(agent_id)
           self._m.activate()

       def store(self, key, value):
           self._m.remember(f"{key}: {value}", memory_type="fact")

       def retrieve(self, query):
           return self._m.recall(query)

       def query(self, question):
           return self._m.answer(question)


4. WHY MEMANTO OVER BUILT-IN MEMORY?
   ┌────────────────────┬──────────────────┬──────────────────┐
   │ Feature            │ CrewAI Default   │ Memanto          │
   ├────────────────────┼──────────────────┼──────────────────┤
   │ Persistence        │ Session-only     │ Permanent        │
   │ Cross-agent access │ No               │ Yes (shared NS)  │
   │ Semantic search    │ No (key-value)   │ Yes (exact)      │
   │ Confidence scoring │ No               │ Yes              │
   │ Temporal queries   │ No               │ Yes (as-of/Δ)    │
   │ Ingestion latency  │ N/A              │ Zero             │
   │ Provenance         │ No               │ Yes              │
   └────────────────────┴──────────────────┴──────────────────┘

   See https://docs.memanto.ai for full documentation.
"""


# ---------------------------------------------------------------------------
# Main Demo
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="CrewAI + Memanto Integration — Memory Test Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
        examples:
          %(prog)s --mode research    # Research agent stores findings
          %(prog)s --mode write       # Writer agent retrieves findings (run later!)
          %(prog)s --mode demo        # Full end-to-end demo
          %(prog)s --how-to-swap      # Show how to swap CrewAI memory for Memanto
        """),
    )
    parser.add_argument(
        "--mode",
        choices=["research", "write", "demo"],
        default="demo",
        help="Which phase to run (default: demo). Run 'research' first, then 'write' later.",
    )
    parser.add_argument(
        "--topic",
        default="AI Agent Memory Systems",
        help="Research topic (default: 'AI Agent Memory Systems')",
    )
    parser.add_argument(
        "--how-to-swap",
        action="store_true",
        help="Print the how-to guide for swapping CrewAI memory with Memanto",
    )
    args = parser.parse_args()

    if args.how_to_swap:
        print(HOW_TO_SWAP)
        return

    # Verify Memanto is configured
    api_key = os.environ.get("MOORCHEH_API_KEY")
    memanto_config = os.path.expanduser("~/.memanto/config.json")
    if not api_key:
        try:
            with open(memanto_config) as f:
                cfg = json.load(f)
            if not cfg.get("api_key"):
                raise FileNotFoundError
        except (FileNotFoundError, json.JSONDecodeError):
            print(
                "Memanto is not configured.\n\n"
                "Run 'memanto' to set up your Moorcheh API key, or set MOORCHEH_API_KEY.\n"
                "Get a free key at https://console.moorcheh.ai/api-keys\n",
                file=sys.stderr,
            )
            sys.exit(1)

    # ------------------------------------------------------------------
    # Agent setup
    # ------------------------------------------------------------------
    research_memory = CrewAIMemantoMemory(
        agent_id="research-agent", crew_namespace="crewai-crew"
    )
    writer_memory = CrewAIMemantoMemory(
        agent_id="writer-agent", crew_namespace="crewai-crew"
    )

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------
    if args.mode == "research":
        research_agent = ResearchAgent(research_memory)
        research_agent.run(args.topic)
        print("\nResearch phase complete. Run --mode write (anytime later) to retrieve.")

    elif args.mode == "write":
        writer_agent = WriterAgent(writer_memory)
        report = writer_agent.run(args.topic)

    elif args.mode == "demo":
        print(HOW_TO_SWAP)
        print("\n" + "=" * 60)
        print("  DEMO: Research Agent stores findings, Writer Agent retrieves them")
        print("=" * 60)

        # Phase 1: Research
        research_agent = ResearchAgent(research_memory)
        findings = research_agent.run(args.topic)

        time.sleep(1)

        # Phase 2: Write (retrieves from Memanto across agents)
        writer_agent = WriterAgent(writer_memory)
        report = writer_agent.run(args.topic)

        print("\n" + "=" * 60)
        print("  DEMO COMPLETE — Memanto preserved memory across agents!")
        print("=" * 60)
        print(
            "Try running again with --mode write to see persistence across sessions.\n"
        )


if __name__ == "__main__":
    main()
