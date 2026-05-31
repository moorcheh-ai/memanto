# Memanto + LangGraph Integration Examples

This directory contains examples of using Memanto as the long-term memory layer for LangGraph agents.

## Examples

### 1. Customer Support Agent

A customer support agent that can remember past interactions with customers across different sessions.

**Key Features:**
- Remembers customer preferences and past issues
- References previous conversations when handling new tickets
- Builds a persistent customer knowledge base

**Directory:** `customer_support/`

### 2. Research Assistant

A research assistant that builds and references a knowledge base over multiple research sessions.

**Key Features:**
- Remembers research findings across sessions
- References previous research when exploring new topics
- Builds a persistent knowledge graph

**Directory:** `research_assistant/`

## How It Works

These examples demonstrate how Memanto integrates with LangGraph:

1. **Memory Storage**: LangGraph agents use Memanto's `remember` function to store important information
2. **Memory Retrieval**: Agents use `recall` to retrieve relevant memories based on context
3. **Cross-Session Persistence**: Memories stored in Memanto persist beyond single graph executions
4. **Temporal Context**: Agents can query memories with time-based relevance

## Running the Examples

1. Install dependencies:
   