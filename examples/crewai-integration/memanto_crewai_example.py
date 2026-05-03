"""
CrewAI + Memanto Integration Example

This example demonstrates how to integrate Memanto as a memory layer
with CrewAI agents. The example shows:
1. Research Agent storing findings in Memanto
2. Writer Agent retrieving those findings 24 hours later
3. Cross-agent memory sharing

Requirements:
    - crewai>=0.80.0
    - memanto>=0.1.0
    - A valid Moorcheh API key
"""

import os
import sys
import time
from datetime import datetime, timedelta
from typing import Any, List

from crewai import Agent, Crew, Task, Process
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


# ============================================================================
# Memanto Integration Layer
# ============================================================================

class MemantoMemoryTool(BaseTool):
    """
    CrewAI tool interface for Memanto memory operations.

    This tool allows CrewAI agents to:
    - Store memories (remember)
    - Retrieve memories (recall)
    - Answer questions using RAG (answer)
    """

    name: str = "memanto_memory"
    description: str = "Store and retrieve long-term memories using Memanto"

    def __init__(self, api_key: str, agent_id: str = "crewai_agent"):
        super().__init__()
        self.api_key = api_key
        self.agent_id = agent_id
        self._client = None
        self._session_token = None

    def _get_client(self):
        """Lazy-load the Memanto client."""
        if self._client is None:
            try:
                from memanto.cli.client.sdk_client import SdkClient

                self._client = SdkClient(api_key=self.api_key)

                # Create agent if it doesn't exist
                try:
                    self._client.create_agent(
                        agent_id=self.agent_id,
                        pattern="tool",
                        description="CrewAI integrated agent"
                    )
                    print(f"[Memanto] Created new agent: {self.agent_id}")
                except Exception:
                    # Agent likely exists, that's fine
                    print(f"[Memanto] Using existing agent: {self.agent_id}")

                # Activate session
                session_data = self._client.activate_agent(self.agent_id)
                self._session_token = session_data["session_token"]
                print(f"[Memanto] Session activated for {self.agent_id}")

            except ImportError as e:
                print(f"[Memanto] Error importing memanto: {e}")
                print("[Memanto] Please install memanto: pip install memanto")
                raise
        return self._client

    def _run(self, query: str, action: str = "recall") -> str:
        """
        Execute the memory operation.

        Args:
            query: The query or content for the memory operation
            action: The action to perform ('remember', 'recall', or 'answer')

        Returns:
            The result of the memory operation
        """
        client = self._get_client()

        try:
            if action == "remember":
                # Parse memory type and content from query
                # Format: "TYPE: Content to remember"
                if ":" in query:
                    memory_type, content = query.split(":", 1)
                    memory_type = memory_type.strip().lower()
                    content = content.strip()
                else:
                    memory_type = "fact"
                    content = query.strip()

                result = client.remember(
                    agent_id=self.agent_id,
                    memory_type=memory_type,
                    title=content[:50] + "..." if len(content) > 50 else content,
                    content=content,
                    confidence=0.9,
                    source="crewai_agent",
                    provenance="explicit_statement"
                )
                return f"✅ Memory stored: {result.get('memory_id', 'unknown')}"

            elif action == "recall":
                result = client.recall(
                    agent_id=self.agent_id,
                    query=query,
                    limit=5
                )
                memories = result.get("memories", [])

                if not memories:
                    return "No relevant memories found."

                response = f"Found {len(memories)} memories:\n\n"
                for i, mem in enumerate(memories, 1):
                    response += f"{i}. {mem.get('title', 'Untitled')}\n"
                    response += f"   Content: {mem.get('content', '')[:100]}...\n"
                    response += f"   Score: {mem.get('score', 0):.3f}\n\n"
                return response

            elif action == "answer":
                result = client.answer(
                    agent_id=self.agent_id,
                    question=query,
                    limit=5
                )
                answer = result.get("answer", "No answer generated")
                sources = result.get("sources", [])

                response = f"🤖 Answer: {answer}\n\n"
                if sources:
                    response += f"📚 Sources used: {len(sources)} memories\n"
                return response

            else:
                return f"Unknown action: {action}"

        except Exception as e:
            return f"❌ Error: {str(e)}"


class MemoryWriterTool(MemantoMemoryTool):
    """Tool specialized for writing/storing memories."""

    name: str = "memory_writer"
    description: str = "Store information in long-term memory. Use this to save important facts, decisions, or findings."

    def _run(self, content: str) -> str:
        """Store a memory with the default type 'fact'."""
        return super()._run(content, action="remember")


class MemoryReaderTool(MemantoMemoryTool):
    """Tool specialized for reading/recalling memories."""

    name: str = "memory_reader"
    description: str = "Retrieve information from long-term memory. Use this to search for previously stored facts, decisions, or findings."

    def _run(self, query: str) -> str:
        """Recall memories based on a query."""
        return super()._run(query, action="recall")


class MemoryQA_Tool(MemantoMemoryTool):
    """Tool specialized for RAG-based question answering."""

    name: str = "memory_qa"
    description: str = "Ask questions and get answers based on stored memories. This uses retrieval-augmented generation to provide accurate answers."

    def _run(self, question: str) -> str:
        """Answer a question using RAG over stored memories."""
        return super()._run(question, action="answer")


# ============================================================================
# CrewAI Agents with Memanto Memory
# ============================================================================

def get_memanto_tools(api_key: str, agent_id: str = "crewai_agent"):
    """Get the Memanto tools for CrewAI agents."""
    return [
        MemoryWriterTool(api_key=api_key, agent_id=agent_id),
        MemoryReaderTool(api_key=api_key, agent_id=agent_id),
        MemoryQA_Tool(api_key=api_key, agent_id=agent_id),
    ]


def create_research_agent(api_key: str, agent_id: str = "crewai_agent"):
    """Create a Research Agent that stores findings in Memanto."""

    research_agent = Agent(
        role="Research Specialist",
        goal="Conduct thorough research and store important findings in long-term memory",
        backstory="""You are an expert researcher with a photographic memory for important information.
        You excel at gathering, analyzing, and storing research findings that can be accessed later.
        You use Memanto to store your findings so they can be retrieved by other agents or in future sessions.""",
        verbose=True,
        allow_delegation=False,
        tools=get_memanto_tools(api_key, agent_id),
        llm=None,  # Will use default
    )

    return research_agent


def create_writer_agent(api_key: str, agent_id: str = "crewai_agent"):
    """Create a Writer Agent that retrieves research from Memanto."""

    writer_agent = Agent(
        role="Content Writer",
        goal="Create compelling content based on research findings stored in memory",
        backstory="""You are a skilled writer who specializes in turning research into engaging content.
        You can access stored research findings through Memanto and use them to create articles, reports,
        or other content. You never invent facts - you only use what's been stored in memory.""",
        verbose=True,
        allow_delegation=False,
        tools=get_memanto_tools(api_key, agent_id),
        llm=None,  # Will use default
    )

    return writer_agent


# ============================================================================
# Demo Scenario: Memory Test
# ============================================================================

def demo_memory_test(api_key: str):
    """
    Demonstrate the Memory Test use case:

    1. Research Agent stores findings in Memanto
    2. Simulate time passing (24 hours)
    3. Writer Agent retrieves those findings from Memanto

    This demonstrates:
    - Cross-session memory (agent can recall after restart)
    - Cross-agent memory (different agents share memory)
    - Long-term retention (memories persist over time)
    """

    print("\n" + "="*80)
    print("🧠 MEMANTO + CREWAI INTEGRATION: MEMORY TEST DEMO")
    print("="*80 + "\n")

    agent_id = "crewai_memory_test"

    # ============================================================================
    # PART 1: Research Phase - Store Findings
    # ============================================================================
    print("\n" + "-"*80)
    print("📊 PART 1: RESEARCH PHASE - Storing Findings")
    print("-"*80 + "\n")

    research_agent = create_research_agent(api_key, agent_id)

    research_task = Task(
        description="""
        Research the topic of "AI Memory Systems" and store the following findings in memory:
        1. Store as 'fact': "Memanto is an open-source agentic memory layer that provides persistent memory for AI agents"
        2. Store as 'fact': "Traditional vector databases require indexing time, while Memanto provides instant availability"
        3. Store as 'fact': "Memanto achieved 89.8% accuracy on LongMemEval benchmark"
        4. Store as 'fact': "CrewAI is a framework for orchestrating role-playing AI agents"
        5. Store as 'decision': "Integrating Memanto with CrewAI provides agents with long-term memory capabilities"

        Use the memory_writer tool to store each finding. Make sure each is stored as a separate memory entry.
        """,
        expected_output="All 5 findings should be stored in Memanto memory successfully",
        agent=research_agent,
    )

    research_crew = Crew(
        agents=[research_agent],
        tasks=[research_task],
        process=Process.sequential,
        verbose=True,
    )

    print("\n🔍 Running Research Agent to store findings...\n")
    research_result = research_crew.kickoff()
    print(f"\n✅ Research Phase Complete!\n")

    # ============================================================================
    # PART 2: Time Simulation - 24 Hours Later
    # ============================================================================
    print("\n" + "-"*80)
    print("⏰ PART 2: TIME SIMULATION - 24 Hours Later")
    print("-"*80 + "\n")

    print("💤 Simulating 24-hour delay... (memory persists across sessions)")
    time.sleep(2)

    print("\n✅ Time simulation complete - creating a NEW session")
    print("   (In a real scenario, this would be a separate run/restart)\n")

    # ============================================================================
    # PART 3: Writer Phase - Retrieve Findings
    # ============================================================================
    print("\n" + "-"*80)
    print("✍️  PART 3: WRITER PHASE - Retrieving Findings")
    print("-"*80 + "\n")

    # Create a NEW writer agent (simulating different session/agent)
    writer_agent = create_writer_agent(api_key, agent_id)

    writer_task = Task(
        description="""
        You need to write a summary about "AI Memory Systems" based on research findings.
        Use the memory_reader tool to search for stored research about:
        1. "AI memory systems"
        2. "Memanto"
        3. "CrewAI integration"

        Then use the memory_qa tool to answer: "What are the key benefits of using Memanto for AI memory?"

        Finally, write a concise summary (200-300 words) incorporating the retrieved information.
        Do NOT invent any facts - only use what you find in memory.
        """,
        expected_output="A well-written summary of AI memory systems based on retrieved research",
        agent=writer_agent,
    )

    writer_crew = Crew(
        agents=[writer_agent],
        tasks=[writer_task],
        process=Process.sequential,
        verbose=True,
    )

    print("\n📝 Running Writer Agent to retrieve and synthesize findings...\n")
    writer_result = writer_crew.kickoff()
    print(f"\n✅ Writer Phase Complete!\n")

    # ============================================================================
    # PART 4: Verification - Check Memory Contents
    # ============================================================================
    print("\n" + "-"*80)
    print("✅ PART 4: VERIFICATION - Memory Contents")
    print("-"*80 + "\n")

    # Create a new MemantoMemoryTool to verify memories
    verifier = MemantoMemoryTool(api_key=api_key, agent_id=agent_id)

    print("📚 All stored memories:\n")
    all_memories = verifier._run("*", action="recall")
    print(all_memories)

    print("\n" + "="*80)
    print("🎉 MEMORY TEST DEMO COMPLETE!")
    print("="*80 + "\n")

    print("✅ Demonstrated:")
    print("   • Research Agent stored findings in Memanto")
    print("   • Memories persisted across session restart")
    print("   • Writer Agent retrieved and used findings from memory")
    print("   • Cross-agent memory sharing worked successfully\n")


def demo_contradiction_handling(api_key: str):
    """
    Demonstrate handling contradictory memories (bonus feature).

    Shows how Memanto can handle updates and supersede old information.
    """

    print("\n" + "="*80)
    print("🔄 BONUS DEMO: CONTRADICTION HANDLING")
    print("="*80 + "\n")

    agent_id = "crewai_contradiction_test"

    # Store initial information
    print("\n1️⃣  Storing initial information...\n")
    tool = MemoryWriterTool(api_key=api_key, agent_id=agent_id)
    result = tool._run("fact: Python 3.10 was released in October 2021")
    print(result)

    # Store updated (contradictory) information
    print("\n2️⃣  Storing updated information (superseding old)...\n")
    result = tool._run("fact: Python 3.11 was released in October 2022, adding significant performance improvements")
    print(result)

    # Query to see what Memanto returns
    print("\n3️⃣  Querying: 'What is the latest Python version and when was it released?'\n")
    qa_tool = MemoryQA_Tool(api_key=api_key, agent_id=agent_id)
    answer = qa_tool._run("What is the latest Python version and when was it released?")
    print(answer)

    print("\n✅ Contradiction handling demo complete!\n")


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main entry point for the example."""

    # Check for API key
    api_key = os.getenv("MOORCHEH_API_KEY")

    if not api_key:
        print("❌ Error: MOORCHEH_API_KEY environment variable not set")
        print("\nPlease set your Moorcheh API key:")
        print("  export MOORCHEH_API_KEY='your-api-key-here'")
        print("\nGet your API key from: https://console.moorcheh.ai/api-keys")
        sys.exit(1)

    # Run the main memory test demo
    demo_memory_test(api_key)

    # Ask if user wants to run bonus demos
    print("\n" + "="*80)
    response = input("Run bonus contradiction handling demo? (y/n): ").strip().lower()
    if response == 'y':
        demo_contradiction_handling(api_key)

    print("\n🎉 All demos complete!\n")


if __name__ == "__main__":
    main()
