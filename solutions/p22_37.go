from crewai import Agent, Task, Crew, Process
from memanto import MemantoMemory
import os

# Initialize Memanto memory layer
memanto = MemantoMemory(
    api_key=os.getenv("MEMANTO_API_KEY"),
    namespace="crewai_memanto_demo"
)

# Define agents with Memanto memory
researcher = Agent(
    role="Senior Research Analyst",
    goal="Uncover cutting-edge developments in AI and machine learning",
    backstory="You are an expert research analyst with a knack for finding hidden patterns and insights.",
    allow_delegation=False,
    verbose=True,
    memory=memanto
)

writer = Agent(
    role="Content Writer",
    goal="Craft compelling blog posts about AI advancements",
    backstory="You are a skilled writer who transforms complex research into engaging narratives.",
    allow_delegation=False,
    verbose=True,
    memory=memanto
)

# Define tasks with memory context
research_task = Task(
    description="Research the latest advancements in agentic AI systems. Focus on memory architectures and multi-agent coordination.",
    expected_output="A comprehensive summary of recent breakthroughs in agentic AI memory systems.",
    agent=researcher,
    context_from_memory=True  # Enable Memanto memory context
)

writing_task = Task(
    description="Based on the research findings, write an engaging blog post about the future of agentic AI memory.",
    expected_output="A well-structured blog post of at least 500 words with clear sections and insights.",
    agent=writer,
    context_from_memory=True
)

# Create the crew with Memanto memory integration
crew = Crew(
    agents=[researcher, writer],
    tasks=[research_task, writing_task],
    process=Process.sequential,
    verbose=True,
    memory=memanto,  # Pass Memanto as the crew's memory layer
    memory_config={
        "type": "memanto",
        "config": {
            "namespace": "crewai_memanto_demo",
            "auto_save": True,
            "retrieval_strategy": "semantic"
        }
    }
)

# Store initial user preferences in Memanto
memanto.store(
    key="user_preferences",
    data={
        "focus_area": "agentic AI memory systems",
        "tone": "professional yet accessible",
        "target_audience": "AI researchers and developers"
    },
    metadata={"type": "preferences", "session": "initial"}
)

# Execute the crew
result = crew.kickoff()

# Store the results in Memanto for future sessions
memanto.store(
    key="session_results",
    data={
        "research_summary": result.tasks_output[0].raw,
        "blog_post": result.tasks_output[1].raw,
        "timestamp": "2024-01-15T10:30:00Z"
    },
    metadata={"type": "output", "session": "demo"}
)

# Retrieve and display stored memory
print("\n=== Stored User Preferences ===")
preferences = memanto.retrieve("user_preferences")
print(preferences)

print("\n=== Session Results ===")
session_data = memanto.retrieve("session_results")
print(f"Research Summary: {session_data['research_summary'][:200]}...")
print(f"Blog Post Preview: {session_data['blog_post'][:200]}...")

# Demonstrate memory persistence across sessions
print("\n=== Memory Persistence Check ===")
memory_stats = memanto.get_stats()
print(f"Total stored memories: {memory_stats['total_keys']}")
print(f"Memory namespace: {memory_stats['namespace']}")

# Search for related memories
print("\n=== Semantic Memory Search ===")
search_results = memanto.search("agentic AI memory systems")
for result in search_results:
    print(f"- {result['key']}: {result['data'][:100]}...")