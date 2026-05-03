from crewai import Agent, Task, Crew, Process
from memanto import MemantoClient
import os
from typing import Dict, List, Optional
import json

# Initialize Memanto client
MEMANTO_API_KEY = os.getenv("MEMANTO_API_KEY", "your-api-key-here")
memanto = MemantoClient(api_key=MEMANTO_API_KEY)

class MemantoMemory:
    """Custom memory class for CrewAI using Memanto"""
    
    def __init__(self, namespace: str = "crewai_memory"):
        self.namespace = namespace
        self.session_id = None
        
    def store(self, key: str, value: any, metadata: Optional[Dict] = None):
        """Store a memory in Memanto"""
        memory_data = {
            "key": key,
            "value": value,
            "metadata": metadata or {},
            "namespace": self.namespace
        }
        memanto.store_memory(memory_data)
        
    def retrieve(self, query: str, limit: int = 5) -> List[Dict]:
        """Retrieve memories from Memanto"""
        results = memanto.search_memory(
            query=query,
            namespace=self.namespace,
            limit=limit
        )
        return results
    
    def get_context(self, user_id: str) -> str:
        """Get relevant context for a user"""
        memories = self.retrieve(f"user_{user_id}", limit=10)
        context = "\n".join([m["value"] for m in memories])
        return context

# Initialize memory
memory = MemantoMemory()

# Define agents with memory integration
researcher = Agent(
    role="Research Analyst",
    goal="Research topics and maintain long-term knowledge",
    backstory="Expert researcher with perfect memory recall",
    tools=[],
    verbose=True,
    allow_delegation=False,
    memory=memory
)

writer = Agent(
    role="Content Writer",
    goal="Write engaging content based on research and user preferences",
    backstory="Creative writer who remembers every user's style",
    tools=[],
    verbose=True,
    allow_delegation=False,
    memory=memory
)

coordinator = Agent(
    role="Project Coordinator",
    goal="Coordinate tasks and maintain project context across sessions",
    backstory="Efficient coordinator with perfect project memory",
    tools=[],
    verbose=True,
    allow_delegation=False,
    memory=memory
)

# Define tasks with memory integration
research_task = Task(
    description="Research {topic} and store findings in long-term memory. Remember user preferences for {user_id}",
    expected_output="Comprehensive research report with key findings",
    agent=researcher,
    context=[{
        "memory_key": f"research_{topic}",
        "user_preferences": lambda: memory.get_context(user_id)
    }]
)

writing_task = Task(
    description="Write an article about {topic} based on research. Consider user's past preferences stored in memory",
    expected_output="Well-written article tailored to user preferences",
    agent=writer,
    context=[{
        "memory_key": f"article_{topic}",
        "research_data": lambda: memory.retrieve(f"research_{topic}")
    }]
)

coordination_task = Task(
    description="Coordinate the workflow and store project state in memory for {user_id}",
    expected_output="Coordinated project with full memory persistence",
    agent=coordinator,
    context=[{
        "memory_key": f"project_{user_id}",
        "project_state": lambda: memory.retrieve(f"project_{user_id}")
    }]
)

# Create crew with memory
crew = Crew(
    agents=[researcher, writer, coordinator],
    tasks=[research_task, writing_task, coordination_task],
    process=Process.sequential,
    verbose=True,
    memory=memory
)

# Example usage with memory persistence
def run_crew_with_memory(topic: str, user_id: str):
    """Run crew with full memory integration"""
    
    # Store initial user preferences
    memory.store(
        key=f"user_{user_id}_preferences",
        value={
            "style": "professional",
            "tone": "informative",
            "length": "medium"
        },
        metadata={"user_id": user_id, "type": "preferences"}
    )
    
    # Store previous session context if exists
    previous_context = memory.get_context(user_id)
    if previous_context:
        print(f"Restored context from previous session: {previous_context}")
    
    # Run the crew
    result = crew.kickoff(
        inputs={
            "topic": topic,
            "user_id": user_id
        }
    )
    
    # Store results in memory
    memory.store(
        key=f"session_{user_id}_{topic}",
        value=result,
        metadata={
            "user_id": user_id,
            "topic": topic,
            "timestamp": "2024-01-01"
        }
    )
    
    # Update project state
    memory.store(
        key=f"project_{user_id}",
        value={
            "last_topic": topic,
            "status": "completed",
            "output": result
        },
        metadata={"user_id": user_id, "type": "project_state"}
    )
    
    return result

# Advanced memory features
class MemantoMemoryManager:
    """Advanced memory management for CrewAI"""
    
    def __init__(self):
        self.memanto = memanto
        self.memory_cache = {}
        
    def semantic_search(self, query: str, threshold: float = 0.7) -> List[Dict]:
        """Semantic search across all memories"""
        results = self.memanto.semantic_search(
            query=query,
            threshold=threshold
        )
        return results
    
    def update_memory(self, key: str, value: any, merge: bool = True):
        """Update existing memory or create new one"""
        existing = self.memanto.get_memory(key)
        if existing and merge:
            if isinstance(existing["value"], dict) and isinstance(value, dict):
                existing["value"].update(value)
                value = existing["value"]
        self.memanto.store_memory({
            "key": key,
            "value": value,
            "namespace": "crewai_memory"
        })
    
    def get_conversation_history(self, user_id: str) -> List[Dict]:
        """Get full conversation history for a user"""
        return self.memanto.search_memory(
            query=f"user_{user_id}_session",
            namespace="crewai_memory",
            limit=100
        )
    
    def clear_user_memory(self, user_id: str):
        """Clear all memories for a specific user"""
        self.memanto.delete_memories(
            namespace="crewai_memory",
            filter={"user_id": user_id}
        )

# Initialize memory manager
memory_manager = MemantoMemoryManager()

# Example: Multi-session workflow with memory persistence
def multi_session_workflow():
    """Demonstrate memory persistence across multiple sessions"""
    
    # Session 1: Initial research
    print("Session 1: Initial research")
    result1 = run_crew_with_memory("AI Ethics", "user_123")
    print(f"Session 1 result: {result1}")
    
    # Session 2: Follow-up with memory context
    print("\nSession 2: Follow-up with memory")
    result2 = run_crew_with_memory("AI Regulation", "user_123")
    print(f"Session 2 result: {result2}")
    
    # Retrieve and display memory
    print("\nRetrieved memories:")
    memories = memory_manager.get_conversation_history("user_123")
    for mem in memories:
        print(f"- {mem['key']}: {mem['value'][:100]}...")
    
    # Semantic search across memories
    print("\nSemantic search results:")
    search_results = memory_manager.semantic_search("user preferences")
    for result in search_results:
        print(f"- {result['key']}: {result['value']}")

# Run the example
if __name__ == "__main__":
    multi_session_workflow()