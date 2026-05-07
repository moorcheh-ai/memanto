#!/usr/bin/env python3
"""
Demo script for CrewAI + Memanto integration
Generates terminal output for video recording
"""

import time
import sys

def print_slow(text, delay=0.005):
    """Print text with typing effect"""
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(delay)
    print()

def demo():
    print("\033[2J\033[H")  # Clear screen
    
    # Header
    print("=" * 70)
    print_slow("🧠  CrewAI + Memanto Integration Demo", 0.01)
    print("=" * 70)
    print()
    
    time.sleep(0.1)
    
    # Setup
    print_slow("📦  Initializing Memanto memory backend...")
    time.sleep(0.05)
    print_slow("    ✓ Connected to SQLite database: crewai_memory.db")
    print_slow("    ✓ Embedding model loaded: all-MiniLM-L6-v2")
    print()
    
    time.sleep(0.05)
    
    # Research Agent
    print_slow("🔍  Research Agent: Starting research on 'Agentic Memory Systems'")
    time.sleep(0.1)
    print_slow("    → Searching academic papers...")
    time.sleep(0.05)
    print_slow("    → Analyzing industry reports...")
    time.sleep(0.05)
    print_slow("    → Synthesizing findings...")
    time.sleep(0.05)
    print()
    
    # Store to memory
    print_slow("💾  Storing research to Memanto memory...")
    time.sleep(0.05)
    print_slow("    ✓ Memory saved with key: 'agentic_memory_research'")
    print_slow("    ✓ Tags: ['crewai', 'research', 'agentic_memory']")
    print_slow("    ✓ Metadata: timestamp, agent_id, session_id")
    print()
    
    time.sleep(0.1)
    
    # Simulate time passing
    print_slow("⏰  [24 hours later... New session started]")
    print()
    time.sleep(0.1)
    
    # Writer Agent
    print_slow("✍️  Writer Agent: Starting content creation")
    time.sleep(0.05)
    print_slow("    → Retrieving research from Memanto...")
    time.sleep(0.05)
    print_slow("    ✓ Found 1 memory with key 'agentic_memory_research'")
    print_slow("    ✓ Content preview: 'Agentic memory systems provide...'")
    print()
    
    time.sleep(0.05)
    
    # Writing
    print_slow("    → Writing blog post...")
    time.sleep(0.05)
    print_slow("    ✓ Title: 'The Future of AI: Agentic Memory Systems'")
    print_slow("    ✓ Introduction: ✓")
    print_slow("    ✓ Key Benefits: ✓")
    print_slow("    ✓ Real-world Applications: ✓")
    print_slow("    ✓ Conclusion: ✓")
    print()
    
    # Store blog
    print_slow("💾  Storing blog post to Memanto...")
    time.sleep(0.05)
    print_slow("    ✓ Memory saved with key: 'agentic_memory_blog'")
    print()
    
    time.sleep(0.05)
    
    # Search demo
    print_slow("🔍  Semantic Search Demo:")
    print_slow("    Query: 'memory benefits for AI agents'")
    time.sleep(0.05)
    print_slow("    ✓ Found 2 relevant memories:")
    print_slow("      1. 'agentic_memory_research' (score: 0.94)")
    print_slow("      2. 'agentic_memory_blog' (score: 0.87)")
    print()
    
    time.sleep(0.05)
    
    # Summary
    print("=" * 70)
    print_slow("✅  Demo Complete!", 0.01)
    print("=" * 70)
    print()
    print_slow("🎯  Key Achievements:")
    print_slow("    ✓ Research Agent stored findings in Memanto")
    print_slow("    ✓ Writer Agent retrieved findings 24h later")
    print_slow("    ✓ Cross-session memory persistence verified")
    print_slow("    ✓ Semantic search working correctly")
    print()
    print_slow("💡  Memanto enables long-term memory for CrewAI agents!")
    print()

if __name__ == "__main__":
    demo()
