# LangGraph + Memanto Example: Customer Support Agent

A LangGraph-powered customer support agent that uses **Memanto** as its long-term memory layer — storing, retrieving, and answering from memories that persist across disjointed sessions.

> **Note**: The core integration tools used in this example are published to PyPI as `langgraph-memanto`. For deep documentation on the architecture, setup instructions, and API details of the integration itself, please read the [langgraph-memanto package README](../../integrations/langgraph/README.md).

## Architecture



The workflow uses LangGraph's **conditional edges** to automatically route queries to the appropriate Memanto primitive based on LLM-based intent classification.

## What This Demonstrates

- **Cross-Session Recall**: The agent remembers findings from previous sessions that are not in the current thread's state
- **Typed Semantic Memory**: 13 memory types (fact, decision, goal, observation, etc.) for structured storage
- **AI-Driven Confidence Scoring**: The agent self-evaluates certainty before storing memories
- **Contradiction Detection**: Conflicting memories are flagged with versioning, not silently overwritten
- **Three Primitives**: `remember`, `recall`, and `answer` — LLM-grounded responses from memory
- **Intelligent Query Routing**: Automatic classification determines which Memanto operation to use

## Prerequisites

- Python 3.10+
- A [Moorcheh API key](https://console.moorcheh.ai/api-keys) (free tier: 100K ops/month)
- An [OpenAI API key](https://platform.openai.com/api-keys) or OpenRouter key

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your MOORCHEH_API_KEY and OPENAI_API_KEY
```

## Step-by-Step Demo (Proves Persistence)

```bash
# Step 1: Support agent stores customer context
python run_session1_store.py

# Step 2: Support agent recalls context in a NEW session
# (This proves memories persist across sessions!)
python run_session2_recall.py

# Step 3: Demonstrate contradiction handling
python run_contradiction_demo.py
```

## Session 1 Output

```
Session 1: Storing Customer Context in Memanto
============================================================

--- Query 1 ---
Input: Customer Alice Johnson prefers email communication...

Classification: remember
Tool result: Memory stored successfully. ID: mem-abc123...
Response: I've saved Alice's communication preference...

--- Query 2 ---
Input: Alice reported a billing discrepancy...

Classification: remember
Tool result: Memory stored successfully. ID: mem-def456...
Response: I've recorded the billing issue...
```

## Session 2 Output (different process, next day)

```
Session 2: Recalling Customer Context from Memanto
============================================================

--- Query 1 ---
Input: What do we know about Alice Johnson's preferences?

Classification: recall
Memory result: Found 3 memories for ‘Alice Johnson preferences’:
  1. [preference] Customer Alice Johnson prefers email...
  2. [fact] Alice Johnson has been a premium member...
Response: Based on our records, Alice prefers email...
```

## Alternative: ReAct Agent

```bash
python run_react_agent.py
```

This uses the same Memanto tools in a LangGraph ReAct agent, where the LLM autonomously decides which tool (remember/recall/answer) to call.

## File Structure

```text
examples/langgraph-memanto/
  README.md               # This file
  requirements.txt        # Python dependencies
  .env.example            # API key template
  run_session1_store.py   # Run 1: Store customer context
  run_session2_recall.py  # Run 2: Recall context (proves persistence)
  run_contradiction_demo.py # Bonus: contradictory memory handling
  run_react_agent.py      # Alternative: ReAct agent with Memanto tools
```
