from crewai import Agent, Task, Crew, Process
from memanto import MemantoMemory
import os

# Initialize Memanto memory layer
memanto = MemantoMemory(
    api_key=os.getenv("MEMANTO_API_KEY"),
    namespace="crewai_memanto_demo"
)

# Define agents with Memanto memory integration
class MemantoAgent(Agent):
    def __init__(self, role, goal, backstory, allow_delegation=False, verbose=True):
        super().__init__(
            role=role,
            goal=goal,
            backstory=backstory,
            allow_delegation=allow_delegation,
            verbose=verbose,
            memory=memanto
        )
    
    def remember(self, key, value):
        """Store a memory in Memanto"""
        memanto.store(key, value, namespace=f"agent_{self.role}")
    
    def recall(self, key):
        """Retrieve a memory from Memanto"""
        return memanto.retrieve(key, namespace=f"agent_{self.role}")
    
    def search_memories(self, query):
        """Search across all memories"""
        return memanto.search(query, namespace=f"agent_{self.role}")

# Create agents with persistent memory
researcher = MemantoAgent(
    role="Senior Research Analyst",
    goal="Uncover cutting-edge developments in AI and machine learning",
    backstory="You are a seasoned researcher with expertise in AI trends and technologies."
)

writer = MemantoAgent(
    role="Content Writer",
    goal="Create compelling, well-researched content based on research findings",
    backstory="You are a skilled writer who transforms complex research into engaging content."
)

# Define tasks with memory context
research_task = Task(
    description="Research the latest advancements in AI memory systems. Use Memanto to store findings.",
    expected_output="A comprehensive summary of AI memory system advancements.",
    agent=researcher,
    context=[memanto]
)

write_task = Task(
    description="Write a blog post about AI memory systems based on research. Remember user preferences from previous sessions.",
    expected_output="A well-written blog post in markdown format.",
    agent=writer,
    context=[memanto]
)

# Create the crew with Memanto memory
crew = Crew(
    agents=[researcher, writer],
    tasks=[research_task, write_task],
    process=Process.sequential,
    memory=memanto,
    verbose=True
)

# Store initial user preferences
memanto.store("user_preferences", {
    "tone": "professional",
    "length": "medium",
    "focus_areas": ["memory systems", "agent architectures"]
}, namespace="global")

# Execute the crew
result = crew.kickoff()

# Demonstrate memory persistence across sessions
print("Previous session memories:")
previous_memories = memanto.search("AI memory systems", namespace="agent_Senior Research Analyst")
for memory in previous_memories:
    print(f"- {memory['content']}")

# Store new memories for future sessions
researcher.remember("last_research_topic", "AI memory systems")
writer.remember("last_written_topic", "AI memory systems blog post")

print("\nMemories stored for future sessions!")
print(f"Result: {result}")