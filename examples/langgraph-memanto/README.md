# LangGraph + Memanto: Persistent Memory for Stateful Agents

This example demonstrates how to give your LangGraph agents **persistent, cross-session memory** using Memanto. The agent remembers user preferences from one session and recalls them in future sessions - no shared state required.

## Demo

![LangGraph + Memanto Demo](https://github.com/moorcheh-ai/memanto/raw/main/assets/langgraph-demo.gif)

## What This Demonstrates

- **Cross-Session Memory**: Preferences stored today are available tomorrow
- **Semantic Memory Types**: 13 memory categories (fact, preference, decision, etc.)
- **Natural Language Recall**: Search memories using plain English queries
- **Zero Ingestion Latency**: Memories are searchable the instant they're stored

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      LangGraph Workflow                          │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────────────┐  │
│  │  START   │───▶│  Agent   │───▶│  Tools (Memanto)         │  │
│  └──────────┘    │  Node    │◀───│  - memanto_remember      │  │
│                  └──────────┘    │  - memanto_recall        │  │
│                       │          │  - memanto_answer        │  │
│                       ▼          └──────────────────────────┘  │
│                  ┌──────────┐                                   │
│                  │   END    │                                   │
│                  └──────────┘                                   │
└───────────────────────│─────────────────────────────────────────┘
                        │
                        ▼
            ┌───────────────────────┐
            │   Memanto Cloud       │
            │   (Persistent Memory) │
            │   - Semantic Search   │
            │   - Typed Memories    │
            │   - Cross-Session     │
            └───────────────────────┘
```

## Prerequisites

- Python 3.10+
- A [Moorcheh API key](https://console.moorcheh.ai/api-keys) (free tier: 100K ops/month)
- An [OpenAI API key](https://platform.openai.com/api-keys)

## Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install the memanto-langgraph integration from local source
pip install -e ../../integrations/langgraph

# Configure API keys
cp .env.example .env
# Edit .env and add your MOORCHEH_API_KEY and OPENAI_API_KEY
```

## Running the Demo

### Option 1: Two Separate Sessions (Recommended for demos)

This approach best demonstrates cross-session persistence:

```bash
# Session 1: User shares preferences (stores in Memanto)
python run_session_1.py

# Session 2: Agent recalls preferences (retrieves from Memanto)
python run_session_2.py
```

### Option 2: Full Demo in One Run

```bash
python run_full_demo.py
```

## Example Output

### Session 1 (Storing Preferences)
```
[User] Hi! I'm Alex. I prefer to be contacted via email rather than phone calls.
[Agent] Hi Alex! I've noted that you prefer email over phone calls for contact.
        I'll make sure to remember this for future interactions.

[User] I'm in the Pacific timezone and prefer responses in the morning.
[Agent] Got it! I've stored that you're in the Pacific timezone and prefer
        morning responses. This will help me serve you better.

[User] I use dark mode for all my apps. Please remember that.
[Agent] Noted! I've saved your preference for dark mode. Whenever I make UI
        suggestions, I'll keep this in mind.
```

### Session 2 (Recalling Preferences)
```
[User] What are my contact preferences?
[Agent] Based on my records, you prefer to be contacted via email rather than
        phone calls.

[User] What timezone am I in?
[Agent] You're in the Pacific timezone, and you prefer to receive responses
        in the morning.

[User] What UI theme should you recommend for me?
[Agent] I'd recommend dark mode, since that's your preferred theme for all apps!
```

## File Structure

```
examples/langgraph-memanto/
├── README.md              # This file
├── requirements.txt       # Python dependencies
├── .env.example           # API key template
├── graph.py               # LangGraph workflow definition
├── run_session_1.py       # Session 1: Store preferences
├── run_session_2.py       # Session 2: Recall preferences
└── run_full_demo.py       # Full demo in one script
```

## How It Works

1. **Session 1**: The user shares preferences with the agent
   - Agent uses `memanto_remember` to store each preference
   - Memories are typed (e.g., "preference", "fact") for better retrieval
   - Session ends, local state is cleared

2. **Session 2**: User returns and asks about their preferences
   - Agent uses `memanto_recall` to search stored memories
   - Memories persist in Memanto's cloud database
   - Agent responds with accurate information from previous session

## Integration Points

The key integration is in `graph.py`:

```python
from memanto_langgraph import MemantoSetup, get_all_tools

# Setup Memanto client and session
setup = MemantoSetup(api_key="your-api-key")
client = setup.setup(agent_id="my-agent")

# Get tools for LangGraph
tools = get_all_tools(client, "my-agent")

# Bind to LLM
llm_with_tools = ChatOpenAI(model="gpt-4o-mini").bind_tools(tools)

# Use in LangGraph workflow
workflow = StateGraph(AgentState)
workflow.add_node("agent", agent_node)
workflow.add_node("tools", ToolNode(tools))
# ... configure edges ...
```

## Memory Types Available

| Type | Use Case |
|------|----------|
| `preference` | User likes/dislikes |
| `fact` | Verified information |
| `decision` | Choices made |
| `goal` | Objectives |
| `context` | Background info |
| `observation` | Things noticed |
| `instruction` | How to do things |
| `relationship` | Connections |
| `commitment` | Promises |
| `learning` | Insights |
| `event` | Things that happened |
| `artifact` | Created content |
| `error` | Mistakes to avoid |

## Troubleshooting

**"No memories found"**: Make sure you ran Session 1 before Session 2.

**API key errors**: Verify your `.env` file has valid keys.

**Import errors**: Ensure you installed the integration package:
```bash
pip install -e ../../integrations/langgraph
```

## License

MIT
