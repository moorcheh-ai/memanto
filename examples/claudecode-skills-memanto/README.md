# Memanto Skills Companion for Claude Code

**A global, persistent cross-session memory layer for AI agent skills.**

This example demonstrates how to solve **Context Fragmentation** in modular developer workflows (like [mattpocock/skills](https://github.com/mattpocock/skills) or custom AI agent prompts) using **Memanto**.

---

## 🐜 The Problem: Context Fragmentation

Modular agent skills (like `/grill-with-docs`, `/tdd`, and `/handoff`) optimize productivity by focusing the LLM on a single task. However:
1. **No Cross-Session Memory**: If you use a skill to align on an architectural design, that vital context is lost when you start a fresh session to write the code.
2. **Repeated Instruction Fatigue**: You have to repeatedly tell the agent your style guides, framework choices, and codebase quirks.
3. **Forgotten Errors**: The agent might repeat a mistake that it resolved in a previous debugging session.

## 🧠 The Solution: Memanto Skills Companion

This integration layer acts as a global active memory companion. By running simple hook commands before and after skill execution, Memanto:
- **Autonomously Distills & Remembers**: Saves architectural decisions, developer preferences, lessons learned, and error resolutions when a session ends.
- **Dynamically Recalls & Injects**: Searches the persistent memory using semantic search before a new session starts, injecting relevant past engineering decisions directly into the workspace context.

---

## 🛠️ Setup

1. **Get an API Key**: Grab your free API key at [moorcheh.ai](https://moorcheh.ai/).
2. **Set Environment Variable**:
   ```bash
   export MOORCHEH_API_KEY="your_api_key_here"
   ```
3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

---

## 🚀 How to Use

The companion provides a single script, `memanto_skills.py`, which integrates into your CLI or shell hooks.

### 1. Start of Session (Dynamic Injection)
Before launching Claude Code or running a skill, query Memanto for relevant past engineering decisions and write them to the workspace context:
```bash
python memanto_skills.py start --task "Refactor the authentication endpoint to support OAuth2" --file "apps/api/auth.py"
```

This queries Memanto for memories matching the task and file path and generates a beautiful `.claude/skills_memory.md` file in your workspace containing:
- Codebase style guides
- Architecture decisions
- Preferred libraries and patterns
- Past errors avoided in this module

Your Claude Code skills can then reference `.claude/skills_memory.md` (e.g., in a `.clauderc` system prompt or by instructing the agent to read it first).

### 2. End of Session (Active Extraction)
When the session is complete, store the distilled insights, structural decisions, or preferences to Memanto so they are available next time:
```bash
python memanto_skills.py end --task "Refactor authentication" --summary "We replaced raw JWT tokens with OAuth2 bearer authentication, using the authlib library. The developer prefers using PyJWT only for decoding local tokens." --confidence 1.0 --tags "auth,jwt,oauth2"
```

Memanto will persist these decisions across all future sessions!

---

## 📊 Example Workflow Demo

To see cross-session persistence in action, run our simple automated simulation:
```bash
python test_skills.py
```

This simulation will:
1. **Session 1 (Design)**: Record architectural decisions about using a specific naming convention and caching mechanism.
2. **Session 2 (Implementation)**: Query Memanto with a new task to write the code, proving that the decisions from Session 1 are successfully recalled and injected.
