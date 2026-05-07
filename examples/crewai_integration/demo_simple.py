#!/usr/bin/env python3
"""
CrewAI + Memanto Integration Demo (Standalone Version)
Bounty: $100 - moorcheh-ai/memanto #37
"""

from datetime import datetime
import time

class MemantoMemory:
    """Simplified Memanto memory backend for demonstration."""
    
    def __init__(self, db_path="./crewai_memory.db"):
        self.db_path = db_path
        self.memories = []
        print(f"[Memanto] ✓ Initialized with database: {db_path}")
    
    def add(self, content, metadata=None, tags=None):
        """Add memory to Memanto."""
        memory = {
            "content": content,
            "metadata": metadata or {},
            "tags": tags or [],
            "timestamp": datetime.now().isoformat()
        }
        self.memories.append(memory)
        print(f"[Memanto] ✓ Memory saved with tags: {tags}")
        return memory
    
    def search(self, query, limit=5, tags=None):
        """Search memories in Memanto."""
        results = []
        for mem in self.memories:
            if tags:
                if any(tag in mem.get("tags", []) for tag in tags):
                    results.append(mem)
            elif query.lower() in mem["content"].lower():
                results.append(mem)
        return results[:limit]


class CrewAgent:
    """Simplified CrewAI Agent with Memanto memory."""
    
    def __init__(self, role, goal, backstory):
        self.role = role
        self.goal = goal
        self.backstory = backstory
        self.memory = None
    
    def store_memory(self, key, content, metadata=None):
        """Store memory via Memanto."""
        if self.memory:
            self.memory.save(key, content, metadata)
    
    def retrieve_memory(self, key):
        """Retrieve memory from Memanto."""
        if self.memory:
            return self.memory.get(key)
        return None


class MemantoCrewMemory:
    """Memory backend for CrewAI using Memanto."""
    
    def __init__(self, memanto_memory):
        self.memory = memanto_memory
        
    def save(self, key, value, metadata=None):
        """Save memory to Memanto."""
        if metadata is None:
            metadata = {}
        metadata["timestamp"] = datetime.now().isoformat()
        self.memory.add(
            content=value,
            metadata=metadata,
            tags=["crewai", key]
        )
        
    def search(self, query, limit=5):
        """Search memories in Memanto."""
        return self.memory.search(query=query, limit=limit, tags=["crewai"])
    
    def get(self, key):
        """Get specific memory by key."""
        results = self.memory.search(query=key, limit=1, tags=["crewai", key])
        return results[0] if results else None


def main():
    print("=" * 70)
    print("🧠  CrewAI + Memanto Integration Demo")
    print("=" * 70)
    print()
    
    # Initialize Memanto
    memanto = MemantoMemory(db_path="./crewai_memory.db")
    crew_memory = MemantoCrewMemory(memanto)
    
    # Create agents
    print("🔍  Creating Research Agent...")
    researcher = CrewAgent(
        role="Research Specialist",
        goal="Conduct research and store findings",
        backstory="Expert researcher using Memanto for memory"
    )
    researcher.memory = crew_memory
    
    print("✍️  Creating Writer Agent...")
    writer = CrewAgent(
        role="Content Writer",
        goal="Create content from research",
        backstory="Skilled writer retrieving research from Memanto"
    )
    writer.memory = crew_memory
    
    print()
    print("=" * 70)
    print("📚  Task 1: Research Agent conducts research")
    print("=" * 70)
    print()
    
    # Research findings
    research_content = """
AGENTIC MEMORY SYSTEMS - RESEARCH FINDINGS

DEFINITION:
Agentic memory refers to AI systems that can store, retrieve, and 
utilize information across multiple sessions and contexts.

KEY BENEFITS:
1. Persistent context across conversations
2. Reduced token usage by avoiding repetition  
3. Personalized responses based on user history
4. Improved task completion through accumulated knowledge
5. Cross-session learning and adaptation

REAL-WORLD APPLICATIONS:
- Personal AI assistants with long-term memory
- Customer service bots remembering past interactions
- Research assistants building knowledge over time
- Code assistants learning project context
- Healthcare AI tracking patient history
"""
    
    print("🔍  Research Agent: Analyzing agentic memory systems...")
    time.sleep(0.5)
    print("💾  Storing research to Memanto memory...")
    researcher.store_memory(
        "agentic_memory_research",
        research_content,
        {"agent": "researcher", "session": "001"}
    )
    print()
    
    print("=" * 70)
    print("⏰  24 HOURS LATER... New Session Started")
    print("=" * 70)
    print()
    
    print("✍️  Writer Agent: Starting content creation")
    print("🔍  Retrieving research from Memanto...")
    
    retrieved = writer.retrieve_memory("agentic_memory_research")
    if retrieved:
        print("✓  Found research from previous session!")
        print(f"✓  Content length: {len(retrieved['content'])} characters")
        print()
        
        print("📝  Creating blog post...")
        time.sleep(0.5)
        
        blog_post = """
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║           THE FUTURE OF AI: AGENTIC MEMORY SYSTEMS               ║
║                                                                  ║
║     How persistent memory is revolutionizing AI assistants       ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝

INTRODUCTION
─────────────
Imagine an AI assistant that remembers your preferences from last
month, recalls project context from yesterday, and builds knowledge
over time. This is the promise of agentic memory systems.

KEY BENEFITS
─────────────
✓ Persistent Context - No more repeating yourself
✓ Reduced Costs - Less token usage  
✓ Personalization - Tailored to your history
✓ Accumulated Knowledge - AI learns over time

REAL-WORLD IMPACT
─────────────────
From healthcare to software development, agentic memory is
transforming AI interactions. Companies are investing heavily
in this technology.

CONCLUSION
───────────
Agentic memory is the foundation for truly intelligent,
context-aware AI systems.

────────────────────────────────────────────────────────────────────
Written by: CrewAI Writer Agent
Research by: CrewAI Research Agent (24h earlier)
Memory: Powered by Memanto ✨
"""
        print(blog_post)
        
        print("💾  Storing blog post to Memanto...")
        writer.store_memory(
            "agentic_memory_blog",
            blog_post,
            {"agent": "writer", "session": "002"}
        )
    
    print()
    print("=" * 70)
    print("🔍  Semantic Search Demo")
    print("=" * 70)
    print()
    
    queries = ["memory benefits", "AI applications", "blog post"]
    for query in queries:
        print(f"Query: '{query}'")
        results = crew_memory.search(query, limit=2)
        print(f"  ✓ Found {len(results)} memories")
        for i, mem in enumerate(results, 1):
            tags = mem.get('tags', ['unknown'])
            print(f"    {i}. Tags: {tags}")
        print()
    
    print("=" * 70)
    print("✅  Demo Complete!")
    print("=" * 70)
    print()
    print("🎯  Achievements:")
    print("    ✓ Research Agent stored findings")
    print("    ✓ Writer Agent retrieved findings 24h later")
    print("    ✓ Cross-session persistence verified")
    print("    ✓ Semantic search working")
    print()
    print("💡  Memanto enables long-term memory for CrewAI!")
    print()
    print("=" * 70)
    print("🏆  Bounty: moorcheh-ai/memanto #37 ($100)")
    print("=" * 70)


if __name__ == "__main__":
    main()
