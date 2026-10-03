# MEMANTO Agent Integration Guide

**For AI Coding Assistants, Chatbots, and Automation Agents**

**Integration Time**: 30 seconds | **Understanding Time**: 5 minutes

---

## Why MEMANTO for AI Agents?

AI agents need memory to provide context-aware, personalized responses. MEMANTO gives your agent:

- **Instant memory** - Remember user preferences, decisions, and context
- **Zero setup** - 3 commands to start using
- **Simple CLI** - No HTTP APIs, no complex SDKs, just shell commands
- **Persistent context** - Works across sessions, conversations, and workflows

---

## Quick Start (3 Commands)

```bash
# 1. Create/Activate your agent
memanto agent create your-agent-id
# OR if already created:
# memanto agent activate your-agent-id

# 2. Remember something
memanto remember "User prefers dark mode" --type preference --source your-agent-id

# 3. Recall it later
memanto recall "dark mode"
```

**That's it!** Your agent now has persistent memory.

---

## Installation

### Users Install MEMANTO

```bash
# Install MEMANTO
pip install memanto

# Setup environment with Moorcheh API key
memanto

# Optional: Start MEMANTO REST API server
# (Only needed if you want to use the REST API endpoints elsewhere)
memanto serve
```

**Note**: No local server is required for CLI commands. Your agent just calls `memanto` commands directly.

---

## Integration Pattern: Python Agents

### Python Client (Recommended)

`pip install memanto` includes an in-process Python client. It creates the agent on first use and reuses the agent's live session, so there is no `agent create` / `activate` step:

```python
from memanto import Memanto

memory = Memanto(agent_id="your-agent-id")

memory.remember("User prefers dark mode", type="preference", tags=["ui"])
memory.recall("dark mode", limit=5)        # {"memories": [...], ...}
memory.answer("What theme does the user prefer?")  # {"answer": "...", ...}
```

Full reference: [Python SDK](https://docs.memanto.ai/sdk/python).

### Alternative: Shell Out to the CLI

```python
import subprocess
import json

class AgentMemory:
    """Simple MEMANTO integration for AI agents"""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        # Create/Activate agent session
        # Use 'create' if new, or 'activate' if existing.
        # This example assumes activation for an existing agent.
        subprocess.run(["memanto", "agent", "activate", agent_id], check=True)

    def remember(self, content: str, memory_type: str = "fact", tags: str = None, confidence: float = 0.8, provenance: str = "explicit_statement", source: str = None):
        """Store a memory"""
        source = source or self.agent_id
        cmd = ["memanto", "remember", content, "--type", memory_type, "--confidence", str(confidence), "--provenance", provenance, "--source", source]
        if tags:
            cmd.extend(["--tags", tags])
        subprocess.run(cmd, check=True)

    def recall(self, query: str, limit: int = 5):
        """Search memories"""
        result = subprocess.run(
            ["memanto", "recall", query, "--limit", str(limit)],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout if result.stdout else ""

    def ask(self, question: str):
        """Ask a question (RAG)"""
        result = subprocess.run(
            ["memanto", "answer", question],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout if result.stdout else ""

# Usage
memory = AgentMemory("my-assistant")
memory.remember("User prefers Python over JavaScript", "preference")
results = memory.recall("programming language preference")
answer = memory.ask("What language does the user prefer?")
```

---

## Common Use Cases

### 1. Remember User Preferences

```python
# When user mentions a preference
memory.remember("User prefers dark mode", "preference", tags="ui,settings")
memory.remember("User likes email over phone", "preference", tags="communication")

# Before responding, check preferences
prefs = memory.recall("user preference communication")
if prefs:
    print(f"User prefers: {prefs[0]['content']}")
```

**Why**: Personalize responses without asking repetitive questions.

---

### 2. Get Context Before Response

```python
# At start of conversation, get recent context
context = memory.recall("recent conversation user", limit=10)

# Build context-aware prompt
prompt = f"""
Previous context:
{context[0]['content'] if context else 'No previous context'}

User message: {user_message}
"""
```

**Why**: Maintain conversation continuity across sessions.

---

### 3. Learn from Corrections

```python
# When user corrects you
def handle_correction(user_correction: str):
    memory.remember(
        f"User correction: {user_correction}",
        "learning",
        tags="correction,improvement"
    )

# Before similar task, check learnings
learnings = memory.recall("learning correction", limit=5)
```

**Why**: Improve over time by remembering mistakes.

---

### 4. Track Project Decisions

```python
# Record architectural decision
memory.remember(
    "Decision: Use PostgreSQL for database. Rationale: Team has expertise.",
    "decision",
    tags="architecture,database"
)

# Before changing architecture, check decisions
decisions = memory.recall("database architecture decision")
if decisions:
    print(f"Existing decision: {decisions[0]['content']}")
```

**Why**: Prevent re-litigating settled decisions.

---

### 5. Store Error Solutions

```python
# When you solve an error
def store_error_solution(error_msg: str, solution: str):
    memory.remember(
        f"Error: {error_msg}\nSolution: {solution}",
        "error",
        tags="debugging,solution"
    )

# When similar error occurs
similar_errors = memory.recall(error_msg, limit=3)
if similar_errors:
    print(f"Similar error solved: {similar_errors[0]['content']}")
```

**Why**: Reuse solutions for recurring problems.

---

## Memory Types

Use the right `memory_type` for better organization:

| Type | Use For | Example |
|------|---------|---------|
| `fact` | General information | "User's name is Sarah" |
| `preference` | User preferences | "Prefers dark mode" |
| `instruction` | User's standing instructions | "Always use TypeScript" |
| `decision` | Project decisions | "Chose React over Vue" |
| `event` | Conversation turns | "User asked about API" |
| `goal` | User goals | "Build a mobile app" |
| `commitment` | Promises made | "Will deploy by Friday" |
| `observation` | Patterns noticed | "User codes late at night" |
| `learning` | Lessons learned | "User prefers short responses" |
| `error` | Error solutions | "Fixed CORS issue with..." |

---

## Advanced: Async Integration

For async agents (Discord bots, web servers):

```python
import asyncio

class AsyncAgentMemory:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        asyncio.run(self._activate())

    async def _activate(self):
        proc = await asyncio.create_subprocess_exec(
            "memanto", "agent", "activate", self.agent_id
        )
        await proc.wait()

    async def remember(self, content: str, memory_type: str = "fact", confidence: float = 0.8, provenance: str = "explicit_statement", source: str = None):
        source = source or self.agent_id
        proc = await asyncio.create_subprocess_exec(
            "memanto", "remember", content, "--type", memory_type, "--confidence", str(confidence), "--provenance", provenance, "--source", source
        )
        await proc.wait()

    async def recall(self, query: str, limit: int = 5):
        proc = await asyncio.create_subprocess_exec(
            "memanto", "recall", query, "--limit", str(limit),
            stdout=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        return stdout.decode() if stdout else ""

# Usage in async context
async def handle_message(user_message: str):
    memory = AsyncAgentMemory("discord-bot")
    context = await memory.recall("recent conversation")
    # ... use context in response
```

---

## Other Languages

### JavaScript/Node.js

```javascript
const { execSync } = require('child_process');

class AgentMemory {
  constructor(agentId) {
    this.agentId = agentId;
    execSync(`memanto agent activate ${agentId}`);
  }

  remember(content, type = 'fact', confidence = 0.8, provenance = 'explicit_statement', source = this.agentId) {
    execSync(`memanto remember "${content}" --type ${type} --confidence ${confidence} --provenance ${provenance} --source ${source}`);
  }

  recall(query, limit = 5) {
    const output = execSync(`memanto recall "${query}" --limit ${limit}`);
    return output.toString();
  }
}

// Usage
const memory = new AgentMemory('my-bot');
memory.remember('User prefers npm over yarn', 'preference');
const prefs = memory.recall('package manager');
```

### Shell Scripts

```bash
#!/bin/bash

# Activate agent
memanto agent activate my-script

# Remember something
memanto remember "Backup completed successfully" --type event --tags "backup,cron" --source "my-script"

# Recall recent backups
memanto recall "backup" --limit 5

# Ask question
memanto answer "When was the last successful backup?"
```

---

## Complete Example: Customer Support Bot

```python
import subprocess
import json
from typing import List, Dict

class SupportBot:
    def __init__(self, bot_id: str = "support-bot"):
        self.bot_id = bot_id
        subprocess.run(["memanto", "agent", "activate", bot_id], check=True)

    def handle_customer_message(self, customer_id: str, message: str) -> str:
        """Handle customer message with context awareness"""

        # 1. Get customer context (preferences + history)
        context = self._get_customer_context(customer_id)

        # 2. Check for preferences
        preferred_name = None
        preferred_contact = None


        # Simplified parsing for string context
        if "prefers to be called" in context.lower():
            # This is a very naive parsing for a string, but keeps the example syntactically valid
            parts = context.lower().split('prefers to be called')
            if len(parts) > 1:
                preferred_name = parts[1].split(',')[0].strip() # Extract name after "called"
        if "prefers email" in context.lower():
            preferred_contact = 'email'


        # 3. Generate personalized response
        greeting = f"Hi {preferred_name}!" if preferred_name else "Hi there!"
        response = f"{greeting} I can help with that."

        if preferred_contact:
            response += f" I'll follow up via {preferred_contact}."

        # 4. Store this interaction
        self._store_interaction(customer_id, message, response)

        return response

    def learn_preference(self, customer_id: str, preference: str):
        """Store customer preference"""
        subprocess.run([
            "memanto", "remember",
            f"Customer {customer_id}: {preference}",
            "--type", "preference",
            "--tags", f"customer,{customer_id}"
        ], check=True)

    def _get_customer_context(self, customer_id: str) -> str:
        """Get customer context"""
        result = subprocess.run([
            "memanto", "recall",
            f"customer {customer_id}",
            "--limit", "10"
        ], capture_output=True, text=True, check=True)

        return result.stdout if result.stdout else ""

    def _store_interaction(self, customer_id: str, message: str, response: str):
        """Store interaction"""
        subprocess.run([
            "memanto", "remember",
            f"Customer {customer_id} asked: {message}\nBot responded: {response}",
            "--type", "event",
            "--tags", f"customer,{customer_id},interaction"
        ], check=True)

# Usage
bot = SupportBot()

# Day 1: Learn customer preference
bot.learn_preference("sarah-123", "Prefers to be called Sarah, not Ms. Williams")
bot.learn_preference("sarah-123", "Prefers email over phone calls")

# Day 2: Customer returns
response = bot.handle_customer_message(
    "sarah-123",
    "I need help with my order"
)
print(response)
# Output: "Hi Sarah! I can help with that. I'll follow up via email."
```

---

## Error Handling

```python
def safe_remember(content: str, memory_type: str = "fact"):
    """Robust memory storage with error handling"""
    try:
        subprocess.run(
            ["memanto", "remember", content, "--type", memory_type],
            check=True,
            timeout=5,  # 5 second timeout
            capture_output=True
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to store memory: {e.stderr.decode()}")
        return False
    except subprocess.TimeoutExpired:
        print("MEMANTO timeout - is server running?")
        return False

def safe_recall(query: str, limit: int = 5):
    """Robust memory recall with error handling"""
    try:
        result = subprocess.run(
            ["memanto", "recall", query, "--limit", str(limit)],
            capture_output=True,
            text=True,
            check=True,
            timeout=5
        )
        return result.stdout if result.stdout else ""
    except subprocess.CalledProcessError:
        return ""
    except subprocess.TimeoutExpired:
        return []
    except json.JSONDecodeError:
        return []
```

---

## Best Practices

# Good
subprocess.run(["memanto", "agent", "create", "my-agent"], check=True) # Automatically activates
subprocess.run(["memanto", "remember", "content"], check=True)

# Also good (if already created)
subprocess.run(["memanto", "agent", "activate", "my-agent"], check=True)
subprocess.run(["memanto", "remember", "content"], check=True)

# Bad - no active agent
subprocess.run(["memanto", "remember", "content"], check=True)  # ERROR!
```

### 2. Use Descriptive Tags
```python
# Good - searchable tags
memory.remember("User prefers dark mode", "preference", tags="ui,theme,dark-mode")

# Bad - no tags
memory.remember("User prefers dark mode", "preference")
```

### 3. Check Context Before Responding
```python
# Good - context-aware
context = memory.recall("user preference")
if context:
    # Use context in response
    pass

# Bad - no context check
# Always responding generically
```

### 4. Store Conversations
```python
# Good - store both sides
memory.remember(
    f"User: {user_msg}\nAgent: {agent_response}",
    "event",
    tags="conversation"
)

# Bad - only store user message
memory.remember(user_msg, "event")
```

---

## Troubleshooting

### "No active agent" Error

**Problem**: Trying to remember/recall without activating agent

**Solution**:
```python
# Create if it doesn't exist (auto-activates)
subprocess.run(["memanto", "agent", "create", "your-agent"], check=True)
# OR activate if it already exists
subprocess.run(["memanto", "agent", "activate", "your-agent"], check=True)
```

### "Connection failed" Error

**Problem**: MEMANTO server not running

**Solution**: User needs to run `memanto serve` in a terminal

### Empty Results

**Problem**: Recall returns no results

**Check**:
1. Is agent activated?
2. Have you stored any memories?
3. Is query relevant to stored content?

```python
# List all agents to verify
result = subprocess.run(["memanto", "agent", "list"], capture_output=True, text=True)
print(result.stdout)
```

---

## Next Steps

1. **Copy the basic integration code** above
2. **Test with 3 quick commands**:
   ```python
   memory = AgentMemory("test-agent")
   memory.remember("Test memory", "fact")
   print(memory.recall("test"))
   ```
3. **Add to your agent's initialization**
4. **Start using in production**

---

## Full Documentation

- **[CLI User Guide](CLI_USER_GUIDE.md)** - Complete command reference
- **[Quick Start](V2_QUICK_START.md)** - REST API (if you need HTTP)
- **[Session Architecture](SESSION_ARCHITECTURE.md)** - How MEMANTO works

---

## Support

**Questions?** See [CLI_USER_GUIDE.md](CLI_USER_GUIDE.md) or [Quick Start](V2_QUICK_START.md)

**MIT License** | **December 2025**

