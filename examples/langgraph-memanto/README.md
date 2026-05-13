# LangGraph + Memanto Example

This example shows how to use Memanto as a persistent long-term memory layer
for a LangGraph customer-support agent.

The demo is intentionally split into two runs:

1. `demo_day1.py` stores facts from a first customer conversation.
2. `demo_day2.py` starts a fresh process and recalls the earlier memories.

That split demonstrates cross-session recall: the LangGraph state is new on
day 2, but Memanto still remembers what the customer said on day 1.

## What This Demonstrates

- A LangGraph workflow that reads from and writes to Memanto.
- Cross-session recall outside of LangGraph's in-thread state.
- Typed memories for preferences, facts, events, and commitments.
- A deterministic fallback store for local dry-runs and unit tests.
- A small support-agent scenario that is easy to record as a 30-second demo.

## Architecture

```text
User message
    |
    v
LangGraph StateGraph
    |
    +--> recall_memories node -----> Memanto recall
    |
    +--> draft_response node ------> response grounded in recalled memories
    |
    +--> write_memory node --------> Memanto remember
```

Memanto is the durable memory system. LangGraph manages the per-run workflow
state. The two systems remain separate: restarting the graph clears transient
state, but the stored memories remain available.

## Setup

```bash
cd examples/langgraph-memanto
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

For a live Memanto run, set a Moorcheh API key:

```bash
set MOORCHEH_API_KEY=your_key_here
```

Without `MOORCHEH_API_KEY`, the demo uses `.memanto_local_store.json` as a
deterministic local fallback. The fallback is useful for reviewing the
LangGraph flow without external services, but the bounty demo should be
recorded with a real Memanto key.

## Run the Demo

```bash
python demo_day1.py
python demo_day2.py
```

Expected behavior:

- Day 1 stores the customer's timezone, plan, dashboard preference, and follow-up
  commitment.
- Day 2 asks a new question in a fresh process.
- The agent recalls day-1 memories and answers with the saved preference and
  follow-up details.

## Record a 30-Second Demo

Suggested flow:

1. Show `python demo_day1.py` storing the memories.
2. Close or clear the terminal.
3. Run `python demo_day2.py`.
4. Highlight that day 2 recalls the Enterprise plan, Europe/London timezone,
   dark dashboard preference, and Tuesday follow-up.

Add the video or GIF link to your PR description for bounty review.

## Files

```text
examples/langgraph-memanto/
├── README.md
├── demo_day1.py
├── demo_day2.py
├── memory_store.py
├── requirements.txt
└── support_agent.py
```

## Notes

- The live adapter uses `memanto.cli.client.sdk_client.SdkClient`.
- The fallback adapter is not a replacement for Memanto; it only keeps the
  example testable without external credentials.
- Keep support facts short and atomic so retrieval stays easy to inspect.
