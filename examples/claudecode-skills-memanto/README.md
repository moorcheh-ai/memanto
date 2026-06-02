# Claude Code + Memanto: Developer Skills Integration Example

This directory demonstrates how **Memanto** acts as a global, active memory companion across different developer skill/command executions (such as `/grill-with-docs`, `/tdd`, and `/handoff`). 

By integrating Memanto, developer tools can solve the **Context Fragmentation** problem. Instead of treating each terminal interaction as an isolated event, Memanto dynamically injects past architectural decisions, codebase quirks, and design preferences into current prompts, eliminating the need to repeat instructions.

---

## Key Concepts Demonstrated

1. **The Global Memory Hook** (`memory_hook.py`):
   A lightweight lifecycle hook that initializes Memanto using Moorcheh credentials, sets up a dedicated tool-pattern agent, and manages session state.

2. **Active Extraction**:
   On skill completion (`post_skill_execute`), the hook autonomously analyzes the interaction (prompt & generated output) to extract meaningful developer preferences, bug fixes, or architectural decisions, storing them in Memanto with custom categorization.

3. **Dynamic Injection**:
   On skill startup (`pre_skill_execute`), the hook queries Memanto for memories matching the active file path or task description, formatting the matches into a system constraint block injected directly into the LLM context.

---

## File Structure

```text
examples/claudecode-skills-memanto/
├── README.md               # This documentation file
├── requirements.txt        # Python dependency list
├── memory_hook.py          # The core MemantoSkillsHook class
├── skills_simulator.py     # CLI execution simulator (proves context persistence)
└── test_skills.py          # Unit tests verifying hook correctness
```

---

## Setup & Running the Simulator

### 1. Configure the Virtual Environment

Create a virtual environment and install requirements:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Your Moorcheh Credentials

Create/edit a `.env` file in the repository root or copy your Moorcheh API key:

```bash
export MOORCHEH_API_KEY="your-api-key-here"
```

### 3. Run the CLI Simulator

Execute the simulator to see the memory hook in action:

```bash
python3 skills_simulator.py
```

**What the Simulator does:**
- **Session 1 (/grill-with-docs)**: Simulates a developer specifying an architectural layout preference (e.g. strict preference for *Tailwind v4* and *Outfit* typography). The hook extracts this preference and saves it to Memanto.
- **Session 2 (/tdd)**: Simulates running a code generation skill in a new session on a different file. The hook automatically recalls the design preference from Session 1, injecting it as a system constraint so the LLM outputs compliant code without re-prompting.

### 4. Run the Unit Tests

Validate hook behavior using `pytest`:

```bash
pytest test_skills.py
```
