

# CrewAI Integration with Memanto Agentic Memory

This document describes how to integrate CrewAI agents with Memanto's agentic memory system.

## Overview

The CrewAI-Memanto integration allows CrewAI agents to:

1. Store memories in Memanto's agentic memory system
2. Retrieve and search existing memories
3. Update and delete memories
4. Get context about an agent's memory state

This integration provides persistent memory capabilities to CrewAI agents, enabling them to remember past interactions, user preferences, and important context across sessions.

## Installation

First, install the required dependencies:

```bash
pip install crewai memanto
```

## Basic Usage

### 1. Initialize the Memory Manager

```python
from src.integrations.crewai import CrewAIMemoryManager, CrewAIMemoryConfig

# Configure the memory manager
config = CrewAIMemoryConfig(
    agent_id="my_crewai_agent",
    scope_type="agent",
    scope_id="my_crewai_agent",
    actor_id="user_123",
    source="agent"
)

# Initialize with your Moorcheh API key
memory_manager = CrewAIMemoryManager(config, moorcheh_api_key="your_moorcheh_api_key")
```

### 2. Store a Memory

```python
# Store a fact memory
result = memory_manager.store_memory(
    memory_type="fact",
    title="User's Favorite Color",
    content="The user's favorite color is blue.",
    confidence=0.95,
    tags=["user_preference", "color"]
)

print(f"Stored memory with ID: {result['id']}")
```

### 3. Retrieve a Memory

```python
# Retrieve a specific memory
memory = memory_manager.retrieve_memory("memory_id_here")
if memory:
    print(f"Title: {memory['title']}")
    print(f"Content: {memory['content']}")
```

### 4. Search Memories

```python
# Search for memories
results = memory_manager.search_memories(
    query="color",
    limit=5,
    memory_types=["fact", "preference"],
    min_confidence=0.8
)

for result in results:
    print(f"{result['title']} (ID: {result['id']})")
```

### 5. Update a Memory

```python
# Update a memory
result = memory_manager.update_memory(
    memory_id="memory_id_here",
    updates={
        "title": "Updated Favorite Color",
        "content": "The user's favorite color is now green.",
        "confidence": 0.98
    }
)
```

### 6. Delete a Memory

```python
# Delete a memory
success = memory_manager.delete_memory("memory_id_here")
if success:
    print("Memory deleted successfully")
```

## Advanced Usage with CrewAI Agents

### Adding Memory Tools to an Agent

```python
from crewai import Agent
from src.integrations.crewai import add_memory_tools_to_agent

# Create a CrewAI agent
agent = Agent(
    role="Personal Assistant",
    goal="Help the user with their daily tasks",
    backstory="An AI assistant that remembers user preferences and context"
)

# Add memory tools to the agent
agent = add_memory_tools_to_agent(
    agent=agent,
    moorcheh_api_key="your_moorcheh_api_key",
    agent_id="personal_assistant_agent"
)

# Now the agent has memory tools available
```

### Using Memory Tools in Tasks

```python
from crewai import Task

# Create a task that uses memory tools
task = Task(
    description="Remember that the user's favorite color is blue",
    expected_output="The memory has been stored successfully",
    agent=agent,
    tools=[agent.tools[0]]  # Use the store_memory tool
)

# Or use the tool directly
result = agent.tools[0](
    memory_type="fact",
    title="User's Favorite Color",
    content="The user's favorite color is blue.",
    confidence=0.95,
    tags=["user_preference", "color"]
)
```

### Enhancing a Crew with Memory

```python
from crewai import Crew

# Create a crew
crew = Crew(
    agents=[agent1, agent2],
    tasks=[task1, task2],
    verbose=2
)

# Enhance the crew with memory capabilities
crew = enhance_crew_with_memory(
    crew=crew,
    moorcheh_api_key="your_moorcheh_api_key",
    agent_configs={
        "agent1": {
            "agent_id": "agent1_id",
            "scope_type": "agent",
            "source": "agent"
        },
        "agent2": {
            "agent_id": "agent2_id",
            "scope_type": "workspace",
            "scope_id": "workspace_123"
        }
    }
)
```

## Memory Configuration Options

### CrewAIMemoryConfig Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| agent_id | str | Required | Unique identifier for the CrewAI agent |
| scope_type | str | "agent" | Type of scope for memory isolation (user, workspace, agent, session, project, task) |
| scope_id | str | agent_id | ID for scope isolation |
| actor_id | str | agent_id | Identifier for the actor creating memories |
| source | str | "agent" | Source type for memories (user, agent, tool, system) |

### Memory Types

Memanto supports the following memory types:

- `fact`: Factual information
- `preference`: User preferences
- `goal`: Agent goals and objectives
- `decision`: Decisions made by the agent
- `artifact`: Documents, files, or other artifacts
- `learning`: Learned information or insights
- `event`: Events or occurrences
- `instruction`: Instructions or guidelines
- `relationship`: Relationships between entities
- `context`: Contextual information
- `observation`: Observations made by the agent
- `commitment`: Commitments or promises
- `error`: Error information

## Best Practices

1. **Memory Organization**: Use appropriate scope types to organize memories:
   - Use `agent` scope for agent-specific memories
   - Use `workspace` scope for workspace-wide memories
   - Use `user` scope for user-specific memories

2. **Confidence Scoring**: Set appropriate confidence scores:
   - 0.9-1.0 for highly reliable information
   - 0.7-0.9 for generally reliable information
   - 0.5-0.7 for less reliable information

3. **Tagging**: Use tags to categorize memories:
   - Add relevant tags to make memories easier to find
   - Use consistent tag naming conventions

4. **Memory Lifecycle**: Manage memory lifecycle:
   - Update memories when information changes
   - Delete outdated or incorrect memories
   - Use TTL (Time To Live) for temporary memories

5. **Context Enrichment**: Use the enhanced memory system to add context:
   - Set relevance scores based on current tasks
   - Add priority and importance scores
   - Track memory access patterns

## Error Handling

The integration includes robust error handling:

```python
from src.integrations.crewai import MemoryError

try:
    memory_manager.store_memory(...)
except MemoryError as e:
    print(f"Failed to store memory: {str(e)}")
```

## Advanced Features

### Enhanced Memory System

The integration includes an enhanced memory system with additional features:

```python
from src.memanto.memory import (
    EnhancedMemoryRecord,
    MemoryContext,
    MemoryEnrichmentService,
    create_enhanced_memory,
    create_memory_context
)

# Create an enhanced memory
memory = create_enhanced_memory(
    memory_type="fact",
    title="Important Fact",
    content="This is an important fact to remember",
    scope=memory_scope,
    actor_id="user_123",
    confidence=0.95,
    priority=0.8,
    importance=0.9
)

# Create a memory context
context = create_memory_context(
    user_confirmed=True,
    conversation_history=["Hello", "How are you?"],
    current_task="Remember important facts",
    agent_state={"priority_rules": [{"type": "fact", "priority": 0.8}]}
)

# Enrich the memory with context
enrichment_service = MemoryEnrichmentService()
enriched_memory = enrichment_service.enrich_memory(memory, context)
```

### Memory Validation

The enhanced memory system includes advanced validation:

```python
from src.memanto.memory import EnhancedMemoryValidationPolicy

# Validate a memory
result = EnhancedMemoryValidationPolicy.validate_memory(
    memory=enriched_memory,
    context=context
)

if result["valid"]:
    print("Memory is valid")
else:
    print(f"Memory validation failed: {result['reason']}")
```

## Examples

### Example 1: Personal Assistant Agent

```python
from crewai import Agent, Task, Crew
from src.integrations.crewai import add_memory_tools_to_agent

# Create a personal assistant agent
assistant = Agent(
    role="Personal Assistant",
    goal="Help the user with their daily tasks and remember important information",
    backstory="An AI assistant that remembers user preferences and context across sessions"
)

# Add memory tools
assistant = add_memory_tools_to_agent(
    agent=assistant,
    moorcheh_api_key="your_moorcheh_api_key",
    agent_id="personal_assistant"
)

# Create a task to remember user preferences
remember_task = Task(
    description="Remember that the user's favorite color is blue and they prefer tea over coffee",
    expected_output="The user's preferences have been stored in memory",
    agent=assistant
)

# Create a task to retrieve preferences
retrieve_task = Task(
    description="Retrieve the user's favorite color and drink preference",
    expected_output="The user's favorite color is blue and they prefer tea",
    agent=assistant,
    context=[remember_task]
)

# Create and run the crew
crew = Crew(
    agents=[assistant],
    tasks=[remember_task, retrieve_task],
    verbose=2
)

result = crew.kickoff()
```

### Example 2: Multi-Agent System with Shared Memory

```python
from crewai import Agent, Task, Crew
from src.integrations.crewai import enhance_crew_with_memory

# Create agents
planner = Agent(
    role="Planner",
    goal="Plan tasks based on user requirements",
    backstory="An AI agent that plans tasks"
)

executor = Agent(
    role="Executor",
    goal="Execute planned tasks",
    backstory="An AI agent that executes tasks"
)

# Create tasks
plan_task = Task(
    description="Plan a day of tasks for the user",
    expected_output="A list of planned tasks",
    agent=planner
)

execute_task = Task(
    description="Execute the planned tasks",
    expected_output="All tasks completed successfully",
    agent=executor,
    context=[plan_task]
)

# Create and enhance crew
crew = Crew(
    agents=[planner, executor],
    tasks=[plan_task, execute_task],
    verbose=2
)

crew = enhance_crew_with_memory(
    crew=crew,
    moorcheh_api_key="your_moorcheh_api_key",
    agent_configs={
        "Planner": {"agent_id": "planner_agent"},
        "Executor": {"agent_id": "executor_agent"}
    }
)

# Run the crew
result = crew.kickoff()
```

## Troubleshooting

### Common Issues

1. **Memory Not Found**: Ensure the memory ID is correct and the namespace matches.
2. **Permission Errors**: Verify your Moorcheh API key has the correct permissions.
3. **Performance Issues**: Consider batching memory operations for better performance.
4. **Memory Conflicts**: Use appropriate validation and consistency checks.

### Debugging

Enable debug logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## API Reference

### CrewAIMemoryManager

#### Methods

- `store_memory(memory_type, title, content, confidence=0.8, tags=None, source_ref=None, **extra_fields)`: Store a memory
- `retrieve_memory(memory_id)`: Retrieve a specific memory
- `search_memories(query, limit=10, memory_types=None, tags=None, min_confidence=0.5)`: Search for memories
- `update_memory(memory_id, updates)`: Update a memory
- `delete_memory(memory_id)`: Delete a memory
- `get_agent_context()`: Get context about the agent's memories

### CrewAIMemoryTool

#### Methods

- `store_memory(memory_type, title, content, confidence=0.8, tags=None, source_ref=None)`: Store a memory
- `retrieve_memory(memory_id)`: Retrieve a memory
- `search_memories(query, limit=10, memory_types=None, tags=None)`: Search for memories
- `update_memory(memory_id, updates)`: Update a memory
- `delete_memory(memory_id)`: Delete a memory
- `get_agent_context()`: Get agent context

### Enhanced Memory System

#### Classes

- `EnhancedMemoryRecord`: Enhanced memory record with additional fields
- `MemoryContext`: Context for memory operations
- `MemoryEnrichmentService`: Service for enriching memories
- `MemoryQueryService`: Service for querying memories

#### Functions

- `create_enhanced_memory(...)`: Create an enhanced memory
- `create_memory_context(...)`: Create a memory context

## Conclusion

The CrewAI-Memanto integration provides powerful memory capabilities to CrewAI agents, enabling persistent memory across sessions and better context awareness. By following the patterns and best practices in this guide, you can create sophisticated AI agents that remember and utilize context effectively.

For more information about Memanto's agentic memory system, see the [Memanto Documentation](https://docs.moorcheh.ai/memanto).

For more information about CrewAI, see the [CrewAI Documentation](https://docs.crewai.com/).
