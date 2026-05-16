# Memanto LangGraph Integration

LangChain-compatible tools for integrating [Memanto](https://memanto.ai) persistent memory with [LangGraph](https://github.com/langchain-ai/langgraph) workflows.

## Installation

```bash
pip install memanto-langgraph
```

Or install from source:

```bash
cd integrations/langgraph
pip install -e .
```

## Quick Start

```python
from memanto_langgraph import MemantoSetup, get_all_tools

# Initialize Memanto
setup = MemantoSetup(api_key="your-moorcheh-api-key")
client = setup.setup(agent_id="my-langgraph-agent")

# Get all tools for binding to your LLM
tools = get_all_tools(client, agent_id="my-langgraph-agent")

# Bind tools to your LLM
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(model="gpt-4o-mini")
llm_with_tools = llm.bind_tools(tools)
```

## Available Tools

### `memanto_remember`
Store structured memories with semantic types, confidence scores, and tags.

```python
# The LLM can use this tool to store:
# - Facts discovered during conversation
# - User preferences
# - Decisions made
# - Observations and learnings
```

### `memanto_recall`
Search and retrieve memories using natural language queries.

```python
# Retrieve relevant memories:
# - "What does the user prefer?"
# - "What decisions were made about the project?"
# - "Find all facts about AI frameworks"
```

### `memanto_answer`
Get AI-generated answers grounded in stored memories using RAG.

```python
# Ask questions that synthesize multiple memories:
# - "Based on our conversation history, what should I prioritize?"
# - "Summarize what we know about the user's requirements"
```

## Full LangGraph Example

```python
from typing import Annotated, Sequence, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from memanto_langgraph import MemantoSetup, get_all_tools

# Define state
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]

# Setup Memanto
setup = MemantoSetup(api_key="your-api-key")
client = setup.setup(agent_id="langgraph-demo")
tools = get_all_tools(client, "langgraph-demo")

# Create LLM with tools
llm = ChatOpenAI(model="gpt-4o-mini")
llm_with_tools = llm.bind_tools(tools)

def agent(state: AgentState):
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}

def should_continue(state: AgentState):
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return END

# Build graph
workflow = StateGraph(AgentState)
workflow.add_node("agent", agent)
workflow.add_node("tools", ToolNode(tools))
workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", should_continue, ["tools", END])
workflow.add_edge("tools", "agent")

graph = workflow.compile()

# Run the graph
result = graph.invoke({
    "messages": [HumanMessage(content="Remember that I prefer dark mode.")]
})
```

## Cross-Session Persistence

The key feature of Memanto is that memories persist across sessions:

```python
# Session 1: Store a preference
graph.invoke({
    "messages": [HumanMessage(content="Remember that my favorite color is blue.")]
})

# ... close the application, restart later ...

# Session 2: Recall the preference
graph.invoke({
    "messages": [HumanMessage(content="What is my favorite color?")]
})
# Agent recalls: "Your favorite color is blue."
```

## Memory Types

Memanto supports 13 semantic memory types for better organization:

- `fact` - Verified information
- `preference` - User preferences
- `goal` - Objectives and targets
- `decision` - Choices made
- `artifact` - Created content references
- `learning` - Insights and lessons
- `event` - Things that happened
- `instruction` - How to do things
- `relationship` - Connections between entities
- `context` - Background information
- `observation` - Things noticed
- `commitment` - Promises and obligations
- `error` - Mistakes to avoid

## License

MIT
