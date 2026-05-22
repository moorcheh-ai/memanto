# LangGraph + Memanto: Cross-Session Recall Demo

This example implements a small LangGraph workflow that stores a user preference in Memanto on Day 1, then retrieves it in a separate run on Day 2.

It satisfies the bounty's core technical requirement: **memory lives outside graph state and survives across sessions**.

## What this shows

- LangGraph state machine orchestration
- Memanto persistent memory writes (`remember`)
- Memanto semantic recall in a separate process (`recall`)
- A reproducible two-run "yesterday memory" test

## Setup

```bash
cd examples/langgraph-memanto
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../crewai-memory/.env.example .env
# Edit .env and set MOORCHEH_API_KEY
```

## Run the two-session demo

```bash
python run_day1.py
# close terminal or start a new shell session
python run_day2.py
```

Expected Day 2 output starts with:

```text
Cross-session recall success:
```

## Optional quick verifier

```bash
python verify_recall.py
```

## Files

- `memory_client.py`: Memanto client setup + agent/session lifecycle
- `run_day1.py`: LangGraph workflow that extracts and stores preference memory
- `run_day2.py`: LangGraph workflow that recalls and answers from memory
- `verify_recall.py`: End-to-end checker for cross-session recall

## Notes

- Uses `MEMANTO_AGENT_ID` env var (default: `langgraph-support-agent`) to keep a stable memory namespace across runs.
- If Day 2 says "No preference found," run Day 1 first with the same `MEMANTO_AGENT_ID`.

## Demo artifact placeholder

A short terminal GIF/video can be attached in the PR, showing `run_day1.py` then `run_day2.py` in separate sessions.
