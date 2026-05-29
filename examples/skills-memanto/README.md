# Memanto + Developer Skills Integration

Memanto as a global memory companion across the mattpocock/skills ecosystem.

## Problem

Each CLI skill execution is isolated — context from one skill (e.g., architecture brainstorming with `/grill-with-docs`) is invisible when running another (e.g., implementing with `/tdd`).

## Solution

Memanto acts as a **persistent memory layer** that:
1. Automatically captures skill inputs and outputs
2. Distills engineering decisions and codebase knowledge
3. Injects relevant past context into new skill invocations

## Usage

```bash
# Wrap any skill execution:
python memanto_skill_wrapper.py --skill /grill-with-docs --query "auth flow"

# Or use full command syntax:
python memanto_skill_wrapper.py --execute "npx /tdd --framework vitest"

# View memory summary:
python memanto_skill_wrapper.py --summary
```

## How It Works

```
Skill Execution → Memanto captures context → Extracts key decisions → Stores in Brain
     ↑                                                                         ↓
     └─────────────── Future skills retrieve past context ─────────────────────┘
```
