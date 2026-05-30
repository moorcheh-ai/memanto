# Memanto + mattpocock/skills: Cross-Session Engineering Memory

> Solves **Context Fragmentation** across mattpocock/skills executions by making Memanto a global, active memory companion.

## Problem

When using `mattpocock/skills` commands like `/grill-with-docs`, `/tdd`, and `/handoff`, each terminal session starts with a blank slate. Architectural decisions made in one skill session are completely invisible to the next. You end up re-prompting the same preferences, re-stating the same conventions, and re-explaining the same decisions.

## Solution

This integration adds a **transparent memory layer** across all skill executions:

1. **Pre-hook (Dynamic Injection):** Before a skill executes, relevant engineering memories are recalled and injected as a system constraint.
2. **Post-hook (Active Extraction):** After a skill completes, engineering signals are extracted and stored for future sessions.
3. **Zero-touch operation:** Via Claude Code hooks, the memory layer works transparently across ALL skills.

## Quick Start

### Credential-Free Mode (Reviewer Safe)

```bash
python3 validate.py
python3 -m pytest test_skill_memory.py -v
python3 mattpocock_adapter.py list
```

### Production Mode (with Moorcheh API Key)

```bash
export MOORCHEH_API_KEY="your-key-here"
python3 install_hooks.py
python3 install_hooks.py --status
```

## Files

| File | Purpose |
|------|---------|
| `memory_backend.py` | Protocol-based backend (Local JSONL + Memanto SDK) |
| `skill_memory.py` | Core lifecycle hooks: pre-hook + post-hook |
| `claude_hooks.py` | Native Claude Code hook handlers |
| `install_hooks.py` | Idempotent installer for ~/.claude/settings.json |
| `mattpocock_adapter.py` | CLI adapter with skill manifest and wrapper generation |
| `validate.py` | Credential-free validation script |
| `generate_sources.py` | Source file validation script |
| `test_skill_memory.py` | Comprehensive test suite |
| `README.md` | This file |

## How It Works

### Signal Extraction

The post-hook scans skill I/O for engineering signals:

| Pattern | Memory Type | Confidence |
|---------|-------------|------------|
| must/always/shall/never X | instruction | 0.90 |
| decided/chose/agreed to X | decision | 0.85 |
| prefer/favor/standard is X | preference | 0.75 |
| pattern/convention/approach is X | decision | 0.80 |

### Memory Injection

The pre-hook recalls relevant memories and formats them:

```text
## Engineering Memory Context (from Memanto)
The following are your established engineering decisions and preferences. Honor them.

- [DECISION] Use event sourcing for orders [architecture] (confidence: 85%)
- [INSTRUCTION] Must always use aggregate roots [tdd, implementation] (confidence: 90%)
```

### Cross-Session Flow

```text
Session 1: /grill-with-docs "Design the order system"
  Post-hook: Stores DECISION + INSTRUCTION memories

Session 2: /tdd "Implement the Order aggregate"
  Pre-hook: Recalls "Use event sourcing" and "aggregate roots"
  No re-prompting needed!

Session 3: /handoff "Next session will work on billing"
  Pre-hook: Recalls all engineering decisions + preferences
  Handoff document includes established architecture
```

## Showcase

Demo: <https://github.com/moorcheh-ai/memanto/tree/main/examples/claudecode-skills-memanto>

## Key Differentiators

1. **Claude Code native hooks** - Zero-touch via UserPromptSubmit, Stop, PostToolUse
2. **Protocol-based backend** - LocalBackend (credential-free) + MemantoBackend (live SDK)
3. **Weighted signal extraction** - Calibrated confidence scores per signal type
4. **Skill-aware tag boosting** - Domain-specific tags for each mattpocock skill
5. **Full lifecycle coverage** - Pre-hook + post-hook + file-reference capture
6. **Idempotent installer** - Safe to run repeatedly, auto-backups settings

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| MOORCHEH_API_KEY | (none) | When set, uses live SDK backend |
| MEMANTO_AGENT_ID | skills-memory-companion | Agent ID for SDK |
| MEMANTO_SKILLS_DATA | ~/.memanto/skills-memory | Local backend data dir |

## References

- Bounty issue: [#508](https://github.com/moorcheh-ai/memanto/issues/508)
- mattpocock/skills: <https://github.com/mattpocock/skills>
- Moorcheh API: <https://moorcheh.ai>
