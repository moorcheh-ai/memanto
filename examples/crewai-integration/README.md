# CrewAI + Memanto Integration

A production-ready example demonstrating how to integrate **Memanto** as a long-term memory layer with **CrewAI** agents.

## 🎯 What This Example Shows

This example solves a common problem in agentic AI: **long-term amnesia**. CrewAI agents are powerful, but they typically lose all context between sessions. Memanto provides persistent, searchable memory that:

- ✅ Persists across agent restarts and system reboots
- ✅ Enables cross-agent memory sharing (different agents can access the same memories)
- ✅ Supports semantic search for relevant information retrieval
- ✅ Handles temporal queries (what was true at a specific point in time)
- ✅ Provides RAG-based question answering over stored memories

### The "Memory Test" Use Case

The example demonstrates a realistic workflow:

1. **Research Phase**: A "Research Agent" gathers information and stores 5 key findings in Memanto
2. **Time Passes**: Simulates 24 hours (in production, this would be a separate run)
3. **Writer Phase**: A "Writer Agent" (potentially in a different session) retrieves those findings and creates content

This proves that:
- Memories persist across sessions ✅
- Different agents can share the same memory ✅
- Information retrieval is accurate and semantic ✅

## 📋 Requirements

- Python 3.10 or higher
- A valid Moorcheh API key ([get one here](https://console.moorcheh.ai/api-keys))
- Internet connection (for Moorcheh API)

## 🚀 Quick Start

### 1. Install Dependencies

```bash
# Navigate to the example directory
cd examples/crewai-integration

# Install required packages
pip install -r requirements.txt
```

### 2. Set Your API Key

```bash
# Set your Moorcheh API key as an environment variable
export MOORCHEH_API_KEY='your-api-key-here'

# Or add it to a .env file:
echo "MOORCHEH_API_KEY=your-api-key-here" > .env
```

### 3. Run the Example

```bash
python memanto_crewai_example.py
```

## 📖 How It Works

### Architecture

```
┌─────────────────┐
│  CrewAI Agent   │
│                 │
│  Research Task  │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────┐
│  MemantoMemoryTool (CrewAI Tool)    │
│  ─────────────────────────────────  │
│  • remember(): Store memories       │
│  • recall(): Retrieve memories      │
│  • answer(): RAG-based QA           │
└────────┬────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│  Memanto API (Moorcheh)             │
│  • Persistent storage               │
│  • Semantic search                  │
│  • Temporal queries                 │
└─────────────────────────────────────┘
```

### Code Structure

#### 1. **Memanto Tools for CrewAI**

Three custom CrewAI tools bridge CrewAI and Memanto:

```python
# Store information
MemoryWriterTool  # Stores memories (facts, decisions, etc.)

# Retrieve information
MemoryReaderTool   # Searches memories by semantic similarity

# RAG-based QA
MemoryQA_Tool      # Answers questions using retrieved context
```

#### 2. **Agents with Memory**

```python
# Research Agent - stores findings
research_agent = Agent(
    role="Research Specialist",
    tools=[MemoryWriterTool(), MemoryReaderTool(), MemoryQA_Tool()],
    # ... other parameters
)

# Writer Agent - retrieves and uses findings
writer_agent = Agent(
    role="Content Writer",
    tools=[MemoryWriterTool(), MemoryReaderTool(), MemoryQA_Tool()],
    # ... other parameters
)
```

#### 3. **Shared Memory Namespace**

Both agents use the same `agent_id` in Memanto, enabling cross-agent memory sharing:

```python
# Both agents share this namespace
agent_id = "crewai_memory_test"

# Research Agent stores here
MemoryWriterTool(api_key=api_key, agent_id=agent_id)

# Writer Agent reads from here (even in a different session!)
MemoryReaderTool(api_key=api_key, agent_id=agent_id)
```

### Memory Types

Memanto supports typed memories for better organization:

- `fact` - Factual information
- `decision` - Decisions made
- `preference` - User or system preferences
- `goal` - Goals or objectives
- `commitment` - Commitments or promises
- `artifact` - Created artifacts or outputs
- `learning` - Learned information
- `event` - Events that occurred
- `instruction` - Instructions or guidelines
- `relationship` - Relationship information
- `context` - Contextual information
- `observation` - Observations made
- `error` - Errors encountered

Example usage:
```python
tool._run("fact: Memanto is an open-source memory layer")
tool._run("decision: Use Memanto for all agent memory operations")
tool._run("preference: User prefers concise responses")
```

## 🔧 Integrating Memanto into Your CrewAI Project

### Step 1: Install Memanto

```bash
pip install memanto
```

### Step 2: Create a Memory Tool

Copy the `MemantoMemoryTool` class from this example into your project, or use the simplified version:

```python
from crewai.tools import BaseTool

class MemantoMemoryTool(BaseTool):
    name: str = "memanto_memory"
    description: str = "Store and retrieve long-term memories"

    def __init__(self, api_key: str, agent_id: str = "my_agent"):
        super().__init__()
        self.api_key = api_key
        self.agent_id = agent_id
        self._client = None

    def _get_client(self):
        if self._client is None:
            from memanto.cli.client.sdk_client import SdkClient
            self._client = SdkClient(api_key=self.api_key)

            # Create/activate agent
            try:
                self._client.create_agent(agent_id=self.agent_id, pattern="tool")
            except:
                pass  # Agent exists

            self._client.activate_agent(self.agent_id)
        return self._client

    def _run(self, content: str, action: str = "remember") -> str:
        client = self._get_client()

        if action == "remember":
            result = client.remember(
                agent_id=self.agent_id,
                memory_type="fact",
                title=content[:50],
                content=content,
                confidence=0.9
            )
            return f"Stored: {result['memory_id']}"

        elif action == "recall":
            result = client.recall(agent_id=self.agent_id, query=content, limit=5)
            memories = result.get("memories", [])
            return "\n".join([m['content'] for m in memories])
```

### Step 3: Add Tool to Your Agents

```python
# Create the tool
memory_tool = MemantoMemoryTool(
    api_key=os.getenv("MOORCHEH_API_KEY"),
    agent_id="my_crewai_agent"
)

# Add to your agents
my_agent = Agent(
    role="My Agent",
    goal="Complete tasks using persistent memory",
    tools=[memory_tool],
    # ... other parameters
)
```

### Step 4: Use in Tasks

```python
task = Task(
    description="""
    Complete your task and use the memory tool to:
    1. Store important findings (remember)
    2. Retrieve relevant context (recall)

    Example: Use memory_tool with action='remember' to save key insights.
    """,
    agent=my_agent
)
```

## 🎬 Demo Output

When you run `memanto_crewai_example.py`, you'll see:

```
================================================================================
🧠 MEMANTO + CREWAI INTEGRATION: MEMORY TEST DEMO
================================================================================

--------------------------------------------------------------------------------
📊 PART 1: RESEARCH PHASE - Storing Findings
--------------------------------------------------------------------------------

🔍 Running Research Agent to store findings...

[Memanto] Created new agent: crewai_memory_test
[Memanto] Session activated for crewai_memory_test

✅ Research Phase Complete!

--------------------------------------------------------------------------------
⏰ PART 2: TIME SIMULATION - 24 Hours Later
--------------------------------------------------------------------------------

💤 Simulating 24-hour delay... (memory persists across sessions)

✅ Time simulation complete - creating a NEW session

--------------------------------------------------------------------------------
✍️  PART 3: WRITER PHASE - Retrieving Findings
--------------------------------------------------------------------------------

📝 Running Writer Agent to retrieve and synthesize findings...

✅ Writer Phase Complete!

--------------------------------------------------------------------------------
✅ PART 4: VERIFICATION - Memory Contents
--------------------------------------------------------------------------------

📚 All stored memories:

Found 5 memories:

1. Memanto is an open-source agentic memory layer...
   Content: Memanto is an open-source agentic memory layer that provides persistent memory for AI agents
   Score: 0.912

2. Traditional vector databases vs Memanto...
   Content: Traditional vector databases require indexing time, while Memanto provides instant availability
   Score: 0.887

...

================================================================================
🎉 MEMORY TEST DEMO COMPLETE!
================================================================================
```

## 🌟 Bonus Features Demonstrated

### Contradiction Handling

The example includes a bonus demo showing how Memanto handles contradictory information:

```bash
python memanto_crewai_example.py
# After the main demo, run the bonus demo when prompted
```

This demonstrates Memanto's ability to:
- Store new information that updates old facts
- Supersede outdated memories
- Provide the most current information when queried

## 🔍 Troubleshooting

### "Module 'memanto' not found"

```bash
pip install memanto
```

### "MOORCHEH_API_KEY not set"

```bash
export MOORCHEH_API_KEY='your-key-here'
```

### "Agent already exists" (this is normal)

The code handles this gracefully - it means the agent namespace was created in a previous run.

### Memory not found

Make sure both agents use the same `agent_id`. The memory namespace is per-agent-id.

## 📚 Advanced Usage

### Temporal Queries

Memanto supports querying what was true at a specific point in time:

```python
# What was true yesterday?
result = client.recall_as_of(
    agent_id=agent_id,
    query="user preferences",
    as_of="2026-05-02T00:00:00Z"
)
```

### Differential Queries

Find what changed since a date:

```python
# What changed since last week?
result = client.recall_changed_since(
    agent_id=agent_id,
    since="2026-04-26T00:00:00Z"
)
```

### Current State Only

Get only currently active (non-superseded) memories:

```python
result = client.recall_current(
    agent_id=agent_id,
    query="active decisions"
)
```

### Memory Confidence

Set confidence levels for memories:

```python
client.remember(
    agent_id=agent_id,
    memory_type="fact",
    content="Important information",
    confidence=0.95  # 0.0 to 1.0
)
```

## 🤝 Contributing

This example is part of the Memanto project. Contributions welcome!

## 📄 License

This example is MIT licensed, same as Memanto.

## 🔗 Links

- [Memanto Documentation](https://docs.memanto.ai)
- [Memanto GitHub](https://github.com/moorcheh-ai/memanto)
- [CrewAI Documentation](https://docs.crewai.com)
- [Moorcheh Console](https://console.moorcheh.ai)

## 💡 Tips for Production Use

1. **Environment Variables**: Always store API keys in environment variables, never hardcode
2. **Agent Namespaces**: Use descriptive `agent_id` values for better organization
3. **Memory Types**: Use appropriate memory types for better retrieval accuracy
4. **Error Handling**: Wrap Memanto calls in try-except blocks for robustness
5. **Batch Operations**: Use `batch_remember()` for storing multiple memories efficiently

## 🎓 Learn More

- Read the [Memanto paper on Hugging Face](https://huggingface.co/papers/2604.22085)
- Join the [Memanto Discord](https://discord.gg/CyxRFQSQ3p)
- Follow [@moorcheh_ai](https://x.com/moorcheh_ai) on X/Twitter
