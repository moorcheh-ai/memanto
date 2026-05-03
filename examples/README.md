# Memanto Examples

This directory contains integration examples showing how to use Memanto with various AI frameworks and tools.

## 📚 Available Examples

### [CrewAI Integration](./crewai-integration/)

A production-ready example demonstrating Memanto as a long-term memory layer for CrewAI agents.

**What it shows:**
- ✅ Cross-session memory persistence (memories survive agent restarts)
- ✅ Cross-agent memory sharing (different agents access shared memory)
- ✅ Semantic search and retrieval
- ✅ RAG-based question answering
- ✅ Handling contradictory memories

**Use case:** Research Agent stores findings → Writer Agent retrieves them 24 hours later

**Quick start:**
```bash
cd crewai-integration
pip install -r requirements.txt
export MOORCHEH_API_KEY='your-key'
python quickstart.py
```

## 🚀 Getting Started with Any Example

1. **Install Memanto:**
   ```bash
   pip install memanto
   ```

2. **Get an API Key:**
   - Visit [https://console.moorcheh.ai/api-keys](https://console.moorcheh.ai/api-keys)
   - Create a free account and generate an API key
   - Free tier: 100K operations/month

3. **Set your API key:**
   ```bash
   export MOORCHEH_API_KEY='your-api-key-here'
   ```

4. **Navigate to an example and follow its README:**
   ```bash
   cd crewai-integration  # or other example
   cat README.md
   ```

## 📖 Common Patterns

### Pattern 1: Persistent Agent Memory

Give your agents long-term memory that survives restarts:

```python
from memanto.cli.client.sdk_client import SdkClient

# Initialize
client = SdkClient(api_key="your-key")
client.create_agent(agent_id="my_agent", pattern="tool")
client.activate_agent(agent_id="my_agent")

# Store memory
client.remember(
    agent_id="my_agent",
    memory_type="fact",
    title="Important information",
    content="This persists across sessions",
    confidence=0.9
)

# Retrieve memory (even in a new session!)
result = client.recall(agent_id="my_agent", query="important info")
```

### Pattern 2: Cross-Agent Memory Sharing

Multiple agents share the same memory namespace:

```python
# Both agents share this agent_id
shared_agent_id = "team_memory"

# Agent A stores
client.remember(agent_id=shared_agent_id, ...)

# Agent B retrieves (later, different session)
result = client.recall(agent_id=shared_agent_id, ...)
```

### Pattern 3: RAG-Based QA

Answer questions using stored context:

```python
answer = client.answer(
    agent_id="my_agent",
    question="What did we decide about X?",
    limit=5  # Use top 5 memories as context
)

print(answer["answer"])  # Grounded answer from memory
```

## 🎯 Memory Types

Memanto supports typed memories for better organization:

| Type | Use Case |
|------|----------|
| `fact` | Factual information |
| `decision` | Decisions made |
| `preference` | User/system preferences |
| `goal` | Goals or objectives |
| `commitment` | Commitments or promises |
| `artifact` | Created outputs |
| `learning` | Learned information |
| `event` | Events that occurred |
| `instruction` | Instructions or guidelines |
| `relationship` | Relationship info |
| `context` | Contextual information |
| `observation` | Observations made |
| `error` | Errors encountered |

## 🔍 Advanced Features

### Temporal Queries

```python
# What was true at this point in time?
client.recall_as_of(agent_id="my_agent", as_of="2026-05-01T00:00:00Z", query="...")

# What changed since this date?
client.recall_changed_since(agent_id="my_agent", since="2026-05-01T00:00:00Z")

# Only currently active (non-superseded) memories
client.recall_current(agent_id="my_agent", query="...")
```

### Batch Operations

```python
# Store multiple memories at once
memories = [
    {"content": "First memory", "type": "fact"},
    {"content": "Second memory", "type": "decision"},
    {"content": "Third memory", "type": "preference"},
]

result = client.batch_remember(agent_id="my_agent", memories=memories)
print(f"Stored {result['successful']} memories")
```

### File Upload

```python
# Upload documents directly to memory
result = client.upload_file(
    agent_id="my_agent",
    file_path="./research.pdf"
)
# Content is chunked and made searchable via recall()
```

## 🤝 Contributing Examples

Want to add an example? Here's what we look for:

1. **Real-world use case**: Solve a genuine problem
2. **Working code**: Must run without issues
3. **Clear documentation**: README with setup and usage
4. **Well-structured**: Clean, readable code
5. **Demo-ready**: Easy to understand and demonstrate

Submit a PR with your example in a new subdirectory!

## 📄 License

All examples are MIT licensed.

## 🔗 Resources

- [Memanto Documentation](https://docs.memanto.ai)
- [Memanto GitHub](https://github.com/moorcheh-ai/memanto)
- [Moorcheh Console](https://console.moorcheh.ai)
- [Join Discord](https://discord.gg/CyxRFQSQ3p)
- [Paper on Hugging Face](https://huggingface.co/papers/2604.22085)

## 💡 Need Help?

- 📖 [Read the docs](https://docs.memanto.ai)
- 💬 [Join our Discord](https://discord.gg/CyxRFQSQ3p)
- 📧 Email support@moorcheh.ai
