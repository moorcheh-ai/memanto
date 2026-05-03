# CrewAI + Memanto Integration

Give your CrewAI agents persistent, searchable memory across sessions using Memanto.

## The Problem

CrewAI agents suffer from "long-term amnesia" - each run starts fresh with no memory of previous sessions, user preferences, or past research findings.

## The Solution

This integration provides a drop-in memory adapter that connects CrewAI agents to Memanto's agentic memory layer.

## Quick Start

```bash
pip install crewai requests
export MEMANTO_API_KEY=your_key_here
```

```python
from examples.crewai_memanto.memanto_memory import MemantoCrewMemory
from crewai import Agent, Task, Crew

memory = MemantoCrewMemory(agent_id="research-crew")

researcher = Agent(
    role="Senior Researcher",
    goal="Research and remember findings across sessions",
    backstory="An expert researcher who never forgets",
)

writer = Agent(
    role="Content Writer",
    goal="Retrieve past research and write compelling content",
    backstory="A writer who builds on accumulated knowledge",
)

research_task = Task(
    description="Research AI memory systems and store key findings in Memanto",
    agent=researcher,
)

write_task = Task(
    description="Retrieve previously stored research findings and write a summary",
    agent=writer,
)

crew = Crew(agents=[researcher, writer], tasks=[research_task, write_task])
result = crew.kickoff()
```

## Swapping Standard CrewAI Memory for Memanto

Standard CrewAI uses in-memory storage that resets on each run.

```python
# Before - no persistence
crew = Crew(agents=[...], tasks=[...], memory=True)

# After - persistent across sessions
from examples.crewai_memanto.memanto_memory import MemantoCrewMemory
memory = MemantoCrewMemory(agent_id="my-crew")
# Use memory.store() and memory.search() within your tasks
```

## Features

- Persistent memory across sessions
- Semantic search over past interactions
- User preference tracking
- Long-term task outcome storage
- Cross-agent memory sharing
- Automatic retry with exponential backoff
- Full type hints

## Built By

[Floyd](https://floyd.lonestaroracle.xyz) - autonomous coding agent by LoneStarOracle
