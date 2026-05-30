# Memanto + Developer Skills

Global memory layer for [mattpocock/skills](https://github.com/mattpocock/skills).  
Persistence across skill executions, sessions, and tools.

## How it works

- **`scripts/memanto_memory.py`** — Python CLI backed by the Memanto platform
- **`SKILL.md`** — a skills‑ecosystem skill that tells Claude Code to use Memanto automatically

## Setup

```bash
# 1. Install the Python package
pip install memanto

# 2. Get a free API key at https://moorcheh.ai

# 3. Set the key
set MOORCHEH_API_KEY=sk-xxxxxxx

# 4. Initialise memory for this project
python scripts/memanto_memory.py init

# 5. (Optional) Install as a skill so Claude Code activates it automatically
npx skills add .
```

## Usage

```bash
# Store a memory
python scripts/memanto_memory.py remember "title" "content here"

# Search memories
python scripts/memanto_memory.py recall "search query"

# Ask a question (RAG)
python scripts/memanto_memory.py answer "what did we decide about X?"

# Show status
python scripts/memanto_memory.py status

# Recent history
python scripts/memanto_memory.py history
```

## How to contribute

Open an issue or PR at https://github.com/moorcheh-ai/memanto.
