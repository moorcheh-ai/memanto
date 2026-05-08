# CrewAI + Memanto Agentic Memory Integration

This example demonstrates how to integrate **Memanto** as an active, persistent memory layer for **CrewAI** agents. 

CrewAI agents are incredibly powerful at reasoning, but by default, they suffer from "long-term amnesia" across sessions. By providing CrewAI agents with Memanto tools (`remember`, `recall`, `answer`), you give them a serverless, zero-latency semantic database that persists across tasks, sessions, and even entirely different AI Crews.

## 🚀 Scenario: Cross-Agent Memory Handoff

In this script, we simulate a standard organizational workflow:
1. **The Research Agent**: Discovers a critical technical constraint (e.g., "The app must use FastAPI and Vue.js"). Instead of just holding it in its local prompt context, it uses the `Memanto Remember Tool` to permanently store this fact into the Memanto semantic database.
2. **The Writer Agent**: Starts its task completely blank. It relies entirely on the `Memanto Recall Tool` (and `Memanto Answer Tool`) to query the database, fetch the constraints the Researcher saved, and draft an accurate project brief.

Because Memanto executes at zero ingestion latency, the Writer can immediately query the facts the Researcher just saved milliseconds prior.

## 🛠️ Setup Instructions

### 1. Install Dependencies
You need both `crewai` and `memanto` installed.
```bash
pip install crewai memanto
```

### 2. Configure Memanto
Before running the script, ensure your Memanto CLI is authenticated with your Moorcheh API key.
```bash
memanto
# Follow the prompt to enter your API key if you haven't already.

# Optional: Create a specific agent namespace for this demo
memanto agent create crewai-demo-agent
```

### 3. Run the Integration
```bash
python crewai_memanto_integration.py
```

## 🧠 How the Tools Work

We wrap the core Memanto CLI commands into CrewAI `@tool` decorators:

* **`memanto_remember(text, memory_type)`**: Wraps `memanto remember "..." --type ...`. Allows agents to actively decide *what* is important enough to save for the long term.
* **`memanto_recall(query)`**: Wraps `memanto recall "..."`. Allows agents to pull raw, exact semantic matches from their history before making a decision.
* **`memanto_answer(query)`**: Wraps `memanto answer "..."`. Allows agents to ask Memanto's built-in RAG to synthesize an answer from past memories, saving CrewAI context tokens.

## 📹 Visual Proof (Terminal Log Mockup)

```text
[Research Agent] Working on task...
[Research Agent] Using Tool: Memanto Remember Tool
[Research Agent] Tool Output: Successfully stored memory in Memanto: The new application MUST be built using FastAPI and Vue.js, and must deploy to AWS. (Type: fact)

... (Handoff) ...

[Writer Agent] Working on task...
[Writer Agent] Using Tool: Memanto Recall Tool
[Writer Agent] Tool Input: "What tech stack and deployment platform does the client require?"
[Writer Agent] Tool Output: Memanto recalled the following context: 
  - (Fact, 99.8% match): The new application MUST be built using FastAPI and Vue.js, and must deploy to AWS.

[Writer Agent] Finalizing Output...
```

*This integration provides a seamless bridge between CrewAI's reasoning engine and Memanto's SOTA information-theoretic retrieval.*