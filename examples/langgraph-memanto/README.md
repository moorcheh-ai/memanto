# LangGraph + Memanto: Customer Support Agent with Permanent Memory

A LangGraph workflow that uses Memanto for cross-session long-term memory. The agent remembers user preferences, past issues, and resolved tickets across conversations.

## How it works

```
User Message → Classify Intent → Recall Memories (Memanto) → Build Context → Generate Response → Store Memory (Memanto)
```

- **classify_intent**: Detects intent (password_reset, billing, technical_issue, howto)
- **retrieve_memories**: Queries Memanto for past interactions from this user
- **build_context**: Formats recalled memories into context for the response
- **generate_response**: Produces contextual reply based on intent + memory
- **store_memory**: Saves this interaction to Memanto for future sessions

## Cross-Session Recall Demo

The agent stores every interaction in Memanto. When the same user returns with a new issue, the agent retrieves relevant past interactions — even from different sessions.

## Usage

```bash
# Install
pip install -r requirements.txt

# First conversation
python support_agent.py --user "alice" --message "I forgot my password"

# Next conversation (same user, different session)
python support_agent.py --user "alice" --message "The bug is still happening"
```

The second call will recall memories from the first conversation, demonstrating cross-session recall.

## Configuration

Set `MOORCHEH_API_KEY` env var for cloud-backed Memanto storage. Without it, the adapter uses local SQLite (same API, persistent across runs).

## Demo (30s GIF)

<!-- TODO: Add link to 30-second demo GIF showing:
  1. First conversation: user reports password issue
  2. Second conversation: user mentions recurring bug
  3. Agent recalls the password issue from the first conversation
-->
