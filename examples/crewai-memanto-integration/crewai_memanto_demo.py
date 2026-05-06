#!/usr/bin/env python3
"""
CrewAI + MEMANTO Integration Demo

This demo shows a multi-agent Crew where:
1. Research Agent stores findings in MEMANTO (Session 1)
2. Writer Agent retrieves and uses those findings (Session 2)

Run it twice to demonstrate cross-session memory persistence.

Usage:
    # First run - stores memories
    python crewai_memanto_demo.py --mode research

    # Second run - retrieves and writes
    python crewai_memanto_demo.py --mode write

    # Both in one go
    python crewai_memanto_demo.py --mode both
"""

import os
import sys
import time
import argparse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import MEMANTO memory
from memanto_memory import MemantoAgentMemory


# ─── Configuration ───────────────────────────────────────────────────────────

AGENT_ID = "crewai-memanto-demo"

RESEARCH_TOPICS = [
    "The impact of AI on software development productivity",
    "Best practices for multi-agent AI systems",
    "Emerging trends in agentic memory architectures",
]

WRITING_PROMPT = (
    "Write a brief article about AI agents and memory, "
    "incorporating key insights from recent research."
)


# ─── Research Agent ──────────────────────────────────────────────────────────

class ResearchAgent:
    """Agent that researches topics and stores findings in MEMANTO."""

    def __init__(self, memory: MemantoAgentMemory):
        self.memory = memory
        self.name = "Researcher"

    def research_and_store(self, topic: str) -> dict:
        """
        Research a topic and store key findings in MEMANTO.

        In a real scenario, this would use an LLM to research.
        Here we demonstrate the memory storage pattern.
        """
        print(f"\n🔬 [{self.name}] Researching: {topic}")

        # Simulate research findings
        findings = self._simulate_research(topic)

        # Store each finding in MEMANTO
        for i, finding in enumerate(findings):
            success = self.memory.remember(
                content=finding["content"],
                memory_type=finding.get("type", "fact"),
                tags=finding.get("tags", "research"),
                confidence=finding.get("confidence", 0.9),
                provenance="research_agent_analysis",
            )
            status = "✅" if success else "❌"
            print(f"  {status} Stored: {finding['content'][:60]}...")

        return {"topic": topic, "findings_count": len(findings)}

    def _simulate_research(self, topic: str) -> list:
        """Simulate research findings for demonstration."""
        findings_map = {
            "The impact of AI on software development productivity": [
                {
                    "content": "AI coding assistants improve developer productivity by 25-55% according to GitHub Copilot research (2024-2025)",
                    "type": "fact",
                    "tags": "productivity,research",
                    "confidence": 0.85,
                },
                {
                    "content": "Developers using AI tools report 56% faster task completion for routine coding tasks",
                    "type": "fact",
                    "tags": "productivity,statistics",
                    "confidence": 0.80,
                },
                {
                    "content": "Multi-agent systems show promise for complex software tasks requiring coordination",
                    "type": "insight",
                    "tags": "multi-agent,future-trends",
                    "confidence": 0.75,
                },
                {
                    "content": "AI-assisted code review catches 30% more bugs compared to manual review alone",
                    "type": "fact",
                    "tags": "code-quality,research",
                    "confidence": 0.80,
                },
            ],
            "Best practices for multi-agent AI systems": [
                {
                    "content": "Shared memory between agents prevents information silos and enables coherent multi-step workflows",
                    "type": "best_practice",
                    "tags": "memory,architecture",
                    "confidence": 0.90,
                },
                {
                    "content": "Agents should have clear role definitions to avoid task overlap and conflict",
                    "type": "best_practice",
                    "tags": "design,roles",
                    "confidence": 0.95,
                },
                {
                    "content": "Persistent memory across sessions is critical for long-running agent workflows",
                    "type": "insight",
                    "tags": "memory,persistence",
                    "confidence": 0.85,
                },
            ],
            "Emerging trends in agentic memory architectures": [
                {
                    "content": "Typed semantic memory (fact vs preference vs goal) enables more precise retrieval than flat memory stores",
                    "type": "insight",
                    "tags": "memory,architecture",
                    "confidence": 0.85,
                },
                {
                    "content": "Zero-ingestion-latency memory allows agents to store and retrieve in real-time without blocking",
                    "type": "fact",
                    "tags": "performance,memory",
                    "confidence": 0.80,
                },
                {
                    "content": "Memory with confidence scoring and provenance helps agents handle contradictory information",
                    "type": "insight",
                    "tags": "memory,reliability",
                    "confidence": 0.90,
                },
            ],
        }

        return findings_map.get(topic, [
            {"content": f"Research finding about: {topic}", "type": "fact",
             "tags": "general", "confidence": 0.70}
        ])


# ─── Writer Agent ───────────────────────────────────────────────────────────

class WriterAgent:
    """Agent that retrieves memories from MEMANTO and produces content."""

    def __init__(self, memory: MemantoAgentMemory):
        self.memory = memory
        self.name = "Writer"

    def retrieve_and_write(self, topic_query: str) -> dict:
        """
        Retrieve stored memories and use them to write content.

        Args:
            topic_query: Query to find relevant memories

        Returns:
            Dict with retrieved memories and generated content
        """
        print(f"\n✍️  [{self.name}] Retrieving memories about: {topic_query}")

        # Recall relevant memories from MEMANTO
        memories = self.memory.recall(topic_query, limit=10)

        if not memories:
            print("  ⚠️  No memories found. Run research mode first!")
            return {"memories_found": 0, "article": None}

        print(f"  📖 Found {len(memories)} relevant memories:")

        # Display retrieved memories
        for i, mem in enumerate(memories):
            content = mem.get("content", mem.get("text", str(mem)))
            mem_type = mem.get("type", "unknown")
            confidence = mem.get("confidence", "N/A")
            print(f"  {i+1}. [{mem_type}] (confidence: {confidence})")
            print(f"     {content[:80]}...")

        # Generate article from memories
        article = self._generate_article(memories)

        return {
            "memories_found": len(memories),
            "article": article,
        }

    def _generate_article(self, memories: list) -> str:
        """Generate an article from retrieved memories."""
        lines = []

        # Extract key facts
        facts = []
        for mem in memories:
            content = mem.get("content", mem.get("text", ""))
            if content:
                facts.append(content)

        if not facts:
            return "No content could be generated."

        article_title = "AI Agents and Memory: Key Insights for 2026"

        body_parts = [
            f"# {article_title}\n",
            "## Overview\n",
            "Recent research in AI agent memory systems has revealed several important insights "
            "for developers building multi-agent applications.\n",
            "## Key Findings\n",
        ]

        for i, fact in enumerate(facts, 1):
            body_parts.append(f"{i}. {fact}\n")

        body_parts.extend([
            "\n## Implications\n",
            "These findings suggest that investing in a robust memory layer—one that supports "
            "typed memories, cross-session persistence, and semantic retrieval—is critical "
            "for building production-ready multi-agent systems.\n",
            "\n---\n",
            "*Generated by CrewAI + MEMANTO Integration Demo*",
        ])

        article = "\n".join(body_parts)
        return article


# ─── Main Demo ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="CrewAI + MEMANTO Integration Demo"
    )
    parser.add_argument(
        "--mode", choices=["research", "write", "both", "test"],
        default="both",
        help="Demo mode: research (store), write (retrieve), both, or test (memory only)"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("🦞  CrewAI + MEMANTO Integration Demo")
    print("=" * 60)

    # Check for API key
    api_key = os.getenv("MOORCHEH_API_KEY")
    if not api_key:
        print("\n⚠️  MOORCHEH_API_KEY not found in .env file.")
        print("   The demo requires a Moorcheh API key to use MEMANTO.")
        print("   Get one at: https://console.moorcheh.ai/api-keys")
        print("   Running in dry-run mode (will attempt MEMANTO but may fail gracefully).\n")

    # Initialize MEMANTO memory
    memory = MemantoAgentMemory(agent_id=AGENT_ID)

    if args.mode == "test":
        # Quick memory test
        print("\n🧪 Running memory test...")
        success = memory.remember(
            "This is a test memory to verify MEMANTO is working",
            memory_type="fact",
            tags="test",
        )
        print(f"  {'✅' if success else '❌'} Test memory stored")

        results = memory.recall("test memory", limit=3)
        print(f"  📖 Recall returned {len(results)} results")
        print(f"  📊 Stats: {memory.get_stats()}")
        return

    # Research mode: Store findings
    if args.mode in ("research", "both"):
        print("\n" + "─" * 60)
        print("📚 RESEARCH PHASE")
        print("─" * 60)

        researcher = ResearchAgent(memory)
        for topic in RESEARCH_TOPICS:
            researcher.research_and_store(topic)
            time.sleep(1)  # Brief pause between topics

        if args.mode == "research":
            print(f"\n✅ Research complete. {memory.get_stats()['stored']} memories stored.")
            print("   Run with --mode write to retrieve and use them.")
            return

    # Writer mode: Retrieve and write
    if args.mode in ("write", "both"):
        print("\n" + "─" * 60)
        print("📝 WRITING PHASE")
        print("─" * 60)

        writer = WriterAgent(memory)
        result = writer.retrieve_and_write("AI agents memory productivity best practices")

        if result["article"]:
            print("\n" + "─" * 60)
            print("📄 GENERATED ARTICLE")
            print("─" * 60)
            print(result["article"])

    # Summary
    print("\n" + "=" * 60)
    print("📊  Session Summary")
    print("=" * 60)
    stats = memory.get_stats()
    print(f"  Memories stored:  {stats['stored']}")
    print(f"  Memories recalled: {stats['recalled']}")
    print(f"  Errors:            {stats['errors']}")
    print()
    print("🦞  Demo complete! Check MEMANTO for persisted memories.")
    print("=" * 60)


if __name__ == "__main__":
    main()
