---
name: grill-with-docs
description: Interview the developer to capture project context, requirements, and domain preferences. Integrates with Memanto memory hooks to skip redundant questions and save newly acquired domain details.
---

# Grill-with-Docs Skill with Memanto Memory Connection

You must follow these steps strictly when interviewing the developer:

## Phase 1: Context Injection (Session Start Hook)
Before starting the interview:
> **Note:** The command below uses a path relative to your **project root** (not this skill file's
> location). Make sure you have completed **Step 4** of the setup in
> `examples/claudecode-skills-memanto/README.md` so that
> `examples/claudecode-skills-memanto/skills_hook.py` exists at your project root.
1. Run the Memanto startup hook command to retrieve past architectural rules, project structures, and developer constraints:
   ```bash
   python examples/claudecode-skills-memanto/skills_hook.py start --skill grill-with-docs --task "$ARGUMENTS"
   ```
2. Read the outputted memories. Review what you already know about the project (e.g. databases used, frontend frameworks, naming conventions). **Do not ask the developer any questions about these already established facts.**

## Phase 2: Targeted Interview
Interview the developer to clarify only the new details or un-documented requirements for the task:
1. Ask sharp, direct questions.
2. Ground your questions in the existing project documents (`README.md`, `ARCHITECTURE.md`) and the memories injected in Phase 1.

## Phase 3: Active Ingestion (Session End Hook)
Once the developer provides the answers and you finalize the design:
1. Compose a detailed summary of the newly learned project context, framework selections, and structural decisions. Example:
   *"Project uses Docker for development. Backend relies on FastAPI. Port 8080 is reserved. Code must use snake_case for fields."*
2. Run the Memanto end hook command to record these facts:
> **Note:** Same as Phase 1 — this path is relative to your **project root**.
> Ensure **Step 4** of the README setup is complete before running this command.
   ```bash
   python examples/claudecode-skills-memanto/skills_hook.py end --skill grill-with-docs --summary "<your summary description here>"
   ```
