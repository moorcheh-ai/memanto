# Memanto + LangGraph Integration

A customer support agent built with **LangGraph** that uses **Memanto** for persistent, cross-session memory.

## What This Demonstrates

- **Cross-Session Recall** — Tell the agent your name today, it remembers tomorrow
- **Typed semantic memory** — Stores facts, preferences, decisions with confidence scoring
- **Graph-based state management** — LangGraph's state machine routes queries through memory-aware nodes

## Architecture

```
User Input → Parse Intent → Memanto Lookup → LLM Reasoning → Memanto Store → Response
                                ↑                                  |
                          (yesterday's facts)              (today's new facts)
```

## Prerequisites

- Python 3.10+
- A [Moorcheh API key](https://console.moorcheh.ai/api-keys) (free tier)
- An [OpenRouter API key](https://openrouter.ai/keys) (for LLM)

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env — add MOORCHEH_API_KEY and OPENROUTER_API_KEY
```

## Demo: Cross-Session Recall

Run once (Session 1):
```bash
python run.py
# "Hi! I'm Alice. My favorite color is blue."
# Agent stores: "user_name=Alice", "preference:color=blue"
```

Run again (Session 2 — new conversation, same memories):
```bash
python run.py
# "What's my name and favorite color?"
# Agent recalls: "Your name is Alice. Your favorite color is blue!"
# This proves cross-session persistence!
```

## File Structure

```
examples/langgraph-memanto/
├── README.md           # This file
├── requirements.txt    # Dependencies
├── .env.example        # API key template
├── memory.py           # Memanto integration wrapper
└── run.py              # Interactive demo with cross-session recall
```
