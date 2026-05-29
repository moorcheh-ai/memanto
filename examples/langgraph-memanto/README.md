# LangGraph + Memanto: Permanent Brain Integration

A LangGraph customer support agent with Memanto-powered long-term memory that persists across sessions.

## Features
- **Cross-Session Recall**: Agent remembers user facts from "yesterday" even in a fresh LangGraph thread
- **Memanto Memory Layer**: Stores/retrieves memories outside standard LangGraph state
- **Practical Demo**: Customer support agent that remembers preferences, past issues, and user context

## Architecture

```
User --> LangGraph State Machine --> Agent Response
                  |
            Memanto API
       (long-term memory store)
```

## Quick Start

```bash
pip install langgraph langchain-openai requests
python customer_support_agent.py
```

## Demo

```python
# Session 1
User: "My name is Alice and my order #12345 was delayed"
Agent: "Noted, Alice! I'll remember that."

# Session 2 (new LangGraph thread, same agent instance)
User: "What was my issue about?"
Agent: "Your order #12345 was delayed. How can I help?"
```

## Memory Architecture
- `store_memory(user_id, key, value)`: Saves facts to Memanto
- `recall_memories(user_id)`: Loads all saved facts for a user
- Automatic context injection into LangGraph system prompt
