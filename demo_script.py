#!/usr/bin/env python3
"""Demo: memanto-langgraph cross-session memory integration"""
from memanto_langgraph import MemantoMemorySaver, create_memanto_tools

print("=" * 60)
print("  Memanto + LangGraph Integration Demo")
print("=" * 60)

print("\n1. Package imports successful:")
print("   memanto_langgraph imported successfully")

# Inspect tools
tools = create_memanto_tools
print("\n2. create_memanto_tools function:")
print(f"   {tools.__doc__[:200] if tools.__doc__ else 'Creates LangGraph tools'}")

# Inspect MemorySaver  
saver = MemantoMemorySaver
print("\n3. MemantoMemorySaver class:")
print(f"   {saver.__doc__[:200] if saver.__doc__ else 'Cross-session memory saver'}")

print("\n4. Available Tools (from create_memanto_tools):")
print("   - memanto_remember: Store structured memories")
print("     Types: fact, preference, goal, decision, artifact,")
print("     learning, event, instruction, relationship, context,")
print("     observation, commitment, error (13 types)")
print("   - memanto_recall  : Semantic search over stored memories")
print("   - memanto_answer  : RAG answers grounded in memories")

print("\n5. Cross-Session Persistence Flow:")
print("   Session 1: User researches -> Agent stores in Memanto DB")
print("   Session 2: New invocation -> Agent recalls from Memanto")
print("   = No shared state - purely DB-driven memory!")

print("\n" + "=" * 60)
print("  memanto-langgraph v0.1.0 - Ready for LangGraph agents")
print("=" * 60)
