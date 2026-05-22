# LangGraph + Memanto: Research Agent with Persistent Memory

A LangGraph-powered research assistant agent that uses **Memanto** as its long-term memory layer — storing, retrieving, and answering from memories that persist across disjointed sessions.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    LangGraph Workflow                        │
│                                                              │
│  ┌──────────┐    ┌──────────┐    ┌──────────────┐           │
│  │  RESEARCH │───▶│  EVALUATE │───▶│  RESPOND     │           │
│  │  (search) │    │ (memory)  │    │  (final)     │           │
│  └──────────┘    └─────┬────┘    └──────────────┘           │
│                        │                                      │
│                  ┌─────▼─────┐                                │
│                  │  MEMANTO  │                                │
│                  │  (store / │                                │
│                  │   recall /│                                │
│                  │   answer) │                                │
│                  └───────────┘                                │
└─────────────────────────────────────────────────────────────┘
```

## What This Demonstrates

- **Cross-Session Recall**: The agent remembers findings from previous sessions that are not in the current thread's state
- **Typed Semantic Memory**: 13 memory types (fact, decision, goal, observation, etc.) for structured storage
- **AI-Driven Confidence Scoring**: The agent self-evaluates certainty before storing memories
- **Contradiction Detection**: Conflicting memories are flagged with versioning, not silently overwritten
- **Three Primitives**: `remember`, `recall`, and `answer` — LLM-grounded responses from memory

## Quick Demo

### Session 1: Store research findings
```bash
python run_agent.py --session research-2026-05-22
```
```
🔍 Researching: quantum computing error correction...
📝 [REMEMBER] Stored: fact — "Surface codes are the leading QECC approach" (confidence: 0.92)
📝 [REMEMBER] Stored: decision — "Prioritize topological QC over gate-based for fault tolerance" (confidence: 0.85)
📝 [REMEMBER] Stored: observation — "Google's Willow chip achieved below-threshold error rates" (confidence: 0.88)
✅ Response: Surface codes are currently the leading approach...
```

### Session 2 (new session, next day): Recall previous findings
```bash
python run_agent.py --session followup-2026-05-23
```
```
🔍 Researching: latest quantum error correction advances...
🔎 [RECALL] Found 3 memories from previous session:
  - fact: "Surface codes are the leading QECC approach" (conf: 0.92, 2026-05-22)
  - decision: "Prioritize topological QC over gate-based" (conf: 0.85, 2026-05-22)
  - observation: "Google's Willow chip achieved below-threshold" (conf: 0.88, 2026-05-22)
💡 [ANSWER] Based on your previous research: Surface codes remain the leading...
📝 [REMEMBER] Updated: fact — "Surface codes + lattice surgery now preferred" (confidence: 0.90, supersedes previous)
✅ Response: Building on your earlier findings, surface codes with lattice surgery...
```

## Prerequisites

- Python 3.10+
- A [Moorcheh API key](https://console.moorcheh.ai/api-keys) (free tier: 100K ops/month)
- An OpenAI or OpenRouter API key (for the LangGraph LLM)

## Setup

```bash
python -m venv venv
source venv/bin activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your MOORCHEH_API_KEY and OPENAI_API_KEY
```

## Running

```bash
# Interactive mode (conversational)
python run_agent.py

# With a specific query
python run_agent.py --query "What are the latest advances in quantum error correction?"

# With a named session (for cross-session recall)
python run_agent.py --session my-research-session
```

## How It Works

The LangGraph workflow has three nodes:

1. **RESEARCH**: Takes the user query and gathers information (simulated web search + existing knowledge)
2. **EVALUATE**: Checks Memanto for relevant memories from previous sessions, and stores new findings
3. **RESPOND**: Generates a final answer enriched with recalled memories

The `MemantoTool` wraps all three Memanto primitives:

- `remember(content, memory_type, confidence)` — Store a new typed memory
- `recall(query, limit)` — Search for relevant memories
- `answer(query)` — Get an LLM-grounded answer from memory

## Cross-Session Recall Proof

The key feature: memories persist in Memanto's semantic database, not in LangGraph state. This means:

1. Run the agent in Session A → memories are stored
2. Start a completely new Session B with a different graph state
3. The agent **recalls** Session A's memories because they live in Memanto, not in the ephemeral graph

This is the "permanent brain" for your graph — the one thing LangGraph's built-in state management can't do alone.
