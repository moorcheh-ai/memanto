from crewai import Agent, Task, Crew, Process
from memanto import MemantoClient
import os
from typing import Dict, List, Optional

# Initialize Memanto client
memanto = MemantoClient(
    api_key=os.getenv("MEMANTO_API_KEY"),
    base_url=os.getenv("MEMANTO_BASE_URL", "http://localhost:8000")
)

class MemantoMemory:
    """Memory layer using Memanto for persistent agent memory"""
    
    def __init__(self, namespace: str = "crewai_memory"):
        self.namespace = namespace
        self.memanto = memanto
    
    def store_memory(self, agent_name: str, key: str, value: str, metadata: Optional[Dict] = None):
        """Store a memory entry"""
        memory_data = {
            "agent": agent_name,
            "key": key,
            "value": value,
            "metadata": metadata or {}
        }
        return self.memanto.store(self.namespace, memory_data)
    
    def retrieve_memory(self, agent_name: str, query: str, limit: int = 5) -> List[Dict]:
        """Retrieve relevant memories based on query"""
        results = self.memanto.search(
            namespace=self.namespace,
            query=query,
            filter={"agent": agent_name},
            limit=limit
        )
        return results
    
    def get_user_preferences(self, user_id: str) -> Dict:
        """Get stored user preferences"""
        results = self.memanto.search(
            namespace=self.namespace,
            query=f"user_preferences_{user_id}",
            filter={"key": f"user_preferences_{user_id}"},
            limit=1
        )
        return results[0] if results else {}
    
    def store_task_result(self, task_id: str, result: str, agent_name: str):
        """Store task execution result"""
        return self.store_memory(
            agent_name=agent_name,
            key=f"task_result_{task_id}",
            value=result,
            metadata={"task_id": task_id, "timestamp": str(__import__('time').time())}
        )

# Initialize memory
memory = MemantoMemory()

# Define agents with memory capabilities
researcher = Agent(
    role="Research Analyst",
    goal="Gather and analyze information with memory of past research",
    backstory="""You are an expert research analyst who remembers all previous research 
    sessions using Memanto memory. You build upon past knowledge and maintain context 
    across multiple research tasks.""",
    tools=[],  # Add custom tools if needed
    allow_delegation=True,
    verbose=True,
    memory=memory  # Custom memory integration
)

writer = Agent(
    role="Content Writer",
    goal="Create compelling content based on research and user preferences",
    backstory="""You are a skilled writer who remembers user preferences and writing style 
    from previous interactions. You use Memanto to maintain consistency across all content.""",
    tools=[],
    allow_delegation=False,
    verbose=True,
    memory=memory
)

coordinator = Agent(
    role="Task Coordinator",
    goal="Coordinate tasks and maintain workflow state across sessions",
    backstory="""You coordinate the entire workflow, remembering task states and 
    dependencies using Memanto's persistent memory. You ensure no task is repeated 
    unnecessarily.""",
    tools=[],
    allow_delegation=True,
    verbose=True,
    memory=memory
)

# Define tasks with memory integration
research_task = Task(
    description="""Research the latest trends in {topic}. Use Memanto memory to check 
    if similar research was done before. If found, build upon previous findings. 
    Store all new findings in Memanto for future reference.""",
    expected_output="A comprehensive research report with references to previous findings",
    agent=researcher,
    context=[{
        "description": "Check Memanto for previous research on this topic",
        "expected_output": "Previous research findings if any"
    }]
)

writing_task = Task(
    description="""Create a well-written article about {topic} based on the research 
    provided. Check Memanto for user preferences regarding writing style, tone, and 
    format. Store the final article in Memanto for future reference.""",
    expected_output="A polished article following user preferences",
    agent=writer,
    context=[{
        "description": "Retrieve user preferences from Memanto",
        "expected_output": "User writing preferences"
    }]
)

coordination_task = Task(
    description="""Coordinate the research and writing tasks. Track progress in Memanto 
    memory. Ensure all tasks are completed and results are stored. Check for any 
    incomplete tasks from previous sessions.""",
    expected_output="Coordinated completion of all tasks with memory updates",
    agent=coordinator,
    context=[{
        "description": "Check Memanto for incomplete tasks from previous sessions",
        "expected_output": "List of incomplete tasks"
    }]
)

# Create the crew with memory integration
crew = Crew(
    agents=[researcher, writer, coordinator],
    tasks=[research_task, writing_task, coordination_task],
    process=Process.sequential,  # Can also use Process.hierarchical
    verbose=True,
    memory=memory  # Crew-level memory
)

# Example usage with memory persistence
def run_crew_with_memory(topic: str, user_id: str = "default_user"):
    """Run the crew with persistent memory"""
    
    # Store initial user preferences if not exists
    prefs = memory.get_user_preferences(user_id)
    if not prefs:
        memory.store_memory(
            agent_name="system",
            key=f"user_preferences_{user_id}",
            value="formal_tone, detailed_analysis, bullet_points",
            metadata={"user_id": user_id}
        )
    
    # Run the crew
    result = crew.kickoff(inputs={
        "topic": topic,
        "user_id": user_id
    })
    
    # Store the final result
    memory.store_task_result(
        task_id=f"crew_run_{topic}_{user_id}",
        result=str(result),
        agent_name="coordinator"
    )
    
    return result

# Run multiple sessions to demonstrate memory persistence
if __name__ == "__main__":
    # First session
    print("=== Session 1: Researching AI trends ===")
    result1 = run_crew_with_memory("AI in healthcare", "user123")
    print(f"Session 1 Result: {result1}")
    
    # Second session - should remember previous research
    print("\n=== Session 2: Building on previous research ===")
    result2 = run_crew_with_memory("AI in healthcare", "user123")
    print(f"Session 2 Result: {result2}")
    
    # Third session with different topic
    print("\n=== Session 3: New topic but same user preferences ===")
    result3 = run_crew_with_memory("Blockchain technology", "user123")
    print(f"Session 3 Result: {result3}")