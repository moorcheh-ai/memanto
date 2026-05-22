# LangGraph + Memanto: Give Your Graph a Permanent Brain

A LangGraph research assistant with persistent cross-session memory powered by Memanto.
Memories survive across sessions, agents, and runs -- going beyond the standard
LangGraph state to provide true long-term recall.

## Why This Matters

LangGraph is the gold standard for stateful agents, but its checkpointing is
per-thread -- it cannot recall information from a different conversation or a
previous session. Memanto solves this by acting as an external persistent memory layer.

| Feature | LangGraph State | Memanto Memory |
|---------|----------------|----------------|
| Persistence | Per-thread only | Cross-session |
| Scope | Current conversation | All sessions |
| Retrieval | Direct access | Semantic search |
| Types | Unstructured | 13 typed categories |
| Confidence | N/A | 0.0-1.0 scoring |
| Provenance | N/A | Tracked per memory |
| Ingestion | Instant | Zero latency |

## What This Demonstrates

1. Cross-Session Recall: The agent remembers something from a previous session
   that is NOT in the current thread state. Run session 1, close it, run session 2
   in a new process -- memories persist.

2. Typed Semantic Memory: 13 memory types (fact, observation, decision, preference,
   etc.) with confidence scoring and provenance tracking.

3. Two Integration Approaches:
   - Simple: create_simple_research_agent() -- a ReAct agent with Memanto tools
   - Advanced: create_research_graph() -- a custom StateGraph with recall/research/synthesize nodes

4. RAG Answering: Use memanto_answer for AI-generated responses grounded in stored memories.

## Quick Start

### Prerequisites

- Python 3.10+
- Moorcheh API key (free tier: 100K ops/month) at https://console.moorcheh.ai/api-keys
- OpenAI API key at https://platform.openai.com/api-keys

### Setup

    cd examples/langgraph-memanto
    python -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env
    # Edit .env and add your MOORCHEH_API_KEY and OPENAI_API_KEY

### Step-by-Step Demo (Proves Cross-Session Recall)

    # Step 1: Research Agent stores findings in Memanto
    python run_session1_research.py

    # Step 2 (in a new terminal, even days later):
    python run_session2_recall.py

## File Structure

    examples/langgraph-memanto/
      README.md                    # This file
      requirements.txt             # Python dependencies
      .env.example                 # API key template
      memanto_langgraph_tools.py   # LangGraph tool wrappers for Memanto
      graph.py                     # LangGraph workflow definitions
      run_session1_research.py     # Session 1: Store memories
      run_session2_recall.py       # Session 2: Recall memories (proves persistence)

## Memanto Tools for LangGraph

Three tools are provided, mirroring Memanto three core operations:

1. memanto_remember - Store a structured memory for long-term persistence.
   Takes memory_type, title, content, confidence (0.0-1.0), and optional tags.

2. memanto_recall - Search persistent memory database using natural language.
   Takes query, optional limit (1-20), and optional memory_types filter.

3. memanto_answer - Get an AI-generated answer grounded in stored memories using RAG.
   Takes a question string.

## Key Design Decisions

1. Tool-based integration: Memanto is exposed as LangGraph tools, not as a
   checkpointer replacement. Memory operations are transparent and controllable.

2. MemantoSetup lifecycle manager: Handles agent creation, session activation,
   and teardown automatically. Reuses existing agents across sessions.

3. Two graph patterns: The simple ReAct agent is sufficient for most use cases.
   The advanced custom graph shows how to build explicit recall/research/synthesize routing.

4. Cross-session by default: All memories stored via memanto_remember are immediately
   available in any future session.

## License

MIT
