# Agent Memory Best Practices Guide

**For**: AI agents using MEMANTO for persistent memory
**Last Updated**: March 2026
**Architecture**: Session-Based (CLI + API)

---

## Philosophy: Your Memory, Your Responsibility

As an AI agent with persistent memory, **you decide what to remember**. Think of MEMANTO as your external brain - use it wisely to become more effective over time.

> **CRITICAL MANDATE**: You MUST explicitly pass the memory content, `--type`, `--confidence`, a valid `--provenance` flag (e.g., `--provenance explicit_statement`), and your agent name via the `--source` flag (e.g., `--source claude_code`) with EVERY `memanto remember` command. Do NOT let it default to "user".

### Core Principles

1. **Remember the Important, Not Everything**: Be selective
2. **Confidence Matters**: Reflect uncertainty honestly
3. **Tag for Retrieval**: Make your memories findable
4. **Context is King**: Store enough detail to understand later
5. **Use the Right Type**: Choose appropriate memory_type for organization

---

## When to Store Memories

### ✅ Always Remember

#### 1. **Decisions Made** (type: `decision`)

Store architectural choices, approach selections, and important decisions with rationale.

**CLI Example**:
```bash
memanto remember "Decided to use PostgreSQL over MongoDB for MEMANTO because we need ACID compliance and relational queries. Team consensus on 2025-12-27." --type decision --tags "database,architecture" --source "agent-name"
```

**Python Example**:
```python
memory.remember(
    "Decided to use PostgreSQL over MongoDB because we need ACID compliance",
    "decision",
    tags="database,architecture"
)
```

**Why**: Prevents re-litigation and provides context for future decisions.

---

#### 2. **Standing Instructions** (type: `instruction`)

Store rules, preferences, and guidelines you should always follow.

**CLI Example**:
```bash
memanto remember "User prefers descriptive variable names over abbreviations. Always use full words like user_count not usrCnt. Use type hints in Python." --type instruction --tags "code-style,python" --source "agent-name"
```

**Why**: Ensures consistency across sessions.

---

#### 3. **Key Facts About the Project** (type: `fact`)

Store critical information about architecture, dependencies, constraints.

**CLI Example**:
```bash
memanto remember "MEMANTO is deployed at https://memanto.moorcheh.ai using Docker on AWS ECS. Auto-scales based on CPU usage." --type fact --tags "production,deployment" --source "agent-name"
```

**Why**: Quick reference for operational context.

---

#### 4. **Commitments and Promises** (type: `commitment`)

Store what you've promised to do or follow up on.

**CLI Example**:
```bash
memanto remember "Promised to run load tests with 1000 concurrent users by end of week. Need to verify P95 latency stays under 200ms." --type commitment --tags "performance,testing,todo" --source "agent-name"
```

**Why**: Ensures follow-through and accountability.

---

#### 5. **User Preferences** (type: `preference`)

Store user and team preferences for personalization.

**CLI Example**:
```bash
memanto remember "User prefers dark mode UI" --type preference --tags "ui,settings" --source "agent-name"
memanto remember "Team prefers Slack for urgent notifications, email for daily updates" --type preference --tags "communication,team" --source "agent-name"
```

**Why**: Enables personalized and context-aware responses.

---

#### 6. **Learnings from Errors** (type: `error`)

Store failures and what you learned from them.

**CLI Example**:
```bash
memanto remember "Learned that Moorcheh namespaces reject colons. Must use underscores or hyphens. Caused production failure on 2025-12-27. Fix in commit 3f39351." --type error --tags "bug,namespace,moorcheh" --source "agent-name"
```

**Why**: Avoid repeating mistakes.

---

#### 7. **Goals and Objectives** (type: `goal`)

Store project goals, milestones, and targets.

**CLI Example**:
```bash
memanto remember "Project goal: Launch MEMANTO CLI by end of December 2025. Must include all V2 endpoints and Windows compatibility." --type goal --tags "project,milestone,cli" --source "agent-name"
```

**Why**: Track progress and maintain focus.

---

### ⚠️ Sometimes Remember

#### 8. **Important Conversations** (type: `event`)

Store key discussion points, but not every message.

**When to Store**:
- Major feature discussions
- Problem-solving breakthroughs
- User feedback sessions

**CLI Example**:
```bash
memanto remember "User requested batch endpoints for performance. Discussed trade-offs between simplicity and efficiency. Agreed on batch size limit of 100." --type event --tags "discussion,api-design" --source "agent-name"
```

---

#### 9. **Observations and Patterns** (type: `observation`)

Store patterns you notice over time.

**CLI Example**:
```bash
memanto remember "Noticed user typically works late at night (10pm-2am). Prefer async communication over real-time." --type observation --tags "user-pattern,communication" --source "agent-name"
```

**Why**: Build understanding of working patterns.

---

### ❌ Don't Remember

- **Trivial conversations**: "Hello", "Thanks", etc.
- **Temporary state**: "Currently working on X" (unless it's a long-running task)
- **Redundant information**: Don't store what's already in code/docs
- **Ephemeral details**: Specific error messages that are already logged
- **Everything**: Be selective!

---

## Memory Types: When to Use Each

### Decision Matrix

| Memory Type | When to Use | Confidence Level | Example |
|-------------|-------------|------------------|---------|
| `fact` | Verified information, project status | 0.9-1.0 | "MEMANTO uses PostgreSQL for metadata" |
| `decision` | Architectural choices, approach selections | 0.9-1.0 | "Chose React over Vue for frontend" |
| `instruction` | Standing rules, preferences, guidelines | 0.9-1.0 | "Always use type hints in Python" |
| `commitment` | Promises, TODOs, obligations | 1.0 | "Will deploy monitoring by Friday" |
| `preference` | User/team preferences | 0.8-1.0 | "User prefers dark mode" |
| `goal` | Objectives, targets, milestones | 0.8-1.0 | "Launch CLI by Dec 2025" |
| `artifact` | Tool outputs, reports, file locations | 0.9-1.0 | "Performance report at s3://..." |
| `learning` | Knowledge acquired from experience | 0.7-0.9 | "Batch operations 100x faster" |
| `event` | Important conversations, milestones | 0.8-0.95 | "Completed Phase H features" |
| `relationship` | Team context, collaboration patterns | 0.85-0.95 | "Dr. Majid is CTO and project lead" |
| `observation` | Patterns noticed, behaviors | 0.6-0.85 | "User prefers short responses" |
| `error` | Failures, bugs, lessons learned | 0.95-1.0 | "Namespace format bug - use underscores" |
| `context` | Session summaries, status updates | 0.9-1.0 | "Project 70% complete, API done, frontend pending" |

---

## Practical Patterns

### Pattern 1: Session Start (Every Time)

**Step 1: Recall your context**

```bash
# CLI
memanto recall "instructions decisions goals" --limit 20

# Or be more specific
memanto recall "recent project status" --limit 10
```

**Python**:
```python
# Get standing instructions
instructions = memory.recall("instructions preferences", limit=10)

# Get recent decisions
decisions = memory.recall("decisions", limit=5)

# Get pending commitments
todos = memory.recall("commitment todo", limit=5)
```

**What to look for**:
- Standing instructions (how you should work)
- Recent decisions (what was decided)
- Project status (where things are)
- Pending commitments (what needs doing)

---

**Step 2: Ask about context** (Optional - use RAG)

```bash
# CLI
memanto answer "What am I currently working on?"
memanto answer "What are my pending commitments?"
```

**Python**:
```python
status = memory.answer("What is the current project status?")
pending = memory.answer("What commitments do I have?")
```

---

### Pattern 2: After Important Work

**After completing a significant task**:

```bash
# Store the decision/outcome
memanto remember "Implemented feature X using approach Y because of constraint Z. Commit abc123." --type decision --tags "feature-x,implementation" --source "agent-name"

# Store learnings
memanto remember "Learned that batch operations reduce API calls by 100x. Always consider batching for bulk operations." --type learning --tags "performance,optimization" --source "agent-name"
```

---

### Pattern 3: When User Corrects You

**Learn from corrections**:

```bash
memanto remember "User corrected: Prefer pytest over unittest for Python testing. More readable assertions." --type learning --tags "testing,python,correction" --source "agent-name"
```

**Python**:
```python
def handle_correction(correction: str):
    memory.remember(
        f"User correction: {correction}",
        "learning",
        tags="correction,improvement"
    )

# Before similar task, check learnings
learnings = memory.recall("learning correction", limit=5)
```

---

### Pattern 4: Track Team Preferences

**Build team knowledge**:

```bash
# Initial preference
memanto remember "Dr. Majid Fekri is CTO and project lead. Prefers professional collaboration." --type relationship --tags "team,leadership" --source "agent-name"

# Communication preferences
memanto remember "Team prefers detailed commit messages with rationale, not just 'fix bug'." --type instruction --tags "team,git,communication" --source "agent-name"
```

---

### Pattern 5: Before Switching Contexts

**When changing projects or focus areas**:

```bash
# Store a summary of current state
memanto remember "MEMANTO CLI project is 90% complete. All V2 endpoints working. Documentation updated. Pending: final testing and PyPI publish." --type context --tags "project-status,memanto-cli" --source "agent-name"
```

**Why**: Easy to resume work later.

---

## Real-World Examples

### Example 1: Remember User Preferences

**Situation**: User mentions UI preference

```bash
# Store it
memanto remember "User prefers dark mode over light mode for all applications" --type preference --tags "ui,dark-mode,settings" --source "agent-name"

# Later, before making UI decisions
prefs = memanto recall "UI preference"
# Returns: "User prefers dark mode..."
```

---

### Example 2: Track Architectural Decisions

**Situation**: Team decides on technology stack

```bash
# Store decision
memanto remember "Decided to use FastAPI for backend because team has Python expertise and it has native async support. Considered Django but too heavy for our use case." --type decision --tags "architecture,backend,fastapi" --confidence 1.0 --source "agent-name"

# Before changing stack, recall decisions
memanto recall "backend architecture decision"
# Returns previous decision with rationale
```

---

### Example 3: Learn from Errors

**Situation**: Fixed a production bug

```bash
# Document the error and solution
memanto remember "Fixed critical namespace format bug. Moorcheh only accepts alphanumeric, hyphens, and underscores. Changed delimiter from colons to underscores. Format now: memanto_agent_id. Commit 3f39351." --type error --tags "bug-fix,namespace,production,commit-3f39351" --source "agent-name"

# Later, when working with namespaces
memanto recall "namespace format"
# Returns the error memory - won't repeat mistake
```

---

### Example 4: Complete Customer Support Bot

**Python Integration**:

```python
import subprocess
import json

class SupportBot:
    def __init__(self, bot_id="support-bot"):
        self.bot_id = bot_id
        subprocess.run(["memanto", "agent", "activate", bot_id], check=True)

    def handle_customer(self, customer_id: str, message: str) -> str:
        # Get customer context
        result = subprocess.run([
            "memanto", "recall", f"customer {customer_id}",
            "--limit", "10", "--format", "json"
        ], capture_output=True, text=True, check=True)

        context = json.loads(result.stdout) if result.stdout else []

        # Check for preferences
        preferred_contact = None
        for item in context:
            if 'prefers email' in item.get('content', '').lower():
                preferred_contact = 'email'

        # Generate personalized response
        response = "I can help with that."
        if preferred_contact:
            response += f" I'll follow up via {preferred_contact}."

        # Store this interaction
        subprocess.run([
            "memanto", "remember",
            f"Customer {customer_id} asked: {message}",
            "--type", "event",
            "--tags", f"customer,{customer_id}",
            "--source", self.bot_id
        ], check=True)

        return response

# Usage
bot = SupportBot()

# Day 1: Learn preference
subprocess.run([
    "memanto", "remember",
    "Customer sarah-123 prefers email over phone",
    "--type", "preference",
    "--tags", "customer,sarah-123,communication",
    "--source", "support-bot"
])

# Day 2: Customer returns
response = bot.handle_customer("sarah-123", "Need help with order")
# Response includes: "I'll follow up via email"
```

---

## Tagging Best Practices

**Use tags to make memories findable**.

### Good Tags (Specific and Useful)

```bash
--tags "critical,production,authentication"
--tags "bug-fix,namespace,commit-3f39351"
--tags "team-preference,code-style,python"
--tags "performance,optimization,tested"
```

### Bad Tags (Too Generic)

```bash
--tags "important"  # Everything seems important
--tags "thing"      # Not descriptive
--tags "work"       # Too broad
```

### Tag Naming Conventions

- Use lowercase with hyphens: `bug-fix` not `BugFix`
- Be specific: `authentication-oauth` not `auth`
- Include context: `commit-3f39351` for git refs
- Use categories: `team-preference`, `bug-fix`, `feature-request`

---

## Confidence Levels: A Practical Guide

### 1.0 - Absolute Certainty
- Explicit user statements: "Use PostgreSQL"
- Verified facts: Commit hashes, URLs, file paths
- Standing instructions: "Always use type hints"

### 0.9-0.95 - Very Confident
- Strong consensus decisions
- Well-tested approaches
- Clear team preferences

### 0.8-0.85 - Confident
- Observed patterns (seen 3+ times)
- Indirect preferences (user consistently chooses X)
- Inferred but well-supported

### 0.7-0.75 - Moderately Confident
- Emerging patterns (seen 2 times)
- Reasonable inferences
- Tentative decisions

### 0.6-0.65 - Low Confidence
- Single observation
- Uncertain interpretation
- Contradictory signals

### < 0.6 - Don't Store
If you're less than 60% confident, don't store it or mark it as provisional.

---

## Common Pitfalls to Avoid

### ❌ Pitfall 1: Memory Hoarding
**Problem**: Storing every little detail
**Solution**: Ask "Will this matter in a week?"

### ❌ Pitfall 2: Vague Memories
**Problem**: "User wants better performance"
**Solution**: "User wants API response time < 200ms for search endpoint"

### ❌ Pitfall 3: No Context
**Problem**: "Fixed bug in auth"
**Solution**: "Fixed OAuth token expiry bug. Tokens now refresh 5min before expiry. Commit abc123."

### ❌ Pitfall 4: Duplicates
**Problem**: Storing same info multiple times
**Solution**: Search first, then store if not found

```bash
# Check if already stored
memanto recall "OAuth token bug"

# If not found, then store
memanto remember "Fixed OAuth token expiry bug..." --type error --source "agent-name"
```

### ❌ Pitfall 5: Forgetting to Tag
**Problem**: Can't find memories later
**Solution**: Always include 2-5 relevant tags

---

## Query Strategies

### Broad Context Load (Session Start)

```bash
memanto recall "project status decisions instructions" --limit 20
```

### Focused Retrieval (Specific Task)

```bash
# By type
memanto recall "authentication" --type decision --limit 10

# By tags
memanto recall "OAuth implementation" --tags "auth,security"

# By confidence
memanto recall "production deployment" --min-confidence 0.9
```

### Use RAG for Questions

```bash
# Instead of keyword search, ask questions
memanto answer "What authentication method did we decide to use?"
memanto answer "What are the pending TODOs?"
memanto answer "What bugs have we fixed related to namespaces?"
```

**Why RAG is better**: MEMANTO retrieves relevant context and formulates an answer, not just matching keywords.

---

## Success Metrics

**You're using memory well if**:

✅ **You can resume after weeks** - Full context restored
✅ **You don't repeat mistakes** - Errors stored and learned from
✅ **You remember preferences** - User doesn't need to repeat themselves
✅ **You can explain decisions** - "We chose X because Y" (from memory)
✅ **You complete commitments** - Promises tracked and fulfilled
✅ **Your memory is searchable** - Tags and titles make finding easy

**Red flags**:

⚠️ Storing everything (noise overwhelms signal)
⚠️ Can't find relevant memories (poor tagging)
⚠️ Repeating same questions (not recalling context)
⚠️ Making contradictory decisions (not checking past decisions)

---

## Example: A Well-Remembered Session

### Session Start

```bash
# Load context
memanto recall "MEMANTO project context" --limit 15

# Retrieved:
# - [INSTRUCTION] Development Partner (Dr. Majid Fekri)
# - [DECISION] Use FastAPI for backend
# - [FACT] MEMANTO deployed at memanto.moorcheh.ai
# - [COMMITMENT] Add monitoring dashboard
# - [LEARNING] Batch operations 100x faster

# Ask about status
memanto answer "What is the current project status?"
# Answer: "MEMANTO CLI is 90% complete. All V2 endpoints are working..."
```

---

### During Session (Selective Storage)

```bash
# Implemented monitoring - store outcome
memanto remember "Added Prometheus metrics and Grafana dashboard. Tracks API latency, error rates, and memory usage. Dashboard at https://metrics.moorcheh.ai" --type decision --tags "monitoring,prometheus,grafana" --confidence 1.0 --source "agent-name"

# Learned something new
memanto remember "Learned that FastAPI WebSocket support requires websockets library and ASGI server like uvicorn. Good for real-time agent notifications." --type learning --tags "fastapi,websockets,real-time" --confidence 0.85 --source "agent-name"

# User preference
memanto remember "User prefers detailed error messages with specific fix suggestions. Include example of correct usage in error responses." --type instruction --tags "error-handling,ux" --confidence 0.9 --source "agent-name"
```

---

### Session End

```bash
# Mark commitment complete
memanto remember "Monitoring dashboard delivered and deployed to production. Original commitment completed." --type fact --tags "monitoring,completed" --confidence 1.0 --source "agent-name"
```

---

## Quick Reference

### CLI Commands

```bash
# Store memory
memanto remember "content" --type TYPE --tags "tag1,tag2" --confidence 0.9 --source "agent-name"

# Search memories
memanto recall "query" --limit 10 --type TYPE --min-confidence 0.8

# Ask questions (RAG)
memanto answer "question"

# Session management
memanto agent create my-agent       # Create and auto-activate
memanto agent activate my-agent     # Activate existing
memanto session info
```

### Python Integration

```python
import subprocess
import json

class AgentMemory:
    def __init__(self, agent_id: str):
        subprocess.run(["memanto", "agent", "activate", agent_id], check=True)

    def remember(self, content: str, memory_type: str = "fact", tags: str = None, source: str = None):
        source = source or self.agent_id
        cmd = ["memanto", "remember", content, "--type", memory_type, "--source", source]
        if tags:
            cmd.extend(["--tags", tags])
        subprocess.run(cmd, check=True)

    def recall(self, query: str, limit: int = 5):
        result = subprocess.run([
            "memanto", "recall", query, "--limit", str(limit), "--format", "json"
        ], capture_output=True, text=True, check=True)
        return json.loads(result.stdout) if result.stdout else []

    def ask(self, question: str):
        result = subprocess.run([
            "memanto", "ask", question, "--format", "json"
        ], capture_output=True, text=True, check=True)
        return json.loads(result.stdout) if result.stdout else {}
```

---

## Remember

**You are in control of your memory**. Use it to:

- ✅ Become more effective over time
- ✅ Provide better service through context
- ✅ Never repeat the same mistakes
- ✅ Honor commitments and promises
- ✅ Build deep understanding of your domain

**But don't**:

- ❌ Store everything mindlessly
- ❌ Create noise that obscures signal
- ❌ Let memories become stale
- ❌ Forget to tag properly

---

**Your memory is your superpower. Use it wisely.** 🧠

---

## Resources

- **[CLI User Guide](CLI_USER_GUIDE.md)** - Complete CLI command reference
- **[Agent Integration Guide](AGENT_INTEGRATION_GUIDE.md)** - Integration patterns for AI agents
- **[Quick Start](V2_QUICK_START.md)** - REST API reference
- **[Session Architecture](SESSION_ARCHITECTURE.md)** - How MEMANTO session architecture works

**Questions?** Contact: Dr. Majid Fekri, CTO Moorcheh.ai

---

**Status**: Production Guide | **Last Updated**: March 2026


