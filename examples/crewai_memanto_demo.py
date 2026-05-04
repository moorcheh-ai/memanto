#!/usr/bin/env python3
"""
CrewAI + Memanto Integration Demo
=================================
A working example of using Memanto as the memory layer for CrewAI agents.

This demonstrates:
1. ResearchAgent stores findings → Memanto
2. WriterAgent retrieves from Memanto (simulating a "next day" scenario)
3. Cross-agent memory: ResearchAgent's findings visible to WriterAgent
4. Memory type classification for better retrieval

Requirements:
    pip install crewai memanto
    memanto setup   # one-time: enter your Moorcheh API key

Run:
    memanto agent create memeory-demo    # first time
    memanto agent activate memeory-demo
    python crewai_memanto_demo.py
"""

import subprocess
import time
import json
import sys
import os
from typing import Optional


# ─── Memanto Client (wraps CLI for programmatic use) ───

class MemantoClient:
    """Python wrapper around Memanto CLI for agent memory operations."""

    def __init__(self, agent_name: str = "memeory-demo"):
        self.agent_name = agent_name
        self._ensure_agent()

    def _run(self, cmd: list[str]) -> str:
        """Run a memanto CLI command and return stdout."""
        import shutil
        memanto_path = shutil.which("memanto") or ".venv/bin/memanto"
        env = os.environ.copy()
        # Pass MOORCHEH_API_KEY if set
        key = os.environ.get("MOORCHEH_API_KEY", "")
        if key:
            env["MOORCHEH_API_KEY"] = key
        result = subprocess.run(
            [memanto_path] + cmd,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        if result.returncode != 0:
            raise RuntimeError(f"memanto {' '.join(cmd)} failed: {result.stderr}")
        return result.stdout.strip()

    def _ensure_agent(self):
        """Create agent if it doesn't exist."""
        # Check if agent exists by listing
        try:
            agents = self._run(["agent", "list"])
            if self.agent_name not in agents:
                self._run(["agent", "create", self.agent_name])
                print(f"[Memanto] Created agent: {self.agent_name}")
            # Activate the agent
            self._run(["agent", "activate", self.agent_name])
        except RuntimeError:
            self._run(["agent", "create", self.agent_name])
            print(f"[Memanto] Created agent: {self.agent_name}")

    def remember(self, content: str, mem_type: str = "fact", title: str = "") -> str:
        """Store a memory. Supported types: instruction, fact, decision, preference,
        event, learning, observation, context, goal, commitment, relationship, artifact, error."""
        cmd = ["remember", content]
        if mem_type:
            cmd.extend(["--type", mem_type])
        if title:
            cmd.extend(["--title", title])
        return self._run(cmd)

    def recall(self, query: str, mem_type: Optional[str] = None) -> str:
        """Semantic search over stored memories."""
        cmd = ["recall", query]
        if mem_type:
            cmd.extend(["--type", mem_type])
        return self._run(cmd)

    def answer(self, question: str) -> str:
        """Grounded RAG answer based on stored memories."""
        return self._run(["answer", question])

    def conflicts(self) -> str:
        """Detect contradictory memories."""
        return self._run(["conflicts"])

    def daily_summary(self) -> str:
        """Generate a summary of today's memories."""
        return self._run(["daily-summary"])

    def export_memories(self) -> str:
        """Export all memories as structured markdown."""
        return self._run(["memory", "export"])


# ─── CrewAI Tool Wrappers for Memanto ───

try:
    from crewai.tools import BaseTool

    class MemantoStoreTool(BaseTool):
        """CrewAI Tool: Store a fact in Memanto long-term memory."""
        name: str = "memanto_store"
        description: str = (
            "Store a finding or fact in Memanto long-term memory. "
            "Args: content (str) - the information to store, "
            "mem_type (str) - memory type: fact/preference/decision/event/learning/observation"
        )
        client: "MemantoClient"

        def _run(self, content: str, mem_type: str = "fact") -> str:
            try:
                result = self.client.remember(content, mem_type=mem_type)
                return f"Stored in Memanto [{mem_type}]: {result}"
            except Exception as e:
                return f"Memanto store error: {e}"

    class MemantoRecallTool(BaseTool):
        """CrewAI Tool: Search past memories in Memanto."""
        name: str = "memanto_recall"
        description: str = (
            "Search Memanto long-term memory for relevant past information. "
            "Args: query (str) - what to search for"
        )
        client: "MemantoClient"

        def _run(self, query: str) -> str:
            try:
                results = self.client.recall(query)
                return f"Memanto recall results for '{query}':\n{results}"
            except Exception as e:
                return f"Memanto recall error: {e}"

    class MemantoAnswerTool(BaseTool):
        """CrewAI Tool: Get a grounded RAG answer from stored memories."""
        name: str = "memanto_answer"
        description: str = (
            "Ask Memanto a question that will be answered using stored memories. "
            "Args: question (str) - the question to answer from memory"
        )
        client: "MemantoClient"

        def _run(self, question: str) -> str:
            try:
                return self.client.answer(question)
            except Exception as e:
                return f"Memanto answer error: {e}"

except ImportError:
    # No CrewAI, use simple tool wrappers
    BaseTool = object


# ─── Main Demo ───

def demo_without_crewai(mc: MemantoClient):
    """Run the memory test without requiring CrewAI (standalone demo)."""
    print("=" * 60)
    print("🐜 Memanto Memory Test (No-CrewAI Standalone)")
    print("=" * 60)

    # Phase 1: Research Agent stores findings
    print("\n📝 Phase 1: ResearchAgent stores findings in Memanto")
    findings = [
        ("fact", "The target user prefers dark mode for their dashboard settings."),
        ("preference", "User timezone is Asia/Shanghai (UTC+8)."),
        ("fact", "Market analysis shows 67% growth in AI agent adoption in Q1 2026."),
        ("learning", "CrewAI with Memanto reduces context-loss errors by 40% compared to default memory."),
        ("observation", "Users report frustration when agents forget context between sessions."),
        ("decision", "Default theme should be set to dark mode based on user preference data."),
    ]

    for mem_type, content in findings:
        mc.remember(content, mem_type=mem_type)
        print(f"  ✅ [{mem_type}] Stored: {content[:70]}...")
        time.sleep(0.3)

    print(f"\n💾 Total: {len(findings)} memories stored.")

    # Phase 2: Simulate end of session
    print("\n⏸️  Session ended (simulating time passing)...")
    time.sleep(1)

    # Phase 3: Writer Agent retrieves from Memanto
    print("\n📖 Phase 3: WriterAgent retrieves from Memanto (simulating 'next day')\n")

    queries = [
        "user display preferences",
        "AI agent market growth statistics",
        "agent memory improvements",
        "user timezone settings",
    ]

    for q in queries:
        result = mc.recall(q)
        # Just show first 120 chars for readability
        summary = result[:150].replace("\n", " ") + ("..." if len(result) > 150 else "")
        print(f"  🔍 '{q}' → {summary}")
        time.sleep(0.3)

    # Phase 4: RAG Answer (requires LLM provider configured in Memanto)
    print("\n🤖 Phase 4: Grounded RAG answer from stored memories\n")
    print("   (Skipping 'answer' - requires LLM provider config in Memanto)")
    print("   The 'recall' above already proves cross-session memory retrieval.")
    print()

    # Phase 5: Contradiction detection (bonus)
    print("🔄 Phase 5: Contradiction detection (bonus)")
    try:
        mc.remember("The user switched preference to light mode for the dashboard.", mem_type="preference")
        print("  ✅ Stored contradictory memory: 'user switched to light mode'")
        time.sleep(0.5)
        conflicts = mc.conflicts()
        print(f"  ⚠️  Conflict check: {conflicts[:200]}")
    except Exception:
        print("  ⚠️  Skipping conflicts (included in full script with LLM)")
    print()

    # Phase 6: Export all memories
    print("📤 Phase 6: Memory export")
    export = mc.export_memories()
    mem_count = export.count("[fact]") + export.count("[preference]") + export.count("[learning]") + export.count("[observation]") + export.count("[decision]")
    print(f"  Exported memories (first 300 chars):\n  {export[:300]}...")
    print()

    print("=" * 60)
    print("✅ Memory Test Complete!")
    print("=" * 60)


def demo_with_crewai(mc: MemantoClient):
    """Run the full CrewAI + Memanto demo (requires crewai installed)."""
    try:
        from crewai import Agent, Task, Crew, Process
    except ImportError:
        print("⚠️  CrewAI not installed. Run: pip install crewai")
        print("Falling back to standalone demo...\n")
        demo_without_crewai(mc)
        return

    # Configure CrewAI to use DeepSeek (OpenAI-compatible)
    import os as _os
    llm_config = None
    deepseek_key = _os.environ.get("DEEPSEEK_API_KEY")
    if deepseek_key:
        from crewai import LLM
        llm_config = LLM(
            model="deepseek/deepseek-chat",
            base_url="https://api.deepseek.com/v1",
            api_key=deepseek_key,
        )
    # If neither configured, print message and fallback
    if llm_config is None and not _os.environ.get("OPENAI_API_KEY"):
        print("=" * 60)
        print("⚠️  No LLM API key found (Set DEEPSEEK_API_KEY or OPENAI_API_KEY)")
        print("   Running standalone Memanto demo instead...")
        print("   The CrewAI integration code is ready in the script.\n")
        print("=" * 60)
        demo_without_crewai(mc)
        return

    print("=" * 60)
    print("🐜 CrewAI + Memanto Memory Test")
    print("=" * 60)

    # Create tools
    store_tool = MemantoStoreTool(client=mc)
    recall_tool = MemantoRecallTool(client=mc)
    answer_tool = MemantoAnswerTool(client=mc)

    # Agent 1: Research Analyst
    research_agent = Agent(
        role="Research Analyst",
        goal="Research topics thoroughly and store all findings in Memanto for future recall",
        backstory=(
            "You are a diligent researcher. After every finding, you MUST use the "
            "memanto_store tool to save it permanently. This ensures no knowledge is lost."
        ),
        tools=[store_tool],
        llm=llm_config,
        allow_delegation=False,
        verbose=True,
    )

    # Agent 2: Content Writer (runs "next day")
    writer_agent = Agent(
        role="Content Writer",
        goal="Write reports by retrieving past research from Memanto memory",
        backstory=(
            "You write reports based on previously stored research. You ALWAYS search "
            "Memanto memory before writing, because your research colleague may have "
            "already found relevant facts. Use memanto_recall to find past work, "
            "and memanto_answer for cross-referencing."
        ),
        tools=[recall_tool, answer_tool],
        llm=llm_config,
        allow_delegation=False,
        verbose=True,
    )

    # Task 1: Research
    research_task = Task(
        description=(
            "Research the impact of AI agent memory on user experience. "
            "Find at least 3 key facts or statistics and store each one in Memanto "
            "using the memanto_store tool. Use appropriate memory types "
            "(fact, learning, observation, preference, decision)."
        ),
        expected_output="A summary of all findings stored in Memanto",
        agent=research_agent,
    )

    # Task 2: Write (simulating next day)
    write_task = Task(
        description=(
            "You are writing a report on 'AI Agent Memory & User Experience'. "
            "BEFORE writing anything, use memanto_recall to search Memanto for any "
            "previous research on this topic. If you find stored facts, use them. "
            "Then use memanto_answer to answer: 'What are the key findings about "
            "AI agent memory?' Write a short report based on the retrieved memories."
        ),
        expected_output="A report based on retrieved Memanto memories",
        agent=writer_agent,
    )

    # Create Crew
    crew = Crew(
        agents=[research_agent, writer_agent],
        tasks=[research_task, write_task],
        process=Process.sequential,
        verbose=True,
    )

    print("\n🚀 Starting CrewAI + Memanto workflow...\n")
    result = crew.kickoff()

    print("\n" + "=" * 60)
    print("📄 Final Output (Writer Agent's Report):")
    print("=" * 60)
    print(result)
    print("=" * 60)
    print("✅ CrewAI + Memanto Memory Test Complete!")
    print("=" * 60)


# ─── Entry Point ───

if __name__ == "__main__":
    mc = MemantoClient(agent_name="memeory-demo")

    # Try CrewAI first, fallback to standalone
    try:
        import crewai  # noqa: F401
        demo_with_crewai(mc)
    except ImportError:
        demo_without_crewai(mc)
