# LangGraph + Memanto Cross-Session Memory Example

This example shows Memanto acting as a long-term memory layer for a
LangGraph workflow. LangGraph owns the short-lived state for the current run;
Memanto stores and recalls memories that survive across separate Python
processes.

## What It Demonstrates

- A LangGraph assistant that stores durable project decisions in Memanto.
- A second run that starts with no local graph state and recalls the earlier decision from Memanto.
- A tiny graph shape that is easy to inspect: recall, decide, persist.

The demo uses the same Memanto SDK client used by the existing CrewAI integration.

## Files

```text
examples/langgraph-memanto/
├── README.md
├── requirements.txt
├── .env.example
├── graph.py
├── run_day_1.py
└── run_day_2.py
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set `MOORCHEH_API_KEY` in `.env`.

## Demo Flow

Run day 1 to store a decision:

```bash
python run_day_1.py
```

Run day 2 in a separate process to prove cross-session recall:

```bash
python run_day_2.py
```

Expected behavior:

- Day 1 stores an architectural decision about using PostgreSQL for audit logs.
- Day 2 asks a fresh graph which audit-log storage it should use.
- The graph recalls the stored decision from Memanto and includes it in the response.

## Demo Recording

Video/GIF link: to be added before this PR is marked ready for review.

## Recording Checklist

The bounty requires a 30-second GIF or video link. Record:

1. `python run_day_1.py`
2. Close the terminal or start a fresh terminal.
3. `python run_day_2.py`
4. Show the recalled memory in the day 2 output.

## Notes

This is a focused example, not a framework wrapper. The goal is to make the memory boundary visible: LangGraph owns short-lived state, Memanto owns cross-session memory.
