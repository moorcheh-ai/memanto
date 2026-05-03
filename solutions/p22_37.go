from crewai import Agent, Task, Crew, Process
from memanto import MemantoClient
import os
from typing import Dict, List, Optional
import json

# Initialize Memanto client
MEMANTO_API_KEY = os.getenv("MEMANTO_API_KEY", "your-api-key")
MEMANTO_ENDPOINT = os.getenv("MEMANTO_ENDPOINT", "https://api.memanto.ai/v1")

memanto_client = MemantoClient(
    api_key=MEMANTO_API_KEY,
    endpoint=MEMANTO_ENDPOINT
)

class MemantoMemory:
    """Custom memory class for CrewAI that uses Memanto for persistent storage."""
    
    def __init__(self, session_id: str = "default"):
        self.session_id = session_id
        self.memory_store = {}
        
    def store(self, key: str, value: any, metadata: Optional[Dict] = None):
        """Store a memory in Memanto."""
        memory_data = {
            "key": key,
            "value": value,
            "metadata": metadata or {},
            "session_id": self.session_id
        }
        
        try:
            memanto_client.store_memory(
                namespace=f"crewai_{self.session_id}",
                key=key,
                data=memory_data
            )
            self.memory_store[key] = value
        except Exception as e:
            print(f"Error storing memory: {e}")
            
    def retrieve(self, key: str) -> Optional[any]:
        """Retrieve a memory from Memanto."""
        if key in self.memory_store:
            return self.memory_store[key]
            
        try:
            memory = memanto_client.retrieve_memory(
                namespace=f"crewai_{self.session_id}",
                key=key
            )
            if memory:
                self.memory_store[key] = memory["value"]
                return memory["value"]
        except Exception as e:
            print(f"Error retrieving memory: {e}")
        return None
        
    def search(self, query: str, limit: int = 10) -> List[Dict]:
        """Search memories using semantic search."""
        try:
            results = memanto_client.search_memories(
                namespace=f"crewai_{self.session_id}",
                query=query,
                limit=limit
            )
            return results
        except Exception as e:
            print(f"Error searching memories: {e}")
            return []
            
    def clear(self):
        """Clear all memories for this session."""
        try:
            memanto_client.clear_namespace(f"crewai_{self.session_id}")
            self.memory_store.clear()
        except Exception as e:
            print(f"Error clearing memories: {e}")

# Create agents with Memanto memory
def create_research_agent(memory: MemantoMemory) -> Agent:
    return Agent(
        role="Senior Research Analyst",
        goal="Uncover cutting-edge developments in AI and data science",
        backstory="""You are a senior research analyst at a leading tech think tank.
        You have access to Memanto memory to remember past research findings and user preferences.""",
        allow_delegation=False,
        verbose=True,
        memory=memory
    )

def create_writer_agent(memory: MemantoMemory) -> Agent:
    return Agent(
        role="Content Writer",
        goal="Craft compelling content based on research findings",
        backstory="""You are a content writer who creates engaging articles.
        You use Memanto memory to maintain consistent style and remember user feedback.""",
        allow_delegation=False,
        verbose=True,
        memory=memory
    )

def create_summarizer_agent(memory: MemantoMemory) -> Agent:
    return Agent(
        role="Executive Summarizer",
        goal="Create concise summaries of complex information",
        backstory="""You are an executive summarizer who distills complex information.
        Memanto helps you remember previous summaries and maintain consistency.""",
        allow_delegation=False,
        verbose=True,
        memory=memory
    )

# Define tasks with memory integration
def create_research_task(agent: Agent, topic: str, memory: MemantoMemory) -> Task:
    return Task(
        description=f"""Research the latest developments in {topic}.
        Check Memanto memory for any previous research on this topic to avoid duplication.
        Store your findings in Memanto for future reference.""",
        expected_output=f"A comprehensive research report on {topic}",
        agent=agent,
        context=[{
            "memory_key": f"research_{topic}",
            "memory_value": memory.retrieve(f"research_{topic}")
        }]
    )

def create_writing_task(agent: Agent, research: str, memory: MemantoMemory) -> Task:
    return Task(
        description=f"""Write an engaging article based on this research: {research}
        Check Memanto memory for user preferences and writing style guidelines.
        Store the final article in Memanto for future reference.""",
        expected_output="A well-written article based on the research",
        agent=agent,
        context=[{
            "memory_key": "writing_style",
            "memory_value": memory.retrieve("writing_style")
        }]
    )

def create_summary_task(agent: Agent, article: str, memory: MemantoMemory) -> Task:
    return Task(
        description=f"""Create an executive summary of this article: {article}
        Check Memanto memory for previous summaries to maintain consistency.
        Store the summary in Memanto for future reference.""",
        expected_output="A concise executive summary",
        agent=agent,
        context=[{
            "memory_key": "summary_history",
            "memory_value": memory.retrieve("summary_history")
        }]
    )

# Main execution function
def run_memanto_crew(topic: str, user_preferences: Optional[Dict] = None):
    """Run a CrewAI crew with Memanto memory integration."""
    
    # Initialize Memanto memory
    memory = MemantoMemory(session_id=f"crew_session_{topic}")
    
    # Store user preferences if provided
    if user_preferences:
        memory.store("user_preferences", user_preferences)
        memory.store("writing_style", user_preferences.get("writing_style", "professional"))
    
    # Create agents
    researcher = create_research_agent(memory)
    writer = create_writer_agent(memory)
    summarizer = create_summarizer_agent(memory)
    
    # Create tasks
    research_task = create_research_task(researcher, topic, memory)
    writing_task = create_writing_task(writer, "research_results", memory)
    summary_task = create_summary_task(summarizer, "article_content", memory)
    
    # Create crew
    crew = Crew(
        agents=[researcher, writer, summarizer],
        tasks=[research_task, writing_task, summary_task],
        process=Process.sequential,
        verbose=True,
        memory=memory
    )
    
    # Execute crew
    result = crew.kickoff()
    
    # Store final results in Memanto
    memory.store(f"final_result_{topic}", result)
    
    return result

# Example usage with user preferences
if __name__ == "__main__":
    # Example user preferences
    user_prefs = {
        "writing_style": "conversational",
        "preferred_topics": ["AI", "blockchain", "quantum computing"],
        "summary_length": "short",
        "language": "english"
    }
    
    # Run the crew
    result = run_memanto_crew(
        topic="AI-powered autonomous agents",
        user_preferences=user_prefs
    )
    
    print(f"Crew execution result: {result}")
    
    # Demonstrate memory persistence
    memory = MemantoMemory(session_id="crew_session_AI-powered autonomous agents")
    
    # Retrieve stored memories
    stored_preferences = memory.retrieve("user_preferences")
    print(f"Stored user preferences: {stored_preferences}")
    
    # Search for related memories
    search_results = memory.search("AI agents research")
    print(f"Search results: {search_results}")