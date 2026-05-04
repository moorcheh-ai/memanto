


# Enhanced Memory System for Memanto

This directory contains the enhanced memory system for Memanto's agentic memory.

## Overview

The enhanced memory system provides:

1. Extended memory record with additional fields (priority, importance, relevance, etc.)
2. Advanced memory validation with context-aware checks
3. Memory enrichment with temporal and relationship context
4. Memory querying with advanced filtering and ranking

## Files

- `memory.py`: Main enhanced memory system module
- `README.md`: This file

## Usage

```python
from src.memanto.memory import (
    EnhancedMemoryRecord,
    MemoryContext,
    MemoryEnrichmentService,
    create_enhanced_memory,
    create_memory_context
)

# Create an enhanced memory
memory = create_enhanced_memory(
    memory_type="fact",
    title="Important Fact",
    content="This is an important fact to remember",
    scope=memory_scope,
    actor_id="user_123",
    confidence=0.95,
    priority=0.8,
    importance=0.9
)

# Create a memory context
context = create_memory_context(
    user_confirmed=True,
    conversation_history=["Hello", "How are you?"],
    current_task="Remember important facts",
    agent_state={"priority_rules": [{"type": "fact", "priority": 0.8}]}
)

# Enrich the memory with context
enrichment_service = MemoryEnrichmentService()
enriched_memory = enrichment_service.enrich_memory(memory, context)
```

## Testing

Run the memory system tests:

```bash
cd /workspace/memanto
python -m pytest tests/test_memory.py -v
```

## Documentation

For more information, see the [CrewAI Integration Documentation](../../docs/crewai_integration.md) which includes documentation for the enhanced memory system.

