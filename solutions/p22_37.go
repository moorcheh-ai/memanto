from crewai import Agent, Task, Crew, Process
from memanto import MemantoClient
import os
from typing import Dict, List, Optional
import json
from datetime import datetime

# Initialize Memanto client
MEMANTO_API_KEY = os.getenv("MEMANTO_API_KEY", "your-memanto-api-key")
MEMANTO_ENDPOINT = os.getenv("MEMANTO_ENDPOINT", "https://api.memanto.ai/v1")
memanto = MemantoClient(api_key=MEMANTO_API_KEY, endpoint=MEMANTO_ENDPOINT)

class MemantoMemory:
    """Custom memory class for CrewAI integration with Memanto"""
    
    def __init__(self, namespace: str = "crewai_memory"):
        self.namespace = namespace
        self.session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
    def store(self, key: str, value: Dict, metadata: Optional[Dict] = None):
        """Store memory in Memanto"""
        memory_entry = {
            "key": key,
            "value": value,
            "metadata": metadata or {},
            "session_id": self.session_id,
            "timestamp": datetime.now().isoformat()
        }
        memanto.store(
            namespace=self.namespace,
            data=memory_entry
        )
        
    def retrieve(self, query: str, limit: int = 5) -> List[Dict]:
        """Retrieve memories from Memanto"""
        results = memanto.search(
            namespace=self.namespace,
            query=query,
            limit=limit
        )
        return results
    
    def get_context(self, task_description: str) -> str:
        """Get relevant context for a task"""
        memories = self.retrieve(task_description)
        if not memories:
            return ""
        
        context = "Previous relevant memories:\n"
        for mem in memories:
            context += f"- {mem.get('value', {}).get('summary', '')}\n"
        return context

# Initialize memory system
memory_system = MemantoMemory(namespace="crewai_demo")

# Define agents with Memanto memory integration
class MemantoAgent(Agent):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.memory = memory_system
        
    def execute_task(self, task, context=None):
        # Get relevant memories before execution
        memory_context = self.memory.get_context(task.description)
        
        # Enhance task with memory context
        enhanced_task = task
        if memory_context:
            enhanced_task.description = f"{task.description}\n\nContext from memory:\n{memory_context}"
        
        # Execute the task
        result = super().execute_task(enhanced_task, context)
        
        # Store the result in memory
        self.memory.store(
            key=f"task_{task.id}",
            value={
                "task": task.description[:100],
                "result": result[:200],
                "agent": self.role
            },
            metadata={
                "agent_role": self.role,
                "task_id": task.id
            }
        )
        
        return result

# Create agents with memory
researcher = MemantoAgent(
    role="Senior Research Analyst",
    goal="Uncover cutting-edge developments in AI and data science",
    backstory="You're a seasoned researcher with expertise in AI trends",
    allow_delegation=False,
    verbose=True,
    memory=memory_system
)

writer = MemantoAgent(
    role="Content Writer",
    goal="Craft compelling blog posts about AI advancements",
    backstory="You're a skilled writer who transforms complex topics into engaging content",
    allow_delegation=False,
    verbose=True,
    memory=memory_system
)

analyst = MemantoAgent(
    role="Data Analyst",
    goal="Analyze trends and provide data-driven insights",
    backstory="You're a data analyst who finds patterns in complex datasets",
    allow_delegation=False,
    verbose=True,
    memory=memory_system
)

# Define tasks with memory integration
research_task = Task(
    description="Research the latest advancements in AI memory systems and their applications",
    expected_output="A comprehensive report on AI memory technologies",
    agent=researcher
)

analysis_task = Task(
    description="Analyze the research findings and identify key trends",
    expected_output="Data-driven analysis of AI memory trends",
    agent=analyst
)

writing_task = Task(
    description="Create a blog post about AI memory systems based on research and analysis",
    expected_output="A compelling blog post about AI memory systems",
    agent=writer
)

# Create the crew with memory integration
crew = Crew(
    agents=[researcher, writer, analyst],
    tasks=[research_task, analysis_task, writing_task],
    process=Process.sequential,
    verbose=True,
    memory=memory_system,
    share_crew=True
)

# Function to demonstrate memory persistence across sessions
def demonstrate_memory_persistence():
    """Show how Memanto maintains memory across different sessions"""
    
    print("\n=== Session 1: Initial Research ===")
    result1 = crew.kickoff()
    print(f"Session 1 Result: {result1[:100]}...")
    
    # Store user preferences
    memory_system.store(
        key="user_preferences",
        value={
            "preferred_topics": ["AI memory", "agent systems"],
            "writing_style": "technical but accessible",
            "audience": "tech professionals"
        },
        metadata={"type": "preferences"}
    )
    
    print("\n=== Session 2: Follow-up with Memory ===")
    # New tasks that leverage previous memories
    follow_up_task = Task(
        description="Based on previous research, explore how AI memory systems can be applied to customer service",
        expected_output="A report on AI memory applications in customer service",
        agent=researcher
    )
    
    # Create new crew with same memory
    follow_up_crew = Crew(
        agents=[researcher, writer],
        tasks=[follow_up_task],
        process=Process.sequential,
        verbose=True,
        memory=memory_system
    )
    
    result2 = follow_up_crew.kickoff()
    print(f"Session 2 Result: {result2[:100]}...")
    
    # Demonstrate memory retrieval
    print("\n=== Memory Retrieval Demo ===")
    memories = memory_system.retrieve("AI memory systems")
    print(f"Found {len(memories)} relevant memories")
    for mem in memories[:3]:
        print(f"- {mem.get('value', {}).get('summary', 'No summary')}")

# Run the demonstration
if __name__ == "__main__":
    demonstrate_memory_persistence()
    
    # Example of querying specific memories
    print("\n=== Querying User Preferences ===")
    preferences = memory_system.retrieve("user preferences")
    if preferences:
        print(f"User preferences: {json.dumps(preferences[0]['value'], indent=2)}")
    
    print("\n✅ Memanto + CrewAI integration complete!")
    print(f"Wallet: TU8NBT5iGyMNkLwWmWmgy7tFMbKnafLHcu")