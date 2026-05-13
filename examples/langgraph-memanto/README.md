# LangGraph + Memanto: Persistent Cross-Session Memory

<p align="center">
  <img src="https://github.com/moorcheh-ai/memanto/raw/main/assets/memanto-dark.svg" width="300" alt="Memanto">
  <br><b>+ LangGraph</b>
</p>

A production-ready example of a **LangGraph agent** using **Memanto** as its persistent long-term memory layer. The agent remembers customer context across completely disjointed sessions — proving **Cross-Session Recall**.

---

## 🎯 What This Demonstrates

| Feature | How It's Shown |
|---------|---------------|
| **Cross-Session Recall** | Session 1 stores facts → Session 2 (brand new process) retrieves them |
| **Typed Memory** | Uses Memanto's 13 memory types (fact, preference, observation, decision) |
| **Confidence Scoring** | Each memory has provenance + confidence + validation metadata |
| **LangGraph Integration** | Full state graph with Memanto tools wired into agent nodes |
| **Temporal Awareness** | Agent references when memories were created ("As we discussed on May 10...") |

## 🏗️ Architecture

```
┌──────────────────────────────────────────────┐
│              LangGraph State Graph            │
│                                              │
│  [classify_intent] → [support_agent] → [END]  │
│         │                  │                 │
│         ▼                  ▼                 │
│  ┌─────────────┐  ┌──────────────────┐       │
│  │  Memanto    │  │  Memanto         │       │
│  │  remember() │  │  recall() +      │       │
│  │             │  │  answer() (RAG)  │       │
│  └─────────────┘  └──────────────────┘       │
│         │                  │                 │
│         ▼                  ▼                 │
│  ┌──────────────────────────────────────┐    │
│  │     Memanto Semantic Memory DB       │    │
│  │  (Survives across sessions/agents)   │    │
│  └──────────────────────────────────────┘    │
└──────────────────────────────────────────────┘
```

## Prerequisites

- Python 3.10+
- A [Moorcheh API key](https://console.moorcheh.ai/api-keys) (free tier: 100K ops/month)
- An [OpenAI API key](https://platform.openai.com/api-keys) or [OpenRouter key](https://openrouter.ai/keys)

## Quick Start

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up API keys
cp .env.example .env
# Edit .env with your MOORCHEH_API_KEY and OPENAI_API_KEY

# 4. Run Session 1: Store customer context in Memanto
python langgraph_memanto_agent.py --session 1

# 5. Run Session 2: NEW session — proves cross-session recall!
python langgraph_memanto_agent.py --session 2
```

### Using OpenRouter (free LLM tier)

```bash
python langgraph_memanto_agent.py --session 1 \
  --openrouter-key "sk-or-v1-your-key-here"
```

## Demo Walkthrough

### Session 1: Storing Context
```
SESSION 1: Storing Customer Context
Customer ID: cust-4242
Agent ID: langgraph-support-agent

📝 Customer asks: 'I need help with my subscription.'
🤖 Agent responds: 'I'll look into that right away.'

💾 Storing in Memanto (cross-session memory):
  ✓ Stored: Customer subscription plan
  ✓ Stored: Customer communication preference
  ✓ Stored: Previous support interaction
  ✓ Stored: Discount applied
```

### Session 2: Cross-Session Recall
```
SESSION 2: Cross-Session Recall (NEW session)
(This is a BRAND NEW session — no in-memory state carried over)

🔍 Recalling customer context from Memanto...

[Cross-Session Recall] Found 4 memories:
  1. [fact] Customer subscription plan (confidence: 1.0)
     Customer cust-4242 is on the Pro plan ($49/mo)...
  2. [preference] Customer communication preference (confidence: 0.95)
     Customer cust-4242 prefers email communication...
  3. [observation] Previous support interaction (confidence: 0.9)
     Customer cust-4242 reported slow API performance on 2026-05-10...
  4. [decision] Discount applied (confidence: 1.0)
     Customer cust-4242 received a 15% loyalty discount...

📝 Customer: 'My API requests are timing out again.'
🤖 Agent: "I see you reported a similar API issue on May 10th,
    which was resolved by upgrading your rate limit. Since you're
    on the Pro plan with a 15% loyalty discount, let me check if
    we can further increase your rate limit..."
```

## File Structure

```
examples/langgraph-memanto/
├── README.md                    # This file
├── requirements.txt             # Python dependencies
├── .env.example                 # API key template
├── langgraph_memanto_agent.py   # Main agent with cross-session demo
└── run_demo.sh                  # One-command demo runner
```

## Technical Details

### Memanto Integration Pattern

The LangGraph agent integrates with Memanto through the `SdkClient`:

```python
from memanto.cli.client.sdk_client import SdkClient

client = SdkClient(api_key="moorcheh_...")
client.create_agent(agent_id="my-agent", pattern="tool")
client.activate_agent("my-agent")

# Store memory
client.remember(
    agent_id="my-agent",
    memory_type="fact",
    title="User preference",
    content="Prefers dark mode",
    confidence=0.9,
    tags=["preference", "ui"],
    source="langgraph-agent",
    provenance="explicit_statement",
)

# Recall memories (new session)
memories = client.recall(
    agent_id="my-agent",
    query="user ui preference",
    limit=5,
)

# RAG-grounded answers
answer = client.answer(
    agent_id="my-agent",
    question="What UI preferences does this user have?",
)

client.deactivate_agent("my-agent")
```

### LangGraph State Schema

```python
class SupportState(TypedDict):
    messages: Annotated[list, add_messages]     # Conversation history
    memory_context: str                          # Recalled Memanto memories
    customer_id: str                             # Customer identifier
    session_id: str                              # Session identifier
```

### Memory Types Used

| Type | Use Case | Example |
|------|----------|---------|
| `fact` | Verifiable information | "Customer is on Pro plan" |
| `preference` | User choices | "Prefers email over phone" |
| `observation` | Noted behavior | "Reported API slowness" |
| `decision` | Actions taken | "Applied 15% discount" |

## Bounty Information

This example is submitted for the **Memanto + LangGraph Integration Challenge** ($100 USD).

- **Bounty URL:** https://github.com/moorcheh-ai/memanto/issues/397
- **Deadline:** June 1, 2026
- **Winning Metric:** Highest Social Traction Score

### Bounty Checklist

- ✅ **Cross-Session Recall**: Agent remembers from "yesterday" in a brand new session
- ✅ **Clean, documented code**: Single folder with README and inline comments
- ✅ **Working example**: Runs end-to-end with `python langgraph_memanto_agent.py`
- ✅ **30-second demo**: See `run_demo.sh`
- ✅ **Starred repo**: https://github.com/moorcheh-ai/memanto
