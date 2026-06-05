---
name: tdd
description: Enforce Test-Driven Development (TDD) cycle by writing tests first, verifying failure, coding, and refactoring. Connects to Memanto at startup to load past context and at completion to persist learned preferences.
---

# TDD Skill with Memanto Memory Connection

You must follow these steps strictly whenever this skill is invoked:

## Phase 1: Context Injection (Session Start Hook)
Before making any changes to the codebase:
> **Note:** The command below uses a path relative to your **project root** (not this skill file's
> location). Make sure you have completed **Step 4** of the setup in
> `examples/claudecode-skills-memanto/README.md` so that
> `examples/claudecode-skills-memanto/skills_hook.py` exists at your project root.
1. Run the Memanto startup hook command to retrieve existing guidelines, developer preferences, and design decisions relevant to the task:
   ```bash
   python examples/claudecode-skills-memanto/skills_hook.py start --skill tdd --task "$ARGUMENTS"
   ```
2. Read the command output. Under `🧠 MEMANTO ACTIVE SYSTEM CONSTRAINTS`, you will find list of memories (e.g. styling preferences, architectural rules). You **MUST** strictly adhere to these guidelines.

## Phase 2: Red-Green-Refactor Cycle
Implement the feature or fix using strict TDD discipline:
1. **Red**: Write a minimal failing unit test for the desired behavior. Do NOT touch production code yet. Run tests to verify they fail.
2. **Green**: Write the minimum amount of production code required to make the test pass. Run tests to verify they pass.
3. **Refactor**: Clean up the code, maintain formatting standards, and verify tests still pass.

## Phase 3: Active Ingestion (Session End Hook)
Once the task is successfully implemented and verified:
1. Compose a concise summary of the engineering choices, preferences, or rules established during this cycle. Example:
   *"Decided to use standard logging instead of prints. Noticed the user prefers async/await pattern for API fetches."*
2. Run the Memanto end hook command to record these outcomes for future terminal sessions:
   ```bash
   python examples/claudecode-skills-memanto/skills_hook.py end --skill tdd --summary "<your summary description here>"
   ```
