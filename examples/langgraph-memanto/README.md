# LangGraph + Memanto Research Assistant

A **LangGraph agent** with persistent cross-session memory powered by Memanto. This example demonstrates that the agent remembers information from past sessions that isn't in the current thread's state.

## What This Demonstrates

- **Cross-Session Recall**: The agent remembers research findings from "yesterday" that aren't in the current conversation
- **Persistent Memory**: Memories survive across separate graph invocations
- **Typed Semantic Memory**: 13 memory types (fact, observation, decision, etc.) with confidence scoring
- **Automatic Context Loading**: Past-session context injected into the system prompt automatically

## Architecture

```
Session 1 (Research Phase):
  User → "Research quantum computing trends"
  Agent → stores findings in Memanto
  Agent → stores user preferences in Memanto

Session 2 (New Conversation):
  User → "What did we discuss about quantum computing?"
  Agent → loads context from Memanto (cross-session recall!)
  Agent → answers using memories from Session 1
```

## Prerequisites

- Python 3.10+
- A [Moorcheh API key](https://console.moorcheh.ai/api-keys) (free tier: 100K ops/month)
- An [OpenAI API key](https://platform.openai.com/api-keys) (for the LLM)

## Setup

```bash
# 1. Create a virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure API keys
cp .env.example .env
# Edit .env and add your MOORCHEH_API_KEY and OPENAI_API_KEY
```

## Step-by-Step Demo

This is the recommended flow to prove cross-session persistence:

```bash
# Step 1: Run Session 1 — Research agent stores findings
python run_session1_research.py

# Step 2: Run Session 2 — New conversation recalls past memories
python run_session2_recall.py

# Step 3: Run the full interactive demo
python run_interactive.py
```

### Session 1 Output (Research Phase)
```
🔬 Research Assistant — Session 1: Research Phase
============================================================
📚 Starting research session...
[Graph] Calling memanto_remember to store findings...
✅ Stored memory: quantum-computing-trends-2025
✅ Stored memory: user-preference-quantum-topics
[Session complete — memories persisted to Memanto]
```

### Session 2 Output (Recall Phase)
```
🧠 Research Assistant — Session 2: Recall Phase
============================================================
📖 Loading memories from past sessions...
[Memanto] Found 5 relevant memories from past sessions
💬 User: What were the key quantum computing trends we discussed?
[Graph] Agent recalls memories from Memanto...
🤖 Assistant: Based on our previous research session, the key quantum
   computing trends are...
✅ Cross-session recall demonstrated!
```

## File Structure

```
examples/langgraph-memanto/
├── README.md                    # This file
├── requirements.txt             # Python dependencies
├── .env.example                 # API key template
├── run_session1_research.py     # Session 1: Research & store memories
├── run_session2_recall.py       # Session 2: Recall from past sessions
├── run_interactive.py           # Full interactive demo
└── research_assistant.py        # Core graph definition
```

## How It Works

### 1. Graph Structure

The agent uses a simple LangGraph with two nodes:

- **researcher** — Uses the LLM (with Memanto tools bound) to research topics and store findings
- **responder** — Loads context from Memanto and responds to follow-up questions

### 2. Cross-Session Memory Flow

```python
from memanto_langgraph import MemantoSetup, create_memanto_tools, MemantoMemorySaver

# Setup
setup = MemantoSetup(api_key=os.environ["MOORCHEH_API_KEY"])
client = setup.setup(agent_id="research-assistant")

# Tools for the LLM
tools = create_memanto_tools(client, agent_id="research-assistant")

# Memory saver for automatic context
saver = MemantoMemorySaver(client, agent_id="research-assistant")

# Load context from past sessions (injected into system prompt)
past_context = saver.load_context(query="research findings and preferences")
```

### 3. Proving Persistence

The key proof: **Session 2 has NO access to Session 1's conversation state.** The only way the agent can answer questions about past research is by retrieving memories from Memanto.

## Bonus: Interactive Demo

```bash
python run_interactive.py
```

This runs a continuous chat where:
1. First few turns are a "research session" — findings are stored
2. You can quit and restart
3. New session automatically loads past context
4. The agent references previous research without being told

## License

MIT
