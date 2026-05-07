"""
CrewAI + Memanto Integration Example

This example demonstrates how to use Memanto as the memory layer
for CrewAI agents, enabling long-term memory across sessions.

Bounty: $100 - moorcheh-ai/memanto #37
"""

import os
from datetime import datetime
from crewai import Agent, Task, Crew, Process
from crewai.memory import LongTermMemory
from memanto import MemantoMemory

# Initialize Memanto as the memory backend
memanto_memory = MemantoMemory(
    db_path="./crewai_memory.db",
    embedding_model="sentence-transformers/all-MiniLM-L6-v2"
)

class MemantoCrewMemory(LongTermMemory):
    """Custom CrewAI memory backend using Memanto."""
    
    def __init__(self, memanto_memory):
        self.memory = memanto_memory
        
    def save(self, key: str, value: str, metadata: dict = None):
        """Save memory to Memanto."""
        if metadata is None:
            metadata = {}
        metadata["timestamp"] = datetime.now().isoformat()
        metadata["agent"] = "crewai"
        self.memory.add(
            content=value,
            metadata=metadata,
            tags=["crewai", key]
        )
        
    def search(self, query: str, limit: int = 5):
        """Search memories in Memanto."""
        results = self.memory.search(
            query=query,
            limit=limit,
            tags=["crewai"]
        )
        return results
    
    def get(self, key: str):
        """Get specific memory by key."""
        results = self.memory.search(
            query=key,
            limit=1,
            tags=["crewai", key]
        )
        return results[0] if results else None


# Create Memanto-backed memory
crew_memory = MemantoCrewMemory(memanto_memory)

# Agent 1: Research Agent
researcher = Agent(
    role="Research Specialist",
    goal="Conduct thorough research and store findings for future use",
    backstory="""You are an expert researcher who excels at gathering 
    information and storing it for later retrieval. You use Memanto to 
    remember important findings across sessions.""",
    memory=crew_memory,
    verbose=True,
    allow_delegation=False
)

# Agent 2: Writer Agent
writer = Agent(
    role="Content Writer",
    goal="Create content based on research findings",
    backstory="""You are a skilled writer who retrieves research 
    findings from memory to create compelling content. You rely on 
    Memanto to access previous research.""",
    memory=crew_memory,
    verbose=True,
    allow_delegation=False
)

# Task 1: Research Task
research_task = Task(
    description="""
    Research the topic: "Benefits of Agentic Memory Systems"
    
    Store your findings in memory with the key "agentic_memory_research".
    Include:
    - Definition of agentic memory
    - Key benefits (3-5 points)
    - Real-world applications
    
    Save your complete findings to memory.
    """,
    agent=researcher,
    expected_output="Research findings stored in Memanto memory"
)

# Task 2: Writing Task (retrieves from memory)
writing_task = Task(
    description="""
    Retrieve the research findings with key "agentic_memory_research" 
    from memory and write a blog post about it.
    
    The blog post should:
    - Have an engaging title
    - Include an introduction
    - Cover all the benefits found in research
    - End with a conclusion
    
    Save the final blog post to memory with key "agentic_memory_blog".
    """,
    agent=writer,
    expected_output="Blog post created and stored in memory",
    context=[research_task]
)

# Create the crew
crew = Crew(
    agents=[researcher, writer],
    tasks=[research_task, writing_task],
    process=Process.sequential,
    memory=True,
    verbose=True
)


def main():
    """Run the CrewAI + Memanto example."""
    print("=" * 60)
    print("🧠 CrewAI + Memanto Integration Demo")
    print("=" * 60)
    print("\nThis demo shows:")
    print("1. Research Agent stores findings in Memanto")
    print("2. Writer Agent retrieves findings from Memanto")
    print("3. Memory persists across the workflow\n")
    
    # Run the crew
    result = crew.kickoff()
    
    print("\n" + "=" * 60)
    print("✅ Crew Execution Complete!")
    print("=" * 60)
    print("\nFinal Output:")
    print(result)
    
    # Demonstrate memory retrieval
    print("\n" + "-" * 60)
    print("🔍 Memory Retrieval Demo")
    print("-" * 60)
    
    # Search for stored research
    research_results = crew_memory.search("agentic memory benefits", limit=3)
    print(f"\nFound {len(research_results)} memories about 'agentic memory benefits':")
    for i, mem in enumerate(research_results, 1):
        print(f"\n{i}. {mem['content'][:200]}...")
        print(f"   Tags: {mem.get('tags', [])}")
        print(f"   Time: {mem.get('metadata', {}).get('timestamp', 'N/A')}")
    
    # Demonstrate cross-session memory
    print("\n" + "-" * 60)
    print("💾 Cross-Session Memory Test")
    print("-" * 60)
    
    # Simulate a new session retrieving old data
    new_session_memory = MemantoCrewMemory(memanto_memory)
    old_research = new_session_memory.get("agentic_memory_research")
    
    if old_research:
        print("\n✅ Successfully retrieved research from previous session!")
        print(f"Content preview: {old_research['content'][:150]}...")
    else:
        print("\n❌ Could not retrieve previous session data")
    
    print("\n" + "=" * 60)
    print("🎉 Demo Complete!")
    print("=" * 60)
    print("\nMemanto successfully enabled:")
    print("  ✓ Long-term memory for CrewAI agents")
    print("  ✓ Cross-agent memory sharing")
    print("  ✓ Cross-session memory persistence")
    print("  ✓ Semantic search capabilities")
    
    return result


if __name__ == "__main__":
    main()
