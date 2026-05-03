from crewai import Agent, Task, Crew, Process
from memanto import MemantoMemory
import os

# Initialize Memanto memory layer
memanto = MemantoMemory(
    api_key=os.getenv("MEMANTO_API_KEY"),
    namespace="crewai_memanto_demo"
)

# Define agents with Memanto memory integration
researcher = Agent(
    role="Senior Research Analyst",
    goal="Uncover cutting-edge developments in AI and machine learning",
    backstory="You are an expert analyst with a knack for finding relevant information.",
    memory=memanto,
    verbose=True,
    allow_delegation=False
)

writer = Agent(
    role="Content Writer",
    goal="Craft compelling blog posts about AI trends",
    backstory="You are a skilled writer who transforms complex topics into engaging content.",
    memory=memanto,
    verbose=True,
    allow_delegation=False
)

# Define tasks with memory context
research_task = Task(
    description="Research the latest advancements in AI memory systems. Use Memanto to store and retrieve previous research findings.",
    expected_output="A comprehensive list of recent AI memory system developments with sources.",
    agent=researcher,
    context_from_memory=True
)

write_task = Task(
    description="Write a blog post about AI memory systems based on the research. Remember user preferences from previous interactions stored in Memanto.",
    expected_output="A well-structured blog post in markdown format.",
    agent=writer,
    context_from_memory=True
)

# Create the crew
crew = Crew(
    agents=[researcher, writer],
    tasks=[research_task, write_task],
    process=Process.sequential,
    memory=memanto,
    verbose=True
)

# Execute with memory persistence
result = crew.kickoff()

print("Crew execution completed. Memory stored in Memanto.")
print(result)

# Example of retrieving memory from a different session
print("\n--- Retrieving stored memory ---")
previous_memories = memanto.search("AI memory systems research")
for memory in previous_memories:
    print(f"Memory: {memory['content']} (timestamp: {memory['timestamp']})")