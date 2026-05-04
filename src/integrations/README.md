

# CrewAI Integration for Memanto

This directory contains the CrewAI integration module for Memanto's agentic memory system.

## Overview

The CrewAI integration enables CrewAI agents to:

1. Store memories in Memanto's agentic memory system
2. Retrieve and search existing memories
3. Update and delete memories
4. Get context about an agent's memory state

## Files

- `crewai.py`: Main integration module with CrewAIMemoryManager, CrewAIMemoryTool, and utility functions
- `README.md`: This file

## Usage

See the [CrewAI Integration Documentation](../../docs/crewai_integration.md) for detailed usage instructions.

## Installation

To use the CrewAI integration, install the optional `crewai` dependency:

```bash
pip install memanto[crewai]
```

## Example

```python
from crewai import Agent
from src.integrations.crewai import add_memory_tools_to_agent

# Create a CrewAI agent
agent = Agent(
    role="Personal Assistant",
    goal="Help the user with their daily tasks",
    backstory="An AI assistant that remembers user preferences"
)

# Add memory tools to the agent
agent = add_memory_tools_to_agent(
    agent=agent,
    moorcheh_api_key="your_moorcheh_api_key",
    agent_id="personal_assistant"
)

# Now the agent can use memory tools
agent.tools[0](  # store_memory tool
    memory_type="fact",
    title="User's Favorite Color",
    content="The user's favorite color is blue.",
    confidence=0.95,
    tags=["user_preference", "color"]
)
```

## Testing

Run the integration tests:

```bash
cd /workspace/memanto
python -m pytest tests/test_crewai_integration.py -v
```

## Documentation

For more information, see the [CrewAI Integration Documentation](../../docs/crewai_integration.md).

