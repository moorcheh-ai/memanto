# MEMANTO CLI User Guide

**Status**: Production Ready
**Last Updated**: December 2025

---

## Table of Contents

1. [Introduction](#introduction)
2. [Installation](#installation)
3. [Quick Start](#quick-start)
4. [Command Reference](#command-reference)
5. [Workflows](#workflows)
6. [Configuration](#configuration)
7. [Troubleshooting](#troubleshooting)
8. [Examples](#examples)

---

## Introduction

MEMANTO CLI provides a command-line interface for interacting with MEMANTO (Memory that AI Agents Love!). It enables you to:

- Create and manage AI agents
- Store and retrieve agent memories
- Upload documents and files into an agent's memory namespace
- Perform semantic search across memories
- Ask questions using RAG (Retrieval-Augmented Generation)
- Manage agent sessions

The CLI uses the MEMANTO API with session-based authentication and provides a beautiful terminal UI powered by Rich.

---

## Installation

### Prerequisites

- Python 3.10 or higher
- MEMANTO REST API server (optional, only if using HTTP endpoints)
- Moorcheh API key (required for cloud connectivity)

### Install Dependencies

```bash
cd memanto
pip install -e .
```

This installs:
- typer (CLI framework)
- rich (terminal UI)
- httpx (HTTP client)
- cryptography (secure key storage)
- pyyaml (configuration)
- All other MEMANTO dependencies

### Verify Installation

```bash
python -m cli.main --help
```

You should see the main help screen with all available commands.

---

## Quick Start

### 1. Initialize the CLI

```bash
memanto
```

This will:
- Prompt for your Moorcheh API key
- Securely encrypt and store the key
- Test connection to the MEMANTO server
- Create configuration file at `~/.memanto/config.yaml`

**Interactive Example:**
```
╭──────────────────────────────────────────╮
│ MEMANTO CLI Initialization                 │
│ Setting up your MEMANTO configuration...   │
╰──────────────────────────────────────────╯

Enter your Moorcheh API key: ********

Testing connection to MEMANTO server...
✓ Connection successful!
Server version: 0.1.0

Configuration saved to: /home/user/.memanto/config.yaml

Next steps:
  1. Create and activate an agent: memanto agent create my-agent
  2. Start storing memories: memanto remember 'your memory here'
```

### 2. Create and Activate an Agent

```bash
memanto agent create my-agent --pattern tool
```

This creates the agent and starts a session immediately (default: 6 hours). You don't need to run `agent activate` manually after creation.

### 3. Store a Memory

```bash
memanto remember "Implemented authentication using JWT tokens" \
  --type decision \
  --tags "authentication,security" \
  --confidence 0.9
```

### 4. Search Memories

```bash
memanto recall "authentication" --limit 5
```

### 5. Ask a Question

```bash
memanto answer "How did we implement authentication?"
```

---

## Command Reference

### Global Commands

#### Use base command for Initialization
 
 ```bash
 memanto [OPTIONS]
 ```
 
 **Options:**
- `--version` - Show installed MEMANTO version and exit
 
 **Example:**
 ```bash
 memanto
 ```

---

### Agent Commands

#### `agent create` - Create and Activate New Agent

```bash
memanto agent create AGENT_ID [OPTIONS]
```

**Arguments:**
- `AGENT_ID` - Unique identifier for the agent

**Options:**
- `--pattern TEXT` - Agent pattern: project, support, or tool (default: tool)
- `--description TEXT` - Optional description

**Behavior:**
1. Creates the agent namespace in Moorcheh.
2. Automatically activates a session for the new agent (default: 6 hours).
3. Saves the session token to your local configuration.

**Examples:**
```bash
# Create and activate a tool-using agent
python -m cli.main agent create code-assistant --pattern tool

# Create and activate a support agent with description
memanto agent create researcher \
  --pattern support \
  --description "Agent for customer support and ticket triage"
```

#### `agent list` - List All Agents

```bash
memanto agent list
```

**Output:**
```
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ Agent ID        ┃ Pattern ┃ Description             ┃ Status   ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━┩
│ code-assistant  │ tool    │ Code assistant          │ 🟢 Active│
│ researcher      │ support │ Support assistant       │          │
└─────────────────┴─────────┴────────────────────────┴──────────┘
```

#### `agent activate` - Activate Agent

```bash
memanto agent activate AGENT_ID [OPTIONS]
```

**Arguments:**
- `AGENT_ID` - ID of agent to activate

**Options:**
- `--duration-hours INT` - Session duration in hours (default: 6)

**Examples:**
```bash
# Activate with default 6-hour session
python -m cli.main agent activate code-assistant

# Activate with 8-hour session
memanto agent activate code-assistant --duration-hours 8
```

#### `agent deactivate` - Deactivate Current Agent

```bash
memanto agent deactivate
```

Clears the active session pointer in local CLI configuration.

> Note: This local CLI action and API session termination are different layers.
> To explicitly end a server-side API session, call `POST /api/v2/agents/{agent_id}/deactivate`.

#### `agent delete` - Delete Agent

```bash
memanto agent delete AGENT_ID [OPTIONS]
```

**Arguments:**
- `AGENT_ID` - ID of the agent to delete

**Options:**
- `--force, -f` - Skip confirmation prompt (default: false)

**Behavior:**
1. Shows a red confirmation warning (skipped with `--force`)
2. Asks whether to keep cloud memories — free storage accessible at [console.moorcheh.ai/namespaces](https://console.moorcheh.ai/namespaces)
3. If the agent has an active session, it is cleared automatically
4. Deletes the local agent metadata with a loading spinner
5. If cloud purge was chosen, also deletes the Moorcheh namespace (with spinner)

> **Note:** Choosing to keep cloud memories means your agent's memories remain safely stored in Moorcheh and can be accessed or re-linked at any time.

**Examples:**
```bash
# Delete with interactive prompts
memanto agent delete my-agent

# Force delete, skip confirmation (still asks about cloud memories)
memanto agent delete my-agent --force
```

---

### Memory Commands

#### `remember` - Store Memory

```bash
memanto remember CONTENT [OPTIONS]
```

**Arguments:**
- `CONTENT` - Memory content to store

**Options:**
- `--type, -t TEXT` - Memory type: fact, decision, instruction, commitment, event (default: fact)
- `--title TEXT` - Memory title (defaults to truncated content)
- `--confidence, -c FLOAT` - Confidence score 0.0-1.0 (default: 0.8)
- `--tags TEXT` - Comma-separated tags

**Examples:**
```bash
# Store a simple fact
python -m cli.main remember "User prefers dark mode"

# Store a decision with metadata
python -m cli.main remember "Switched to PostgreSQL for better JSON support" \
  --type decision \
  --title "Database Migration Decision" \
  --confidence 0.95 \
  --tags "database,architecture,postgresql"

# Store a commitment
python -m cli.main remember "Must complete security audit by end of month" \
  --type commitment \
  --tags "security,deadline"
```

**Output:**
```
✓ Memory stored successfully!
Memory ID: mem_abc123xyz
Type: decision | Confidence: 0.95
```

#### `upload` - Upload a File to Memory

```bash
memanto upload FILE_PATH
```

**Arguments:**
- `FILE_PATH` - Path to the file to upload

**Supported formats:** `.pdf`, `.docx`, `.xlsx`, `.json`, `.txt`, `.csv`, `.md`

The file is processed by Moorcheh — its content is chunked and embedded, making it instantly searchable via `memanto recall`. When you recall memories, file-sourced results are labelled `· file upload · summary` or `· file upload · chunk` in the panel title so you can distinguish them from manually stored memories.

**Examples:**
```bash
# Upload a PDF document
memanto upload report.pdf

# Upload a markdown file
memanto upload SECURITY.md
```

**Output:**
```
OK File uploaded successfully!
File: SECURITY.md
Size: 0.01 MB
Namespace: agent:my-agent
Completed in 3.21s
```

---

#### `recall` - Search Memories

```bash
memanto recall QUERY [OPTIONS]
```

**Arguments:**
- `QUERY` - Search query (semantic search)

**Options:**
- `--limit, -n INT` - Maximum results (default: `recall_limit` from config, factory default 10)
- `--type, -t TEXT` - Filter by memory type
- `--min-confidence FLOAT` - Minimum confidence score
- `--tags TEXT` - Filter by tags (comma-separated)

**Examples:**
```bash
# Basic search
python -m cli.main recall "authentication"

# Search with filters
python -m cli.main recall "security" \
  --type decision \
  --min-confidence 0.8 \
  --limit 5

# Search by tags
python -m cli.main recall "architecture" \
  --tags "database,backend" \
  --limit 20
```

**Output:**
```
Found 3 memories:

╭─ Memory 1 ──────────────────────────────────────────╮
│ Database Migration Decision                         │
│                                                      │
│ Switched to PostgreSQL for better JSON support      │
│ and advanced indexing capabilities...               │
│                                                      │
│ Type: decision | Confidence: 0.95 | Score: 0.927    │
│ Created: 2025-12-27T14:30:00Z                       │
╰─────────────────────────────────────────────────────╯

╭─ Memory 2 ──────────────────────────────────────────╮
│ ...                                                  │
╰─────────────────────────────────────────────────────╯
```

#### `answer` - RAG Question Answering

```bash
memanto answer QUESTION [OPTIONS]
```

**Arguments:**
- `QUESTION` - Question to ask

**Options:**
- `--limit, -n INT` - Number of context memories to use (default: `answer_limit` from config, factory default 5)

**Examples:**
```bash
# Ask about project decisions
memanto answer "Why did we choose PostgreSQL?"

# Ask with more context
memanto answer "What security measures have we implemented?" --limit 10
```

**Output:**
```
╭─ RAG Response ──────────────────────────────────────╮
│ Question: Why did we choose PostgreSQL?             │
│                                                      │
│ Answer:                                              │
│ We chose PostgreSQL because it provides better      │
│ JSON support and advanced indexing capabilities     │
│ compared to our previous database solution...       │
╰─────────────────────────────────────────────────────╯

Used 3 memories as context:
  1. Database Migration Decision (score: 0.927)
  2. Backend Architecture Review (score: 0.854)
  3. Performance Optimization Notes (score: 0.781)
```

---

### Session Commands

#### `session info` - Show Session Info

```bash
memanto session info
```

**Output:**
```
┏━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Property       ┃ Value                          ┃
┡━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ Agent ID       │ code-assistant                 │
│ Session Token  │ eyJhbGciOiJIUzI1NiI...         │
└────────────────┴────────────────────────────────┘
```

### Configuration Commands

#### `config show` - Display Configuration

```bash
memanto config show
```

**Output:**
```
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Setting          ┃ Value                        ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ Config File      │ /home/user/.memanto/config.yaml│
│ Server URL       │ localhost:8000               │
│ API Key          │ ***configured***             │
│ Active Agent     │ code-assistant               │
│ Session Active   │ yes                          │
│ Interactive Mode │ True                         │
│ Smart Parse      │ True                         │
└──────────────────┴──────────────────────────────┘
```

---

## Workflows

### Daily Development Workflow

```bash
# Morning: Activate your agent
memanto agent activate dev-assistant

# Throughout the day: Store important decisions and facts
memanto remember "Fixed authentication bug in login endpoint" \
  --type decision \
  --tags "bugfix,authentication"

memanto remember "User requested dark mode feature" \
  --type instruction \
  --tags "feature-request,ui"

# Review day's work
memanto recall "today" --limit 20

# End of day: Deactivate
memanto agent deactivate
```

### Project Knowledge Base

```bash
# Store architecture decisions
memanto remember "Using microservices architecture with API gateway" \
  --type decision \
  --title "Architecture Pattern" \
  --tags "architecture,microservices" \
  --confidence 1.0

# Store team guidelines
memanto remember "All PRs require 2 approvals before merge" \
  --type instruction \
  --tags "process,code-review"

# Query the knowledge base
memanto answer "What are our code review requirements?"
```

### Research Assistant

```bash
# Create and auto-activate support agent
memanto agent create support-assistant --pattern support

# Store research findings
memanto remember "Paper XYZ shows 30% improvement in model accuracy" \
  --type fact \
  --tags "research,ml,paper-xyz" \
  --confidence 0.9

# Search research by topic
memanto recall "model accuracy improvements" --limit 10

# Synthesize findings
memanto answer "What papers discuss model accuracy improvements?"
```

---

## Configuration

### Configuration File Location

- **Linux/Mac**: `~/.memanto/config.yaml`
- **Windows**: `C:\Users\<username>\.memanto\config.yaml`

### Configuration Structure

```yaml
version: "2.0"

server:
  url: "localhost"
  port: 8000
  auto_start: false

moorcheh:
  api_key_encrypted: "gAAAAABf..."  # Fernet encrypted

session:
  default_duration_hours: 6
  auto_extend: true

cli:
  interactive_mode: true
  smart_parse: true
  color_output: true
  compact_view: false

# Answer configuration (all optional — defaults shown)
answer:
  model: "anthropic.claude-sonnet-4-6"  # LLM used for answer
  temperature: 0.7        # LLM temperature (0.0–1.0)
  answer_limit: 5         # context memories passed to LLM for `answer`
  threshold: 0.01         # default threshold for non-kiosk answer calls

# Recall configuration
recall:
  limit: 10               # top-N results returned by `recall`

active_agent_id: "code-assistant"
active_session_token: "eyJhbGciOiJIUzI1NiI..."
```

### Security

- API keys are encrypted using Fernet (symmetric encryption)
- Encryption key stored in `~/.memanto/.key` with 0600 permissions
- Session tokens stored in config but require valid API key
- Never commit config files to version control

---

## Troubleshooting

### "MEMANTO not configured" Error

**Problem**: Running commands before setup

**Solution**:
```bash
memanto
```

### "No active agent" Error

**Problem**: Trying to use memory commands without active session

**Solution**:
```bash
# List available agents
memanto agent list

# Activate one
memanto agent activate <agent-id>
```

### Connection Failed

**Problem**: Cannot reach Moorcheh/MEMANTO services.

**Check**:
1. **Network**: Do you have internet access? (CLI talks directly to Moorcheh Cloud).
2. **API Key**: Is your key valid?
   ```bash
   memanto config show
   ```

3. **Reconfigure**:
   ```bash
   # Re-run setup and enter your new key when prompted
   memanto
   ```

### API Key Issues

**Problem**: Invalid or expired API key

**Solution**:
```bash
# Get new API key from Moorcheh dashboard
# Reconfigure by running setup again
memanto
```

### Session Expired

**Problem**: Session token expired

**Solution**:
```bash
# Reactivate the agent
memanto agent activate <agent-id>
```

---

## Examples

### Complete Project Setup

```bash
# 1. Setup
memanto

# 2. Create and auto-activate project-specific agent
memanto agent create project-alpha --pattern tool \
  --description "Agent for Project Alpha development"

# 3. (Optional) Reactivate or change duration
memanto agent activate project-alpha --duration-hours 8

# 4. Store initial context
memanto remember "Project uses Python 3.11, FastAPI, PostgreSQL" \
  --type fact \
  --title "Tech Stack" \
  --tags "project-setup,stack"

memanto remember "API versioning using /api/v2/ prefix" \
  --type decision \
  --tags "api,architecture"

# 5. Work session...
memanto remember "Implemented user authentication with JWT" \
  --type decision \
  --tags "auth,security"

# 6. Review progress
memanto recall "authentication security" --limit 5

# 7. Get context for next task
memanto answer "What have we implemented for security so far?"
```

### Multi-Agent Workflow

```bash
# Development agent
memanto agent create dev --pattern tool
memanto agent activate dev
memanto remember "Implemented feature X" --type fact

# Switch to support agent (auto-activates)
memanto agent deactivate
memanto agent create support --pattern support
memanto remember "Found paper on optimization technique Y" --type fact

# Switch back
memanto agent deactivate
memanto agent activate dev
```

### Bulk Knowledge Import

```bash
#!/bin/bash
# import-knowledge.sh

AGENT_ID="knowledge-base"

# Activate agent
memanto agent activate $AGENT_ID

# Import facts from file
while IFS='|' read -r title content tags; do
  memanto remember "$content" \
    --title "$title" \
    --type fact \
    --tags "$tags" \
    --confidence 1.0
done < knowledge.txt

echo "Import complete!"
```

---

## Advanced Usage

### Scripting with MEMANTO CLI

```python
#!/usr/bin/env python3
import subprocess
import json

def memanto_cli(*args):
    """Helper to call MEMANTO CLI"""
    cmd = ["memanto"] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

# Store multiple memories
memories = [
    ("Decision A", "fact", "tag1,tag2"),
    ("Decision B", "decision", "tag2,tag3"),
]

for title, mem_type, tags in memories:
    memanto_cli("remember", title, "--type", mem_type, "--tags", tags)

# Search and process
results = memanto_cli("recall", "decision", "--limit", 10)
print(results)
```

---

## Next Steps

1. **Integration**: Use MEMANTO CLI in your development workflow
2. **Automation**: Create scripts for common tasks
3. **Team Adoption**: Share configuration patterns with team
4. **Monitoring**: Track memory growth and query patterns

For more information:
- [API Documentation](./API_REFERENCE.md)
- [Agent Patterns](./AGENT_RUNTIME_GUIDE.md)
- [Memory Best Practices](./AGENT_MEMORY_BEST_PRACTICES.md)

---

**Last Updated**: December 2025
