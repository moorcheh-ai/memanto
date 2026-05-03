"""
Quick Start Script for CrewAI + Memanto Integration

A simplified version of the main example that's faster to run and test.
This demonstrates the core memory persistence feature.
"""

import os
import sys


def main():
    """Quick start demo showing Memanto memory persistence."""

    print("\n" + "="*80)
    print("🧠 CrewAI + Memanto: Quick Start Demo")
    print("="*80 + "\n")

    # Check for API key
    api_key = os.getenv("MOORCHEH_API_KEY")
    if not api_key:
        print("❌ Error: MOORCHEH_API_KEY environment variable not set\n")
        print("Please set your Moorcheh API key:")
        print("  export MOORCHEH_API_KEY='your-api-key-here'\n")
        print("Get your API key from: https://console.moorcheh.ai/api-keys")
        return 1

    try:
        from memanto.cli.client.sdk_client import SdkClient

        print("✅ Memanto client imported successfully\n")

        # Initialize client
        client = SdkClient(api_key=api_key)

        # Create/activate agent
        agent_id = "crewai_quickstart"
        try:
            client.create_agent(agent_id=agent_id, pattern="tool")
            print(f"✅ Created agent: {agent_id}")
        except Exception as e:
            print(f"ℹ️  Agent exists or creation issue: {e}")
            print(f"ℹ️  Continuing with existing agent: {agent_id}")

        # Activate session
        session = client.activate_agent(agent_id=agent_id)
        print(f"✅ Session activated (expires: {session['expires_at'][:19]})\n")

        # ============================================================================
        # PART 1: Store Memories (simulating Research Agent)
        # ============================================================================
        print("-" * 80)
        print("📝 PART 1: Storing Memories (Research Agent)")
        print("-" * 80 + "\n")

        memories_to_store = [
            ("fact", "Memanto is an open-source agentic memory layer"),
            ("fact", "CrewAI is a framework for orchestrating AI agents"),
            ("decision", "Integrating Memanto provides long-term memory to CrewAI agents"),
            ("preference", "Users prefer concise responses with clear structure"),
        ]

        stored_ids = []
        for mem_type, content in memories_to_store:
            result = client.remember(
                agent_id=agent_id,
                memory_type=mem_type,
                title=content[:50],
                content=content,
                confidence=0.9,
                source="research_agent",
                provenance="explicit_statement"
            )
            mem_id = result.get("memory_id", "unknown")
            stored_ids.append(mem_id)
            print(f"✅ Stored [{mem_type}]: {content[:60]}...")
            print(f"   ID: {mem_id}\n")

        # ============================================================================
        # PART 2: Simulate Time Passing (new session)
        # ============================================================================
        print("-" * 80)
        print("⏰ PART 2: Time Passing (New Session)")
        print("-" * 80 + "\n")

        print("💤 Simulating session restart (memories persist)...\n")

        # Deactivate current session
        client.deactivate_agent(agent_id=agent_id)
        print("✅ Session ended")

        # Activate new session (simulating restart)
        session = client.activate_agent(agent_id=agent_id)
        print(f"✅ New session started (expires: {session['expires_at'][:19]})\n")

        # ============================================================================
        # PART 3: Retrieve Memories (simulating Writer Agent)
        # ============================================================================
        print("-" * 80)
        print("🔍 PART 3: Retrieving Memories (Writer Agent)")
        print("-" * 80 + "\n")

        queries = [
            "Memanto capabilities",
            "CrewAI framework",
            "integration decisions",
            "user preferences",
        ]

        for query in queries:
            print(f"Query: '{query}'")
            result = client.recall(
                agent_id=agent_id,
                query=query,
                limit=3
            )
            memories = result.get("memories", [])

            if memories:
                for i, mem in enumerate(memories[:2], 1):
                    print(f"  {i}. {mem.get('content', '')[:70]}...")
                    print(f"     Score: {mem.get('score', 0):.3f}\n")
            else:
                print("  No memories found\n")

        # ============================================================================
        # PART 4: RAG-based Question Answering
        # ============================================================================
        print("-" * 80)
        print("🤖 PART 4: RAG-based Question Answering")
        print("-" * 80 + "\n")

        question = "What are the key benefits of integrating Memanto with CrewAI?"
        print(f"Question: {question}\n")

        answer_result = client.answer(
            agent_id=agent_id,
            question=question,
            limit=3
        )

        answer = answer_result.get("answer", "No answer generated")
        sources = answer_result.get("sources", [])

        print(f"Answer: {answer}\n")
        if sources:
            print(f"Sources used: {len(sources)} memory entries\n")

        # ============================================================================
        # Summary
        # ============================================================================
        print("=" * 80)
        print("✅ Quick Start Demo Complete!")
        print("=" * 80 + "\n")

        print("Demonstrated:")
        print("  • Stored memories with different types (fact, decision, preference)")
        print("  • Memories persisted across session restart")
        print("  • Semantic search retrieved relevant memories")
        print("  • RAG-based QA answered questions using memory context\n")

        print("🎉 Ready to integrate Memanto into your CrewAI projects!\n")
        print("For the full demo with multi-agent workflow, run:")
        print("  python memanto_crewai_example.py\n")

        return 0

    except ImportError as e:
        print(f"❌ Import error: {e}\n")
        print("Please install required packages:")
        print("  pip install -r requirements.txt\n")
        return 1

    except Exception as e:
        print(f"❌ Error: {e}\n")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
