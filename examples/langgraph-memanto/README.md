# LangGraph + Memanto: Persistent Memory for Stateful Agents

A customer support agent built with [LangGraph](https://langchain-ai.github.io/langgraph/) and [Memanto](https://memanto.ai/) that remembers user preferences and past conversations across sessions.

## How It Works

LangGraph manages the conversation flow as a state graph. Memanto provides the long-term memory layer — preferences and context are stored outside the ephemeral LangGraph state and retrieved on subsequent sessions.

The graph has three nodes:
1. **load_memory** — fetches user preferences and recent context from Memanto
2. **process_query** — responds using the retrieved memory context
3. **store_memory** — saves new information back to Memanto

Cross-session recall is demonstrated in the simulation: a user sets a preference in "Session 1", then returns in "Session 2" with no local state — the agent remembers.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set your API key
cp .env.example .env
# Edit .env with your MOORCHEH_API_KEY

# 3. Run the simulation
python agent.py
```

## Example Output

```
SESSION 1: User sets a preference
SESSION 2 (next day): User returns with a new question
Agent recalls user prefers dark mode from cross-session memory.
```

## Demo Video

[Link to 30-second demo](https://your-demo-link-here.com)

## File Structure

| File | Purpose |
|------|---------|
| `agent.py` | LangGraph state graph definition + simulation |
| `memory.py` | Memanto wrapper for remember/recall/answer |
| `requirements.txt` | Python dependencies |
| `.env.example` | API key template |
