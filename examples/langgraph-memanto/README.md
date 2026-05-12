# 🧠 Memanto + LangGraph: Giving Your Graph a Permanent Brain

This example demonstrates how to integrate [Memanto](https://github.com/Moorcheh-AI/memanto) as a long-term memory layer for a [LangGraph](https://langchain.github.io/langgraph/) agent. It addresses the challenge of maintaining conversational context and factual recall across disjointed sessions, ensuring your agent "remembers" information from "yesterday" that isn't explicitly part of the current thread's state.

## ✨ Features

*   **Cross-Session Recall**: The agent remembers facts and preferences learned in previous interactions, even after the application restarts or new conversations begin.
*   **LLM-Powered Fact Extraction**: Uses a Large Language Model (LLM) to extract important, self-contained facts from conversations for long-term storage in Memanto.
*   **Contextual Retrieval**: Dynamically queries Memanto based on current user input to provide relevant past information to the LLM for informed responses.
*   **Clean LangGraph Workflow**: A straightforward graph structure demonstrating the memory integration points.

## 🛠️ Setup

1.  **Clone the repository (if you haven't already):**
    ```bash
    git clone https://github.com/your-org/your-repo.git
    cd your-repo
    ```
2.  **Navigate to the example directory:**
    ```bash
    cd examples/langgraph-memanto
    ```
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Set your OpenAI API Key:**
    The agent uses `langchain-openai` for its LLM. Ensure your `OPENAI_API_KEY` is set as an environment variable:
    ```bash
    export OPENAI_API_KEY="sk-..."
    ```
    (Replace `sk-...` with your actual OpenAI API Key)

## 🚀 How to Run

1.  **Execute the agent script:**
    ```bash
    python agent.py
    ```

Observe the console output. You'll see:
*   **Session 1**: The agent learns new facts (e.g., your name, hobbies).
*   **Session 2 (Same App Run)**: The agent uses its current LangGraph state to answer.
*   **New, Disjointed Session**: This simulates restarting the agent entirely. The agent will recall facts from Session 1, demonstrating Memanto's cross-session memory capabilities.
*   Memanto creates a local database directory named `./memanto_langgraph_db` to persist its memories.

## 📺 Demonstration

*(Link to a 30-second GIF or video demonstrating cross-session recall will go here)*
