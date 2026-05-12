# LangGraph + Memanto Integration: A Persistent Brain for Your Agent

This example demonstrates how to integrate [Memanto](https://memanto.ai) as a long-term memory solution for a [LangGraph](https://langchain-langgraph.github.io/langgraph/) agent. This allows your agent to store and retrieve "memories" that persist across different sessions, giving it a permanent brain beyond the immediate conversational state.

## 🧠 How it Works

The agent acts as a simple fact-storing and retrieval assistant:

1.  **Remember Facts**: When you tell the agent to "Remember: <fact>", it stores that fact in Memanto.
2.  **Retrieve & Respond**: When you ask a question, the agent queries Memanto for relevant past information and uses those memories to formulate its response.

Crucially, the Memanto integration ensures that these stored facts are available even if the agent script is restarted, demonstrating **cross-session recall**.

### Mock Memanto Client

For ease of demonstration and to avoid requiring a running Memanto service, this example uses a `PersistentMemantoClient` mock. This mock client saves and loads memories from a local `memanto_data.json` file, effectively simulating the persistence and retrieval capabilities of a real Memanto instance. In a production environment, you would replace this mock with the official Memanto client.

## 🚀 Getting Started

### 1. Fork and Clone

First, fork this repository and clone your fork:

```bash
git clone YOUR_FORK_URL
cd YOUR_FORK_URL/examples/langgraph-memanto
```

### 2. Install Dependencies

Install the required Python packages:

```bash
pip install -r requirements.txt
```

### 3. Run the Agent

Execute the agent script:

```bash
python agent.py
```

## ✨ Demonstration

Once running, you can interact with the agent:

1.  **Store a memory:**
    ```
    You: Remember: The capital of France is Paris.
    Agent: Okay, I've remembered: 'The capital of France is Paris.'.
    ```
2.  **Ask a question:**
    ```
    You: What is the capital of France?
    Agent: Based on what I recall:
    - The capital of France is Paris.
    Regarding your question: 'What is the capital of France?'
    I can try to use these memories to help.
    ```
3.  **Demonstrate Cross-Session Recall:**
    *   Exit the `agent.py` script (`exit`).
    *   Run `python agent.py` again.
    *   Ask the same question: `What is the capital of France?`
    *   The agent will still recall the fact, because it was loaded from `memanto_data.json`.

---

## 🎥 Video/GIF Demonstration

[Link to your 30-second GIF or video demonstrating the agent's functionality, especially cross-session recall.]
