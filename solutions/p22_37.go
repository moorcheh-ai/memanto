from crewai import Agent, Task, Crew, Process
from memanto import MemantoClient
import os
from typing import Dict, List, Optional

# Initialize Memanto client
MEMANTO_API_KEY = os.getenv("MEMANTO_API_KEY", "your-api-key")
MEMANTO_ENDPOINT = os.getenv("MEMANTO_ENDPOINT", "https://api.memanto.ai/v1")
memanto = MemantoClient(api_key=MEMANTO_API_KEY, endpoint=MEMANTO_ENDPOINT)

class MemantoMemory:
    """Custom memory class for CrewAI integration with Memanto"""
    
    def __init__(self, session_id: str = "default"):
        self.session_id = session_id
        self.memory_store = {}
        
    def store(self, key: str, value: any, metadata: Optional[Dict] = None):
        """Store a memory item in Memanto"""
        try:
            memory_data = {
                "key": key,
                "value": value,
                "session_id": self.session_id,
                "metadata": metadata or {}
            }
            memanto.store_memory(memory_data)
            self.memory_store[key] = value
            return True
        except Exception as e:
            print(f"Error storing memory: {e}")
            return False
    
    def retrieve(self, key: str) -> Optional[any]:
        """Retrieve a memory item from Memanto"""
        try:
            if key in self.memory_store:
                return self.memory_store[key]
            
            result = memanto.retrieve_memory(key, session_id=self.session_id)
            if result:
                self.memory_store[key] = result["value"]
                return result["value"]
            return None
        except Exception as e:
            print(f"Error retrieving memory: {e}")
            return None
    
    def search(self, query: str, limit: int = 5) -> List[Dict]:
        """Search memories using semantic search"""
        try:
            results = memanto.search_memories(
                query=query,
                session_id=self.session_id,
                limit=limit
            )
            return results
        except Exception as e:
            print(f"Error searching memory: {e}")
            return []
    
    def clear(self):
        """Clear all memories for this session"""
        try:
            memanto.clear_session(self.session_id)
            self.memory_store.clear()
            return True
        except Exception as e:
            print(f"Error clearing memory: {e}")
            return False

# Create agents with Memanto memory
memory = MemantoMemory(session_id="crewai_demo_session")

researcher = Agent(
    role="Research Analyst",
    goal="Conduct thorough research and store findings in long-term memory",
    backstory="Expert researcher with perfect recall using Memanto memory system",
    allow_delegation=True,
    verbose=True,
    memory=memory
)

writer = Agent(
    role="Content Writer",
    goal="Create compelling content based on research and user preferences",
    backstory="Creative writer who remembers user style preferences",
    allow_delegation=True,
    verbose=True,
    memory=memory
)

analyst = Agent(
    role="Data Analyst",
    goal="Analyze trends and patterns from stored memories",
    backstory="Analytical mind that leverages historical data for insights",
    allow_delegation=True,
    verbose=True,
    memory=memory
)

# Define tasks with memory integration
research_task = Task(
    description="Research the latest trends in AI and machine learning for 2024. Store key findings in memory.",
    expected_output="A comprehensive research report with 5 key trends",
    agent=researcher,
    context=[{
        "memory_key": "user_preferences",
        "description": "User's preferred research topics"
    }]
)

content_task = Task(
    description="Write a blog post about AI trends based on research. Remember user's preferred writing style from memory.",
    expected_output="A well-written blog post of 500 words",
    agent=writer,
    context=[{
        "memory_key": "writing_style",
        "description": "User's preferred writing style"
    }]
)

analysis_task = Task(
    description="Analyze the research findings and previous content to identify patterns. Store analysis in memory.",
    expected_output="A detailed analysis report with recommendations",
    agent=analyst,
    context=[{
        "memory_key": "previous_analyses",
        "description": "Historical analysis data"
    }]
)

# Create the crew
crew = Crew(
    agents=[researcher, writer, analyst],
    tasks=[research_task, content_task, analysis_task],
    process=Process.sequential,
    verbose=True,
    memory=memory
)

# Example usage with memory persistence
def run_crew_with_memory():
    """Run the crew with memory persistence"""
    
    # Store initial user preferences
    memory.store("user_preferences", {
        "topics": ["AI", "machine learning", "deep learning"],
        "depth": "comprehensive",
        "format": "bullet points"
    })
    
    memory.store("writing_style", {
        "tone": "professional",
        "length": "medium",
        "audience": "technical"
    })
    
    # Run the crew
    result = crew.kickoff()
    
    # Retrieve and display stored memories
    print("\n=== Stored Memories ===")
    stored_preferences = memory.retrieve("user_preferences")
    print(f"User Preferences: {stored_preferences}")
    
    stored_style = memory.retrieve("writing_style")
    print(f"Writing Style: {stored_style}")
    
    # Search for relevant memories
    print("\n=== Memory Search Results ===")
    search_results = memory.search("AI trends 2024")
    for result in search_results:
        print(f"- {result['key']}: {result['value'][:100]}...")
    
    return result

# Run the crew
if __name__ == "__main__":
    result = run_crew_with_memory()
    print(f"\nFinal Result: {result}")