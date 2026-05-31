# Memanto Integration for LangGraph

**Persistent, cross-session long-term memory for stateful AI agents.**

This example demonstrates how to integrate **Memanto** with **LangGraph** to build a stateful AI Customer Support Agent that maintains durable, long-term memory across separate threads and conversation sessions.

---

## 🧠 The Problem: Thread-Scoped Memory Limits

LangGraph is the gold standard for building stateful multi-agent systems, but its default state checkpointers suffer from **session isolation**:
1. **Thread Fragmentation**: A user thread (e.g., `thread_123`) stores chat history, but when the user starts a fresh chat (e.g., `thread_456`), all past facts, user preferences, and agreed-upon decisions are completely wiped.
2. **Context Blowup**: Shoving entire past conversation histories into the LLM context to preserve memory quickly becomes token-expensive, slow, and prone to dilution.

## 🚀 The Solution: Memanto Long-Term Memory Layer

By introducing Memanto as a serverless, cross-session semantic memory layer, we give our LangGraph workflow a permanent brain:
- **Dynamic Context Recall (Pre-Node Hook)**: Before the assistant node generates a reply, it queries Memanto for memories relevant to the user and task, dynamically injecting them as a system constraint.
- **Active Memory Distillation (Post-Node Hook)**: At the end of the conversation loop, a dedicated node distills key preferences, structural decisions, or resolved complaints, persisting them to the Moorcheh backend.

```
                  ┌──────────────────────────────┐
                  │   User starts fresh thread   │
                  └──────────────┬───────────────┘
                                 │
                                 ▼
                  ┌──────────────────────────────┐
                  │    Recall Context Node       │ ◄─── (Semantic Search)
                  │  Queries Memanto for User   │
                  └──────────────┬───────────────┘
                                 │
                                 ▼
                  ┌──────────────────────────────┐
                  │    Generate Reply Node       │ (Tailored response based
                  │   Uses Injected Memories     │  on recalled preferences)
                  └──────────────┬───────────────┘
                                 │
                                 ▼
                  ┌──────────────────────────────┐
                  │    Extract Memory Node       │ ───► (Remember new choices)
                  │ Distills new facts to Memanto│
                  └──────────────────────────────┘
```

---

## 🛠️ Setup

1. **Moorcheh API Key**: Get your free API key at [moorcheh.ai](https://moorcheh.ai/).
2. **Environment Variable**:
   ```bash
   export MOORCHEH_API_KEY="your_api_key_here"
   ```
3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

---

## 📂 Codebase Structure

- `agent.py`: The LangGraph state schema, node definitions, and graph compilation.
- `run_simulation.py`: Interactive CLI script simulating a multi-day customer interaction showing cross-session persistence.
- `requirements.txt`: Project dependencies.

---

## 🎬 Automated Simulation

To see the agent remember details across completely independent threads, run:
```bash
python run_simulation.py
```

### The Scenario:
1. **Day 1 (Thread A)**: The user ("Alice") introduces herself, states she is using the **Premium Plan**, and shares her preference (*"I always prefer dark mode UIs"*). The agent resolves her query and distills this into Memanto.
2. **Day 2 (Thread B - Fresh State)**: Alice starts a completely new chat session. The agent dynamically recalls her profile and UI preferences, greeting her by name and addressing her premium plan immediately!
