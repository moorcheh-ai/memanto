# 🐜 Memanto + LangGraph Integration

This example demonstrates how to give your LangGraph agents a **Permanent Brain** using Memanto as the long-term memory layer. 

By default, LangGraph is the gold standard for stateful agents, but its state is bound to the current thread/session. Memanto solves this by acting as a persistent semantic memory layer that survives across disjointed sessions.

## 🌟 Key Features
- **Cross-Session Recall**: The agent remembers facts and preferences from completely independent threads.
- **Tool-Based Integration**: Memanto is natively integrated as LangChain `tool` nodes (`remember` and `recall`), allowing the LLM to decide when to store and when to retrieve memories.
- **Zero-Latency Ingestion**: Memories are instantly available for recall without waiting for expensive graph reconstructions.

## 📺 Demonstration
The `agent.py` script runs a demo containing two completely separate LangGraph sessions:
1. **Session 1**: The user states a preference ("My favorite color is crimson red and I prefer very short answers"). The agent uses the `remember` tool to store this in Memanto.
2. **Session 2**: The LangGraph state is completely wiped. The user asks "What is my favorite color?". The agent uses the `recall` tool, retrieves the memory from Memanto, and answers correctly in a concise format!

## 🚀 How to Run

### 1. Install Dependencies
```bash
pip install memanto langgraph langchain-openai
```

### 2. Configure Memanto
You need a Moorcheh API key to use Memanto.
```bash
memanto
```
Follow the prompts to configure your environment.

### 3. Create and Activate an Agent Namespace
Create a dedicated agent namespace for this demo:
```bash
memanto agent create langgraph-demo-agent
memanto activate langgraph-demo-agent
```

### 4. Run the Agent
Make sure your OpenAI API key is set, then run the script!
```bash
export OPENAI_API_KEY="sk-your-key-here"
python agent.py
```

## 🏗️ Code Architecture
```python
# The agent is equipped with two straightforward tools:

@tool
def remember(memory_type: str, content: str) -> str:
    # Uses Memanto to permanently store facts, preferences, or goals.
    
@tool
def recall(query: str) -> str:
    # Uses Memanto's exact semantic search to pull relevant memories before answering.
```
The LLM dynamically reasons about when to call these tools based on the user's input, creating a seamless, persistent conversational experience.
