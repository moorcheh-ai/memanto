from crewai import Agent, Task, Crew, Process
from memanto import MemantoClient
import os

# Initialize Memanto client
memanto = MemantoClient(
    api_key=os.getenv("MEMANTO_API_KEY"),
    base_url=os.getenv("MEMANTO_BASE_URL", "http://localhost:8000")
)

# Define agents with Memanto memory integration
class MemantoAgent(Agent):
    def __init__(self, role, goal, backstory, memory_namespace="default"):
        super().__init__(role=role, goal=goal, backstory=backstory)
        self.memory_namespace = memory_namespace
        self.memanto = memanto

    def remember(self, query, limit=5):
        """Retrieve relevant memories from Memanto"""
        results = self.memanto.search(
            namespace=self.memory_namespace,
            query=query,
            limit=limit
        )
        return [r["content"] for r in results]

    def memorize(self, content, metadata=None):
        """Store a memory in Memanto"""
        self.memanto.store(
            namespace=self.memory_namespace,
            content=content,
            metadata=metadata or {}
        )

# Create agents with memory capabilities
researcher = MemantoAgent(
    role="Senior Research Analyst",
    goal="Uncover cutting-edge developments in AI and data science",
    backstory="You work at a leading tech think tank. Your expertise lies in identifying emerging trends.",
    memory_namespace="research_memories"
)

writer = MemantoAgent(
    role="Tech Content Strategist",
    goal="Craft compelling content on tech advancements",
    backstory="You are a renowned content strategist, known for your insightful articles.",
    memory_namespace="writing_memories"
)

# Define tasks with memory integration
research_task = Task(
    description="Research the latest advancements in AI agents and memory systems. Use Memanto to store findings.",
    expected_output="A comprehensive research summary with key findings stored in Memanto.",
    agent=researcher,
    callback=lambda result: researcher.memorize(
        content=f"Research result: {result}",
        metadata={"task": "research", "timestamp": str(datetime.now())}
    )
)

writing_task = Task(
    description="Write an article based on the research findings. Retrieve relevant memories from Memanto.",
    expected_output="A well-structured article that incorporates past research insights.",
    agent=writer,
    callback=lambda result: writer.memorize(
        content=f"Article written: {result[:200]}...",
        metadata={"task": "writing", "timestamp": str(datetime.now())}
    )
)

# Create the crew with memory-enhanced workflow
crew = Crew(
    agents=[researcher, writer],
    tasks=[research_task, writing_task],
    process=Process.sequential,
    verbose=True,
    memory=True,
    memory_config={
        "provider": "memanto",
        "config": {
            "api_key": os.getenv("MEMANTO_API_KEY"),
            "base_url": os.getenv("MEMANTO_BASE_URL", "http://localhost:8000")
        }
    }
)

# Execute the crew with memory persistence
if __name__ == "__main__":
    # Store initial context
    memanto.store(
        namespace="project_context",
        content="User prefers concise, actionable insights with real-world examples.",
        metadata={"type": "preference", "user": "default"}
    )

    # Run the crew
    result = crew.kickoff()

    # Demonstrate memory retrieval across sessions
    print("\n=== Memory Retrieval Demo ===")
    past_research = researcher.remember("AI agents memory systems", limit=3)
    print(f"Retrieved {len(past_research)} relevant memories from past research")

    # Store final results
    memanto.store(
        namespace="project_results",
        content=f"Final crew output: {result}",
        metadata={"crew": "research_writer", "timestamp": str(datetime.now())}
    )

    print(f"\nFinal Result: {result}")