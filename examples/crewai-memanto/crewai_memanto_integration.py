import os
import subprocess
from textwrap import dedent
from crewai import Agent, Task, Crew, Process
from crewai.tools import tool

# -----------------------------------------------------------------------------
# Memanto Custom Tools for CrewAI
# -----------------------------------------------------------------------------
# Memanto's CLI acts as a serverless semantic memory database.
# We wrap the core primitives (remember, recall, answer) into CrewAI tools.

@tool("Memanto Remember Tool")
def memanto_remember(text: str, memory_type: str = "fact") -> str:
    """
    Stores a new memory into the agent's semantic database using Memanto.
    Use this tool whenever you discover an important fact, user preference, or 
    outcome that needs to be remembered for future tasks.
    
    Args:
        text (str): The information to remember.
        memory_type (str): The category of the memory (e.g., 'fact', 'preference', 'goal', 'decision'). Default is 'fact'.
    """
    try:
        # Run: memanto remember "text" --type <type>
        result = subprocess.run(
            ["memanto", "remember", text, "--type", memory_type],
            capture_output=True,
            text=True,
            check=True
        )
        return f"Successfully stored memory in Memanto: {text} (Type: {memory_type})"
    except subprocess.CalledProcessError as e:
        return f"Failed to store memory. Error: {e.stderr}"


@tool("Memanto Recall Tool")
def memanto_recall(query: str) -> str:
    """
    Recalls exactly relevant context from the agent's semantic database using Memanto.
    Use this tool to fetch prior research, user preferences, or past decisions before taking action.
    
    Args:
        query (str): What you are trying to remember or find out.
    """
    try:
        # Run: memanto recall "query"
        result = subprocess.run(
            ["memanto", "recall", query],
            capture_output=True,
            text=True,
            check=True
        )
        return f"Memanto recalled the following context:\n{result.stdout}"
    except subprocess.CalledProcessError as e:
        return f"Failed to recall memory. Error: {e.stderr}"


@tool("Memanto Answer Tool")
def memanto_answer(query: str) -> str:
    """
    Generates a grounded RAG answer based on the agent's past memories using Memanto.
    Unlike 'recall' which just fetches raw facts, 'answer' synthesizes a coherent response.
    
    Args:
        query (str): The question you need answered based on past memory.
    """
    try:
        # Run: memanto answer "query"
        result = subprocess.run(
            ["memanto", "answer", query],
            capture_output=True,
            text=True,
            check=True
        )
        return f"Memanto Answer:\n{result.stdout}"
    except subprocess.CalledProcessError as e:
        return f"Failed to generate answer. Error: {e.stderr}"


# -----------------------------------------------------------------------------
# Scenario: Cross-Session/Cross-Agent Memory
# -----------------------------------------------------------------------------
# Agent 1 (Researcher) runs and saves its findings into Memanto.
# Agent 2 (Writer) runs later and pulls those findings to draft a report.

def run_crewai_memanto_demo():
    print("🚀 Initializing CrewAI + Memanto Agentic Memory Demo...\n")
    
    # Optional: ensure an agent session is active in memanto
    # subprocess.run(["memanto", "agent", "create", "crewai-demo-agent"], capture_output=True)

    # 1. Define the Research Agent (Writer to Memory)
    researcher = Agent(
        role="Senior Data Researcher",
        goal="Discover and securely store critical project parameters and technical constraints.",
        backstory=dedent("""
            You are a meticulous researcher. Your job is to find important facts and
            IMMEDIATELY store them in the Memanto database so the rest of the team can access them later.
        """),
        verbose=True,
        allow_delegation=False,
        tools=[memanto_remember]
    )

    # 2. Define the Writer Agent (Reader from Memory)
    writer = Agent(
        role="Technical Documentation Writer",
        goal="Draft a project brief by strictly recalling context from the Memanto database.",
        backstory=dedent("""
            You are a technical writer who relies entirely on the team's shared memory.
            Before writing anything, you MUST query the Memanto database using your recall tool
            to fetch the technical constraints discovered by the researcher.
        """),
        verbose=True,
        allow_delegation=False,
        tools=[memanto_recall, memanto_answer]
    )

    # 3. Task for Researcher
    research_task = Task(
        description=dedent("""
            The client just emailed us the following constraint: 
            'The new application MUST be built using FastAPI and Vue.js, and must deploy to AWS.'
            
            Use your Memanto Remember Tool to store this fact as an 'instruction' or 'fact'.
        """),
        expected_output="Confirmation that the fact was successfully stored in Memanto.",
        agent=researcher
    )

    # 4. Task for Writer
    writing_task = Task(
        description=dedent("""
            Write a 2-paragraph project kickoff brief. 
            First, use the Memanto Recall Tool to find out what tech stack and deployment platform the client requires.
            If you aren't sure, use the Memanto Answer Tool to ask 'What tech stack are we using?'.
            Then, draft the brief based ONLY on those memories.
        """),
        expected_output="A 2-paragraph kickoff brief referencing the correct tech stack.",
        agent=writer
    )

    # 5. Assemble the Crew
    crew = Crew(
        agents=[researcher, writer],
        tasks=[research_task, writing_task],
        process=Process.sequential
    )

    # 6. Kickoff!
    print("Starting the Crew. Watch as Memanto persists state between agents...\n")
    result = crew.kickoff()

    print("\n==============================================")
    print("✅ Final Output Generated from Memanto Context:")
    print("==============================================")
    print(result)

if __name__ == "__main__":
    # Note: Requires `pip install crewai memanto` and a valid Moorcheh API key configured.
    run_crewai_memanto_demo()
