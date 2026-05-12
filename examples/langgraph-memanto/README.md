# Memanto + LangGraph Integration Example

> **Give your LangGraph agents a permanent brain.**

This example shows how to use **Memanto** as the long-term memory layer for a **LangGraph** agent. Memories survive across sessions, agents, and even reboots — so your graph never starts from a blank slate.

## 🎯 What This Demonstrates

| Challenge | How Memanto Solves It |
|-----------|----------------------|
| LangGraph state is ephemeral — lost on restart | Memanto persists memories in a semantic database |
| Multiple agents can't share context | All agents read/write the same `agent_id` namespace |
| No built-in memory retrieval | `recall` searches by meaning, not just keyword |
| Flat context window | `answer` uses RAG to synthesize insights from many memories |

## 🏠 Architecture

```
User Message
     |
     v
+------------------+
| classify_intent  |  --> technical_issue | billing_question | feature_request | general_chat
+------------------+
     |
     v
+------------------+
|  fetch_context   |  --> memanto_recall(user_id + intent)
+------------------+
     |
     v
+------------------+
| generate_response|  --> LLM drafts reply using retrieved memories
+------------------+
     |
     v
+------------------+
| persist_memory   |  --> memanto_remember(extracted facts)
+------------------+
```

## 🚀 Quick Start

### 1. Install dependencies

```bash
cd examples/langgraph-memanto
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and add your keys
```

| Variable | Where to get it |
|----------|-----------------|
| `MOORCHEH_API_KEY` | https://console.moorcheh.ai/api-keys |
| `OPENROUTER_API_KEY` | https://openrouter.ai/keys (free tier works) |

### 3. Run the customer-support agent

```bash
python run_customer_support.py
```

Type messages and watch the agent recall previous context even after you restart the script.

## 📚 Memory Types Used

The agent stores memories with rich metadata:

- **preference** — user likes/dislikes (e.g. "prefers email over chat")
- **fact** — verified information (e.g. "on Pro plan since 2024")
- **decision** — agreed resolution (e.g. "refund approved")
- **issue** — reported problems (e.g. "login fails on Safari")

Each memory includes confidence scores, tags, and provenance for clean retrieval.

## 🔧 Customisation

### Swap the LLM

The graph accepts any LangChain-compatible chat model:

```python
from langchain_anthropic import ChatAnthropic

llm = ChatAnthropic(model="claude-3-5-sonnet-20241022")
```

### Change the agent namespace

```python
AGENT_ID = "my-company-support-agent"
```

All memories are scoped to this ID, so you can run multiple agents without collision.

### Add more graph nodes

`build_customer_support_graph()` returns a compiled `StateGraph`. You can extend it with additional nodes (escalation, sentiment analysis, etc.) before calling `.compile()`.

## 📝 Files

| File | Purpose |
|------|---------|
| `langgraph_memanto/client.py` | Memanto lifecycle manager (setup/teardown) |
| `langgraph_memanto/tools.py` | Raw `remember` / `recall` / `answer` functions |
| `langgraph_memanto/graph.py` | Re-usable `build_customer_support_graph()` builder |
| `run_customer_support.py` | Interactive CLI demo |
| `requirements.txt` | Python dependencies |
| `.env.example` | Environment template |

## 📱 Social Traction

If you build something cool with this, post it and tag **#Memanto** + **@moorcheh-ai** on X / LinkedIn / Reddit. The bounty is awarded to the PR with the highest engagement by **June 1st 2026**.

---

Built with ❤️ by the open-source community.
