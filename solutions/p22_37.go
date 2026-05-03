from crewai import Agent, Task, Crew, Process
from memanto import MemantoClient
import os
from typing import Dict, List, Optional
import json
from datetime import datetime

class MemantoMemory:
    """Memanto-based memory layer for CrewAI agents"""
    
    def __init__(self, api_key: str = None, base_url: str = "http://localhost:8000"):
        self.client = MemantoClient(api_key=api_key or os.getenv("MEMANTO_API_KEY"), base_url=base_url)
        self.session_id = f"crew_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
    def store_memory(self, agent_name: str, key: str, value: any, metadata: Dict = None):
        """Store a memory with context"""
        memory = {
            "agent": agent_name,
            "key": key,
            "value": value,
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "metadata": metadata or {}
        }
        return self.client.store(memory)
    
    def retrieve_memory(self, agent_name: str, key: str) -> Optional[any]:
        """Retrieve specific memory"""
        results = self.client.query(
            query=f"agent:{agent_name} key:{key}",
            limit=1
        )
        return results[0]["value"] if results else None
    
    def search_memories(self, query: str, agent_name: str = None, limit: int = 10) -> List[Dict]:
        """Search across all memories"""
        search_query = query
        if agent_name:
            search_query = f"agent:{agent_name} {query}"
        return self.client.query(query=search_query, limit=limit)
    
    def get_agent_context(self, agent_name: str) -> Dict:
        """Get all memories for a specific agent"""
        memories = self.search_memories(query="", agent_name=agent_name, limit=100)
        context = {}
        for mem in memories:
            context[mem["key"]] = mem["value"]
        return context
    
    def update_preferences(self, user_id: str, preferences: Dict):
        """Store user preferences"""
        self.store_memory(
            agent_name="user_preferences",
            key=f"user_{user_id}",
            value=preferences,
            metadata={"type": "preferences", "user_id": user_id}
        )
    
    def get_user_preferences(self, user_id: str) -> Optional[Dict]:
        """Retrieve user preferences"""
        return self.retrieve_memory("user_preferences", f"user_{user_id}")

class ResearchAgent:
    """Agent specialized in research with Memanto memory"""
    
    def __init__(self, memory: MemantoMemory):
        self.memory = memory
        self.agent = Agent(
            role='Senior Research Analyst',
            goal='Uncover cutting-edge developments in AI and data science',
            backstory="""You are a senior research analyst at a leading tech think tank.
            Your expertise lies in identifying emerging trends and technologies.
            You have a photographic memory for research findings.""",
            allow_delegation=True,
            verbose=True,
            memory_provider=self
        )
    
    def remember(self, key: str, value: any):
        """Store research findings"""
        self.memory.store_memory("research_agent", key, value)
    
    def recall(self, key: str) -> Optional[any]:
        """Retrieve past research"""
        return self.memory.retrieve_memory("research_agent", key)
    
    def search_research(self, topic: str) -> List[Dict]:
        """Search through past research"""
        return self.memory.search_memories(topic, agent_name="research_agent")

class WriterAgent:
    """Agent specialized in content writing with Memanto memory"""
    
    def __init__(self, memory: MemantoMemory):
        self.memory = memory
        self.agent = Agent(
            role='Content Writer',
            goal='Craft compelling content based on research findings',
            backstory="""You are a renowned content writer known for your ability to 
            translate complex technical concepts into engaging narratives.
            You remember every piece of content you've ever written.""",
            allow_delegation=True,
            verbose=True,
            memory_provider=self
        )
    
    def remember_writing_style(self, style: Dict):
        """Store writing style preferences"""
        self.memory.store_memory("writer_agent", "writing_style", style)
    
    def get_writing_style(self) -> Optional[Dict]:
        """Retrieve writing style"""
        return self.memory.retrieve_memory("writer_agent", "writing_style")
    
    def store_draft(self, topic: str, content: str):
        """Store a draft for future reference"""
        self.memory.store_memory(
            "writer_agent", 
            f"draft_{topic.lower().replace(' ', '_')}", 
            content,
            metadata={"type": "draft", "topic": topic}
        )

class UserPreferenceAgent:
    """Agent that manages user preferences with Memanto"""
    
    def __init__(self, memory: MemantoMemory):
        self.memory = memory
        self.agent = Agent(
            role='User Preference Manager',
            goal='Maintain and utilize user preferences for personalized experiences',
            backstory="""You are an expert in user experience and personalization.
            You never forget a user's preferences and use them to enhance every interaction.""",
            allow_delegation=True,
            verbose=True,
            memory_provider=self
        )
    
    def set_preference(self, user_id: str, key: str, value: any):
        """Set a user preference"""
        preferences = self.memory.get_user_preferences(user_id) or {}
        preferences[key] = value
        self.memory.update_preferences(user_id, preferences)
    
    def get_preference(self, user_id: str, key: str) -> Optional[any]:
        """Get a specific user preference"""
        preferences = self.memory.get_user_preferences(user_id)
        return preferences.get(key) if preferences else None
    
    def get_all_preferences(self, user_id: str) -> Dict:
        """Get all preferences for a user"""
        return self.memory.get_user_preferences(user_id) or {}

class MemantoCrew:
    """Main Crew that orchestrates agents with Memanto memory"""
    
    def __init__(self, memanto_api_key: str = None):
        self.memory = MemantoMemory(api_key=memanto_api_key)
        
        # Initialize agents with shared memory
        self.research_agent = ResearchAgent(self.memory)
        self.writer_agent = WriterAgent(self.memory)
        self.user_pref_agent = UserPreferenceAgent(self.memory)
        
        # Create tasks
        self.tasks = []
        
    def create_research_task(self, topic: str, user_id: str = None) -> Task:
        """Create a research task with memory context"""
        
        # Check if we have previous research on this topic
        previous_research = self.research_agent.search_research(topic)
        context = ""
        if previous_research:
            context = f"Previous research found: {json.dumps(previous_research[:3])}"
        
        # Check user preferences
        preferences = {}
        if user_id:
            preferences = self.user_pref_agent.get_all_preferences(user_id)
        
        task = Task(
            description=f"""Research the latest developments in {topic}.
            
            Context from previous sessions: {context}
            User preferences: {json.dumps(preferences)}
            
            Store all findings using the memory system for future reference.
            Focus on: {preferences.get('research_focus', 'general trends')}
            """,
            expected_output=f"A comprehensive research report on {topic}",
            agent=self.research_agent.agent
        )
        return task
    
    def create_writing_task(self, topic: str, style: str = "professional") -> Task:
        """Create a writing task with memory of writing style"""
        
        # Retrieve writing style if previously stored
        writing_style = self.writer_agent.get_writing_style()
        style_context = ""
        if writing_style:
            style_context = f"Previous writing style: {json.dumps(writing_style)}"
        
        task = Task(
            description=f"""Write a compelling article about {topic} in {style} style.
            
            {style_context}
            
            Use the research findings stored in memory.
            Store the final draft in memory for future reference.
            """,
            expected_output=f"A well-written article about {topic}",
            agent=self.writer_agent.agent
        )
        return task
    
    def create_preference_task(self, user_id: str, preferences: Dict) -> Task:
        """Create a task to update user preferences"""
        
        task = Task(
            description=f"""Update user preferences for user {user_id}.
            New preferences: {json.dumps(preferences)}
            
            Store these preferences permanently using the memory system.
            Previous preferences: {json.dumps(self.user_pref_agent.get_all_preferences(user_id))}
            """,
            expected_output="User preferences updated successfully",
            agent=self.user_pref_agent.agent
        )
        return task
    
    def run_workflow(self, topic: str, user_id: str = None, preferences: Dict = None):
        """Run a complete workflow with memory persistence"""
        
        print(f"Starting workflow for topic: {topic}")
        print(f"Session ID: {self.memory.session_id}")
        
        # Step 1: Update preferences if provided
        if preferences and user_id:
            pref_task = self.create_preference_task(user_id, preferences)
            pref_crew = Crew(
                agents=[self.user_pref_agent.agent],
                tasks=[pref_task],
                process=Process.sequential,
                verbose=True
            )
            pref_result = pref_crew.kickoff()
            print(f"Preferences updated: {pref_result}")
        
        # Step 2: Research
        research_task = self.create_research_task(topic, user_id)
        research_crew = Crew(
            agents=[self.research_agent.agent],
            tasks=[research_task],
            process=Process.sequential,
            verbose=True
        )
        research_result = research_crew.kickoff()
        print(f"Research completed: {research_result}")
        
        # Store research results in memory
        self.research_agent.remember(f"research_{topic.lower().replace(' ', '_')}", research_result)
        
        # Step 3: Write content
        writing_task = self.create_writing_task(topic)
        writing_crew = Crew(
            agents=[self.writer_agent.agent],
            tasks=[writing_task],
            process=Process.sequential,
            verbose=True
        )
        writing_result = writing_crew.kickoff()
        print(f"Writing completed: {writing_result}")
        
        # Store the final article in memory
        self.writer_agent.store_draft(topic, writing_result)
        
        return {
            "session_id": self.memory.session_id,
            "research": research_result,
            "article": writing_result,
            "memory_snapshot": self.memory.get_agent_context("research_agent")
        }
    
    def continue_workflow(self, topic: str, user_id: str = None):
        """Continue a workflow using previous memory"""
        print(f"Continuing workflow for topic: {topic}")
        
        # Retrieve previous context
        previous_research = self.research_agent.search_research(topic)
        print(f"Found {len(previous_research)} previous research entries")
        
        # Run with memory context
        return self.run_workflow(topic, user_id)

def main():
    """Example usage of Memanto-powered CrewAI"""
    
    # Initialize the crew with Memanto memory
    crew = MemantoCrew(memanto_api_key=os.getenv("MEMANTO_API_KEY"))
    
    # First session: Set preferences and run workflow
    print("=" * 50)
    print("SESSION 1: Initial Setup")
    print("=" * 50)
    
    result1 = crew.run_workflow(
        topic="Quantum Computing Breakthroughs",
        user_id="user_123",
        preferences={
            "research_focus": "practical applications",
            "writing_style": "educational",
            "content_length": "medium"
        }
    )
    
    print(f"\nSession 1 Results:")
    print(f"Session ID: {result1['session_id']}")
    
    # Second session: Continue with memory
    print("\n" + "=" * 50)
    print("SESSION 2: Continuing with Memory")
    print("=" * 50)
    
    result2 = crew.continue_workflow(
        topic="Quantum Computing Breakthroughs",
        user_id="user_123"
    )
    
    print(f"\nSession 2 Results:")
    print(f"Session ID: {result2['session_id']}")
    
    # Demonstrate memory persistence
    print("\n" + "=" * 50)
    print("MEMORY DEMONSTRATION")
    print("=" * 50)
    
    # Retrieve stored preferences
    preferences = crew.user_pref_agent.get_all_preferences("user_123")
    print(f"Stored preferences: {json.dumps(preferences, indent=2)}")
    
    # Search across all memories
    memories = crew.memory.search_memories("quantum computing")
    print(f"\nFound {len(memories)} memories related to quantum computing")
    
    # Get complete agent context
    research_context = crew.memory.get_agent_context("research_agent")
    print(f"\nResearch agent has {len(research_context)} stored memories")

if __name__ == "__main__":
    main()