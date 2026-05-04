

"""
Example of CrewAI integration with Memanto's agentic memory system.

This script demonstrates how to use the CrewAI-Memanto integration
to create agents with persistent memory capabilities.
"""

import os
from crewai import Agent, Task, Crew

from src.integrations.crewai import add_memory_tools_to_agent, enhance_crew_with_memory

def main():
    """Run the example CrewAI integration with Memanto."""

    # Get Moorcheh API key from environment variable
    moorcheh_api_key = os.getenv("MOORCHER_API_KEY")
    if not moorcheh_api_key:
        print("Please set the MOORCHER_API_KEY environment variable")
        return

    print("=== CrewAI + Memanto Integration Example ===\n")

    # Example 1: Simple agent with memory tools
    print("Creating a simple agent with memory tools...")

    # Create a personal assistant agent
    assistant = Agent(
        role="Personal Assistant",
        goal="Help the user with their daily tasks and remember important information",
        backstory="An AI assistant that remembers user preferences and context across sessions",
        verbose=True
    )

    # Add memory tools to the agent
    assistant = add_memory_tools_to_agent(
        agent=assistant,
        moorcheh_api_key=moorcheh_api_key,
        agent_id="personal_assistant_example"
    )

    print(f"Agent created with {len(assistant.tools)} memory tools\n")

    # Example 2: Store some user preferences
    print("Storing user preferences in memory...")

    # Store user's favorite color
    store_color_result = assistant.tools[0](
        memory_type="preference",
        title="User's Favorite Color",
        content="The user's favorite color is blue.",
        confidence=0.95,
        tags=["user_preference", "color"]
    )
    print(store_color_result)

    # Store user's drink preference
    store_drink_result = assistant.tools[0](
        memory_type="preference",
        title="User's Drink Preference",
        content="The user prefers tea over coffee.",
        confidence=0.9,
        tags=["user_preference", "drink"]
    )
    print(store_drink_result)

    # Example 3: Search for memories
    print("\nSearching for user preferences...")

    search_result = assistant.tools[2](
        query="color drink",
        limit=5
    )
    print(search_result)

    # Example 4: Create a task that uses memory
    print("\nCreating a task that uses memory...")

    # Create a task to retrieve preferences
    retrieve_task = Task(
        description="Retrieve the user's favorite color and drink preference",
        expected_output="The user's favorite color is blue and they prefer tea",
        agent=assistant
    )

    # Example 5: Create a crew with memory-enhanced agents
    print("\nCreating a crew with memory-enhanced agents...")

    # Create another agent
    planner = Agent(
        role="Task Planner",
        goal="Plan tasks based on user requirements",
        backstory="An AI agent that plans tasks and remembers user preferences"
    )

    # Add memory tools to the planner
    planner = add_memory_tools_to_agent(
        agent=planner,
        moorcheh_api_key=moorcheh_api_key,
        agent_id="task_planner_example"
    )

    # Create a task for the planner
    plan_task = Task(
        description="Plan a day of tasks for the user, considering their preferences",
        expected_output="A list of planned tasks that respect the user's preferences",
        agent=planner,
        context=[retrieve_task]
    )

    # Create a crew
    crew = Crew(
        agents=[assistant, planner],
        tasks=[retrieve_task, plan_task],
        verbose=2
    )

    # Enhance the crew with memory capabilities
    crew = enhance_crew_with_memory(
        crew=crew,
        moorcheh_api_key=moorcheh_api_key,
        agent_configs={
            "Personal Assistant": {"agent_id": "personal_assistant_crew"},
            "Task Planner": {"agent_id": "task_planner_crew"}
        }
    )

    print("\nRunning the crew...\n")
    result = crew.kickoff()

    print("\n=== Example Complete ===")
    print("The CrewAI agents successfully used Memanto's agentic memory system!")

if __name__ == "__main__":
    main()

