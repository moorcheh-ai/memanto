

"""
Example of using Memanto as the memory store for a CrewAI multi-agent crew.

This example demonstrates:
1. Creating a multi-agent crew with Memanto memory
2. Agents collaborating on a research task
3. Using Memanto's advanced memory features:
   - Vector-based retrieval of past thoughts
   - Memory validation and trust scoring
   - Temporal queries
"""

import os
from datetime import datetime
from typing import List, Optional

from crewai import Agent, Task, Crew
from crewai.memory.unified_memory import Memory
from memanto.integrations.crewai_adapter import MemantoCrewAdapter, MemantoCrewAdapterConfig

# Set up Memanto adapter
def create_memanto_memory() -> Memory:
    """Create a CrewAI Memory instance using Memanto as the storage backend"""
    # Configure Memanto adapter
    config = MemantoCrewAdapterConfig(
        moorcheh_api_key=os.getenv("MOORCHEH_API_KEY", ""),
        default_scope_type="agent",
        default_memory_type="context",
        recency_weight=0.3,
        semantic_weight=0.5,
        importance_weight=0.2
    )

    # Create adapter
    adapter = MemantoCrewAdapter(config)

    # Create and return CrewAI Memory instance
    return Memory(
        storage=adapter,
        llm="gpt-4o-mini",  # Use a capable LLM for memory analysis
        recency_weight=0.3,
        semantic_weight=0.5,
        importance_weight=0.2
    )

# Create agents with Memanto memory
def create_agents() -> List[Agent]:
    """Create a team of agents with Memanto memory"""
    # Researcher agent
    researcher = Agent(
        role="Senior Research Analyst",
        goal="Uncover cutting-edge developments in AI and data science",
        backstory=(
            "You are a seasoned research analyst with a deep understanding of AI trends. "
            "Your expertise lies in identifying emerging technologies and their potential "
            "impact on various industries. You have access to a vast network of information "
            "sources and are known for your ability to synthesize complex information into "
            "actionable insights."
        ),
        memory=True,  # Enable memory
        verbose=True
    )

    # Writer agent
    writer = Agent(
        role="Tech Content Strategist",
        goal="Craft compelling content on technical advancements",
        backstory=(
            "You are a renowned Tech Content Strategist, known for your insightful and "
            "engaging articles on technology and innovation. With a deep understanding of "
            "the tech industry, you transform complex concepts into compelling narratives "
            "that captivate and educate. Your work has been featured in top tech publications."
        ),
        memory=True,  # Enable memory
        verbose=True
    )

    # Editor agent
    editor = Agent(
        role="Chief Editing Officer",
        goal="Ensure the highest quality of content before publication",
        backstory=(
            "You are the Chief Editing Officer with an eagle eye for detail and a passion "
            "for perfection. Your role is to review and refine content, ensuring it meets "
            "the highest standards of clarity, coherence, and grammatical accuracy. You have "
            "a knack for identifying inconsistencies and improving the overall flow of text."
        ),
        memory=True,  # Enable memory
        verbose=True
    )

    return [researcher, writer, editor]

# Create tasks for the agents
def create_tasks() -> List[Task]:
    """Create tasks for the agents to work on"""
    # Research task
    research_task = Task(
        description=(
            "Conduct a comprehensive analysis of the latest advancements in AI in 2026. "
            "Identify key trends, breakthrough technologies, and potential industry impacts. "
            "Your final report should clearly articulate the most significant developments "
            "and their implications for the future of AI."
        ),
        expected_output=(
            "A comprehensive 3-paragraph report on the latest AI advancements. "
            "The report should include a detailed analysis of key trends, "
            "breakthrough technologies, and their potential industry impacts."
        ),
        agent=create_agents()[0],  # Researcher
        async_execution=False
    )

    # Writing task
    writing_task = Task(
        description=(
            "Using the insights from the researcher's report, develop an engaging blog post "
            "that highlights the most significant AI advancements. Your post should be "
            "informative yet accessible, catering to a tech-savvy audience. Make it sound "
            "exciting and relevant to current industry discussions."
        ),
        expected_output=(
            "A 4-paragraph blog post written in a engaging and informative style. "
            "The post should highlight the most significant AI advancements, "
            "making them accessible to a tech-savvy audience."
        ),
        agent=create_agents()[1],  # Writer
        context=[research_task],
        async_execution=False
    )

    # Editing task
    editing_task = Task(
        description=(
            "Review the blog post for clarity, coherence, grammatical accuracy, and "
            "adherence to the expected output format. Ensure the content is engaging, "
            "informative, and maintains a consistent tone throughout. Make any necessary "
            "edits to improve the overall quality of the post."
        ),
        expected_output=(
            "A polished 4-paragraph blog post that is clear, coherent, and grammatically "
            "accurate. The post should be engaging, informative, and maintain a consistent "
            "tone throughout, ready for publication."
        ),
        agent=create_agents()[2],  # Editor
        context=[writing_task],
        async_execution=False
    )

    return [research_task, writing_task, editing_task]

# Create and run the crew
def run_crew() -> None:
    """Create and run the crew with Memanto memory"""
    # Create memory instance
    memory = create_memanto_memory()

    # Create agents
    agents = create_agents()

    # Create tasks
    tasks = create_tasks()

    # Create crew
    crew = Crew(
        agents=agents,
        tasks=tasks,
        memory=memory,  # Use Memanto memory
        verbose=2
    )

    # Execute the crew
    result = crew.kickoff()

    # Print the result
    print("\n\n########################")
    print("## Here is the result ##")
    print("########################\n")
    print(result)

    # Demonstrate memory usage
    print("\n\n########################")
    print("## Memory Demonstration ##")
    print("########################\n")

    # Show recent memories
    print("Recent memories from the crew:")
    recent_memories = memory.recall("*", limit=5)
    for i, (record, score) in enumerate(recent_memories):
        print(f"\nMemory {i+1} (Score: {score:.2f}):")
        print(f"Content: {record.content[:100]}...")
        print(f"Scope: {record.scope}")
        print(f"Categories: {record.categories}")
        print(f"Importance: {record.importance}")
        print(f"Created: {record.created_at}")

    # Show how to use temporal queries
    print("\n\nTemporal query demonstration:")
    print("Memories created in the last 5 minutes:")
    five_minutes_ago = datetime.utcnow().isoformat()
    temporal_memories = memory.recall(
        "*",
        created_after=five_minutes_ago,
        limit=3
    )
    for i, (record, score) in enumerate(temporal_memories):
        print(f"\nMemory {i+1} (Score: {score:.2f}):")
        print(f"Content: {record.content[:100]}...")
        print(f"Created: {record.created_at}")

if __name__ == "__main__":
    run_crew()

