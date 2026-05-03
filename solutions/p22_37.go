from crewai import Agent, Task, Crew, Process
from memanto import MemantoMemory
import os

# Initialize Memanto memory layer
memanto = MemantoMemory(
    api_key=os.getenv("MEMANTO_API_KEY"),
    namespace="crewai_memanto_integration"
)

# Define agents with Memanto memory
researcher = Agent(
    role="Senior Research Analyst",
    goal="Uncover cutting-edge developments in AI and data science",
    backstory="You are an expert analyst with a knack for finding hidden patterns",
    memory=memanto,
    verbose=True,
    allow_delegation=False
)

writer = Agent(
    role="Content Writer",
    goal="Craft compelling blog posts about AI trends",
    backstory="You are a skilled writer who transforms complex topics into engaging stories",
    memory=memanto,
    verbose=True,
    allow_delegation=False
)

# Define tasks with memory context
research_task = Task(
    description="Research the latest advancements in agentic memory systems. Focus on Memanto and similar frameworks.",
    expected_output="A comprehensive summary of recent developments",
    agent=researcher,
    context_from_memory=True
)

write_task = Task(
    description="Write a blog post about the research findings. Include user preferences from memory.",
    expected_output="A polished blog post in markdown format",
    agent=writer,
    context_from_memory=True
)

# Create the crew with Memanto memory integration
crew = Crew(
    agents=[researcher, writer],
    tasks=[research_task, write_task],
    process=Process.sequential,
    memory=memanto,
    verbose=True
)

# Store initial user preferences in Memanto
memanto.store(
    key="user_preferences",
    data={
        "writing_style": "professional",
        "tone": "enthusiastic",
        "length": "medium",
        "topics_of_interest": ["AI memory", "agentic systems", "open source"]
    }
)

# Store previous session context
memanto.store(
    key="previous_session",
    data={
        "completed_tasks": ["initial_research"],
        "user_feedback": "Great work, but add more technical depth",
        "last_topic": "agentic memory"
    }
)

# Execute the crew with memory recall
result = crew.kickoff()

# Retrieve and display memory context
print("Retrieved Memory Context:")
print(memanto.retrieve("user_preferences"))
print(memanto.retrieve("previous_session"))

# Update memory with new learnings
memanto.store(
    key="session_2_completed",
    data={
        "tasks_completed": ["research", "writing"],
        "output_summary": result,
        "timestamp": "2024-01-15"
    }
)

# Search memory for relevant context
search_results = memanto.search("agentic memory systems")
print(f"Memory search results: {search_results}")

# Export final result
print("\nFinal Crew Output:")
print(result)