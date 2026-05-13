# 🧠 Memanto + LangGraph: Multi-Agent Cognitive Architecture

[![LangGraph](https://img.shields.io/badge/LangGraph-✅_Compatible-blue)](https://langchain-ai.github.io/langgraph/)
[![Memanto](https://img.shields.io/badge/Memanto-✅_Powered-purple)](https://memanto.ai/)
[![No LLM Required](https://img.shields.io/badge/LLM-Free-❌_No_Key_Needed-green)]()
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-yellow)](https://python.org)

> **A multi-agent LangGraph system where three specialized agents (Support, Research, Coordinator) collaborate through a shared Memanto long-term memory layer — remembering information across completely separate sessions, threads, and agent instances.**

## ✨ What Makes This Different

| Feature | This Demo | Other Solutions |
|---------|-----------|-----------------|
| **Multi-Agent** | 🤝 3 agents (Support + Research + Coordinator) sharing memory | Single-agent only |
| **No LLM Key** | ✅ Fully deterministic — works offline with `--preview` | Requires OpenAI/Anthropic key |
| **Memory Isolation** | 🧩 Each agent has private + shared memory space | Single memory pool |
| **Cross-Session** | 🔄 Run `--mode seed`, `exit`, `--mode query` — same recall | In-memory only |
| **Conflict Detection** | ⚠️ Cloud: auto-detect conflicting memories | Not available |
| **Time Travel** | 🕐 `recall_as_of()` — what did we know last week? | Fresh state only |

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Coordinator                       │
│  (Classify, Route, Consolidate — no memory)         │
└────┬──────────────────────┬─────────────────────────┘
     │                      │
┌────▼──────────┐   ┌──────▼──────────┐
│  Support      │   │  Research       │
│  (user-facing)│   │  (knowledge)    │
│  Memanto mem  │   │  Memanto mem    │
└────┬──────────┘   └──────┬──────────┘
     │                      │
┌────▼──────────────────────▼──────────┐
│       Shared Collaboration Space     │
│  Cross-agent memory (shared agent)   │
└─────────────────────────────────────┘
```

## 🚀 Quick Start

### No API Key? No problem:

```bash
# Run the full demo with local preview store
python run_demo.py --preview

# Cross-session recall demo
python run_demo.py --mode seed --preview
python run_demo.py --mode query --preview
```

### With Memanto Cloud:

```bash
cp .env.example .env
# Edit .env with your MOORCHEH_API_KEY
python run_demo.py --no-preview
```

## 🧪 What It Demonstrates

### 1. Cross-Session Memory 🌉
The agent remembers information from "yesterday" across separate invocations:

```bash
# Session 1
$ python run_demo.py --mode seed --preview
📝 Session 1: Seeding memories...
✅ Seeded 4 memories across 3 agent spaces!

# Session 2 (completely new process)
$ python run_demo.py --mode query --preview
🔍 Session 2: Querying cross-session memories...
🗣️  What do you know about me?
     [PREFERENCE] Fav language: User loves Python with type hints
     [FACT] Current project: Building a LangGraph agent with Memanto memory
```

### 2. Multi-Agent Collaboration 🤖🔬🤝
Three agents share information through a coordinated memory system:

- **Support Agent**: Remembers user preferences and past conversations
- **Research Agent**: Maintains a knowledge base of researched topics
- **Shared Space**: Cross-agent decisions and architecture notes

### 3. Memory Conflict Detection ⚠️
When cloud mode is enabled, Memanto automatically detects conflicting
memories (e.g., "User prefers Python" vs "User avoids Python").

### 4. Time-Travel Recall 🕐
The `recall_as_of()` method shows what the agent knew at any point in time.

## 📋 Available Commands

| Input | Action |
|-------|--------|
| "Remember that I use Python" | Store a memory |
| "What do you know about me?" | Recall all memories |
| "Help me with [topic]" | Route to Support Agent |
| "Research [topic]" | Route to Research Agent |
| "Consolidate memories" | Generate memory summary |

## 📁 File Structure

```
examples/langgraph-memanto/
├── run_demo.py              # Demo runner (seed/query/full)
├── langgraph_memory_graph.py # LangGraph graph definition
├── memanto_adapter.py        # Memanto ↔ LangGraph bridge
├── requirements.txt          # Dependencies
├── .env.example              # API key template
├── README.md                 # This file
└── demo.gif                  # Demo recording (see below)
```

## 🔧 How It Works

1. **`MemantoAdapter`** wraps Memanto's `remember`, `recall`, `answer` primitives
   in a LangGraph-friendly interface. In `--preview` mode, it uses a local JSON
   file instead of the Memanto cloud API.

2. **`langgraph_memory_graph.py`** defines the multi-agent LangGraph with:
   - `classify_intention` — keyword-based routing (no LLM needed)
   - `support_node` — user-facing support with memory context
   - `research_node` — knowledge base management
   - `memory_remember` / `memory_recall` — direct memory ops
   - `consolidate_memories` — cross-agent summary

3. **Three Memanto agent IDs** provide memory isolation:
   - `memanto-langgraph-support-agent` — Support's private memory
   - `memanto-langgraph-research-agent` — Research's private memory
   - `memanto-langgraph-shared-space` — Cross-agent collaboration

## 📸 Demo

[![Demo GIF](demo.gif)](demo.gif)
*(Record with your favorite screen recorder and replace `demo.gif`)*