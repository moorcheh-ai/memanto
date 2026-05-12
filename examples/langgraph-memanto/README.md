# LangGraph + Memanto: Persistent Memory for Stateful Agents

This directory contains a production-ready example of **LangGraph agents using Memanto as their long-term memory layer**. LangGraph provides stateful workflow orchestration, and Memanto adds persistent cross-session memory.

> **Bounty Challenge**: This example demonstrates the key requirement: **Cross-Session Recall** — the agent remembers information from "yesterday" that isn't in the current thread's state.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         LangGraph Agent                           │
│  ┌─────────┐    ┌─────────────┐    ┌──────────┐    ┌───────────┐  │
│  │ recall  │───▶│   research  │───▶│  store   │───▶│   answer  │  │
│  │ memories│    │   (LLM)     │    │ findings │    │   query   │  │
│  └─────────┘    └─────────────┘    └──────────┘    └───────────┘  │
│       │                                                │          │
└───────┼────────────────────────────────────────────────┼──────────┘
        │                                                │
        ▼                                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                      Memanto Memory Layer                         │
│  • remember: Store findings with typed semantic memory           │
│  • recall:   Retrieve past sessions' memories                    │
│  • answer:   RAG-grounded responses from stored memories          │
│                                                                  │
│  Memory persists across SESSIONS - not just graph invocations    │
└──────────────────────────────────────────────────────────────────┘
```

## What This Demonstrates

- **Cross-Session Recall**: Run Session A today, retrieve those memories in Session B tomorrow
- **Typed Semantic Memory**: 13 memory types (fact, observation, decision, preference, etc.)
- **Persistent Context**: Graph state incorporates memories from prior sessions
- **RAG-Ground Responses**: `answer` tool synthesizes AI responses from stored memories
- **Zero Ingention Latency**: Memories searchable instantly upon storage

## Prerequisites

- Python 3.10+
- A [Moorcheh API key](https://console.moorcheh.ai/api-keys) (free tier: 100K ops/month)
- An [OpenAI API key](https://platform.openai.com/api-keys) (for LangGraph's LLM)

## Setup

```bash
cd examples/langgraph-memanto
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your MOORCHEH_API_KEY
```

## The Cross-Session Recall Demo

The key demonstration is proving that memories persist **across sessions**, not just within a single graph run:

```bash
# STEP 1: Run Session A - research a topic and store findings
python session_a.py

# STEP 2: Run Session B (even tomorrow!) - the agent recalls Session A's memories
python session_b.py
```

### What You'll See

**Session A output:**
```
Running research on 'LangGraph state management patterns'...
...
[Memory Stored]
Research findings saved to Memanto for future sessions.

Session A ended. Memories are now saved in Memanto.
```

**Session B output (same agent ID):**
```
Connected to Memanto as agent: research-assistant-001
(This is the SAME agent from Session A - memories should be preserved)

Running query about LangGraph state management...
(The agent should recall findings from Session A first)

...
[Prior Memories Retrieved]
Found 2 memories for 'research findings about LangGraph state management patterns':
  1. [observation] Research findings: LangGraph state management patterns (confidence: 0.75)
     Key insights from researching...

SESSION B COMPLETE
- Cross-session recall: True
- Prior memories retrieved: 2 items
- This proves memories from Session A persist into Session B!
```

**This proves cross-session persistence — the core bounty requirement.**

## File Structure

```
examples/langgraph-memanto/
├── README.md              # This file
├── requirements.txt       # Python dependencies
├── .env.example            # API key template
├── tools.py               # Memanto tools (remember, recall, answer)
├── research_graph.py      # Research assistant graph (StateGraph)
├── support_graph.py       # Customer support agent graph (StateGraph)
├── session_a.py           # Run 1: Research and store memories
├── session_b.py           # Run 2: Recall prior memories
└── run_support.py         # Bonus: Customer support agent demo
```

## The Two Graphs

### 1. Research Assistant (`research_graph.py`)
- **Purpose**: Demonstrate research workflow with cross-session memory
- **Nodes**: recall → research → store → answer
- **Use case**: Build knowledge bases over time without losing context

### 2. Customer Support Agent (`support_graph.py`)
- **Purpose**: Demonstrate support workflow with customer memory
- **Nodes**: greet → diagnose → resolve → follow-up
- **Use case**: Personalized support that remembers customer history

## Memanto Tools Used

| Tool | LangGraph Usage | Purpose |
|------|---------------|---------|
| `memanto_remember` | Store findings, preferences | Persist important information |
| `memanto_recall` | Check prior memories, context | Cross-session retrieval |
| `memanto_answer` | Synthesize RAG-grounded responses | Query stored knowledge |

## Bonus: Customer Support Demo

```bash
python run_support.py
```

This runs a customer support scenario where:
1. The agent checks for prior interactions with the customer
2. Retrieves any known preferences
3. Personalizes the support experience
4. Stores the new interaction for future sessions

## How Cross-Session Recall Works

```
Session A                            Session B (next day/week)
─────────                            ──────────────────────────

graph.invoke({...})                  graph.invoke({...})
     │                                    │
     ▼                                    ▼
remember tool                         recall tool
stores:                               retrieves:
  - research findings                   - Session A's findings
  - key facts                           - Session A's context
  - preferences

Session ends                         Session B uses
     │                                    │
     ▼                                    ▼
                              ┌─────────────────────┐
                              │ Cross-Session Memory│
                              │ Retrieved and used! │
                              └─────────────────────┘
```

The LangGraph state is ephemeral (within a single run), but Memanto provides the **persistent memory layer** that survives across sessions.

## Documentation

For the Memanto SDK and tool architecture, see:
- [Memanto SDK Client](../../memanto/cli/client/sdk_client.py)
- [CrewAI Integration Tools](../../integrations/crewai/memanto_crewai/tools.py) (same pattern)

---

**Built for the Memanto + LangGraph Integration Bounty**