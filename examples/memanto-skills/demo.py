#!/usr/bin/env python3
"""
Demo: Context flow between mattpocock Skills via Memanto

Simulates a realistic workflow:
1. Architecture skill stores design decisions
2. TDD skill recalls architecture + stores test context
3. Handoff skill recalls everything
"""
from memanto_memory import MemantoMemory
import time

memory = MemantoMemory()

# Simulate Skill: /grill-with-docs (Architecture Design)
def skill_grill_with_docs(project: str, topic: str):
    print(f"[grill-with-docs] Analyzing {topic}...")
    arch_facts = {
        "framework": "FastAPI",
        "database": "PostgreSQL",
        "api_design": "RESTful + GraphQL hybrid",
        "auth": "JWT with refresh tokens",
        "deployment": "Docker + Kubernetes"
    }
    for k, v in arch_facts.items():
        memory.store(project, k, v)
    print(f"[grill-with-docs] Stored {len(arch_facts)} architecture facts to Memanto")
    return arch_facts

# Simulate Skill: /tdd (Test-Driven Development)
def skill_tdd(project: str):
    print(f"[tdd] Recalling architecture context...")
    arch_context = memory.recall(project)
    print(f"[tdd] Found {len(arch_context)} context items from grill-with-docs")
    print(f"[tdd] Writing tests for {arch_context.get('framework', 'unknown')}")
    
    test_facts = {
        "test_framework": "pytest",
        "coverage_target": "85%",
        "api_tests": "30 test cases",
        "status": "in_progress"
    }
    for k, v in test_facts.items():
        memory.store(project, k, v)
    print(f"[tdd] Stored {len(test_facts)} test facts to Memanto")

# Simulate Skill: /handoff (Handoff to another developer)
def skill_handoff(project: str):
    print(f"[handoff] Recalling ALL project context...")
    all_context = memory.recall(project)
    print(f"[handoff] Complete project summary:")
    for k, v in all_context.items():
        print(f"  - {k}: {v}")
    print(f"[handoff] Handoff document generated with {len(all_context)} context items")
    return all_context

# Run the demo
if __name__ == "__main__":
    PROJECT = "demo-app"
    print("="*60)
    print("Memanto + mattpocock Skills: Context Flow Demo")
    print("="*60)
    
    # Step 1: Architecture design
    print("\n>>> Skill: /grill-with-docs")
    skill_grill_with_docs(PROJECT, "FastAPI web application")
    
    # Step 2: TDD (different "session")
    print("\n>>> Skill: /tdd (new session, no prior context)")
    skill_tdd(PROJECT)
    
    # Step 3: Handoff (recalls everything)
    print("\n>>> Skill: /handoff (final handoff)")
    final = skill_handoff(PROJECT)
    
    print("\n" + "="*60)
    print("Cross-skill context flow achieved via Memanto!")
    print(f"Total context items: {len(final)}")
    print("="*60)
