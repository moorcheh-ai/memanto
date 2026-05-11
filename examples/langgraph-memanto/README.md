# LangGraph + Memanto: Cross-Session Memory Example

Demonstrates an AI assistant that **remembers user preferences and past conversations across sessions** using Memanto as the persistent memory layer.

## Quick Start

```bash
# Install memanto
pip install memanto

# Run the demo
python examples/langgraph-memanto/example.py
```

## What it demonstrates

| Feature | Description |
|---------|-------------|
| Cross-Session Recall | Agent remembers facts from "yesterday" across sessions |
| Preference Learning | Detects and stores user preferences (languages, tools, etc.) |
| Persistent Storage | Memory survives program restarts via JSON on disk |
| LangGraph-Style Nodes | `load_context → process_query → generate_response → save_memory` |

## Memory Architecture

```
User Query → [load_context_node] → loads Memanto memory
                 ↓
           [process_query_node] → extracts facts/preferences
                 ↓
          [generate_response_node] → personalized with memory
                 ↓
           [save_memory_node] → persists to Memanto
```

## Demo Output

```
📅 Session 1 (First visit):
  👋 Welcome! This is your first session.

📅 Session 2 (Returning user):
  👋 Welcome back! (Session #2)
  💡 Remembered: Hi! I'm Alice and I like Python

📅 Session 3 (Building memory):
  👋 Welcome back! (Session #3)
  💡 New preference stored: I use FastAPI
  🎯 Based on your preferences: here's something about Python
```

## Files

- `example.py` — Complete LangGraph workflow with Memanto adapter
- Output: `memanto_data/user_*_memory.json` — persisted memory files
