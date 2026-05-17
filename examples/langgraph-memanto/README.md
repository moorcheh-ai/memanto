# LangGraph + Memanto Example

This example shows a customer support agent built with **LangGraph** that uses **Memanto** as its long-term memory layer.

LangGraph keeps the short-lived workflow state for the current request, while Memanto stores support history outside that state so the agent can remember past conversations across sessions.

## What It Demonstrates

- A LangGraph workflow with three nodes: `greet`, `handle_query`, and `store_memory`
- Memanto recall before answering, so the agent can use past support context
- Memanto writes after the response, so the next run can remember the interaction
- Cross-session persistence by reusing the same `customer_id`

## Files

```text
examples/langgraph-memanto/
|-- README.md
|-- requirements.txt
`-- support_agent.py
```

## Prerequisites

- Python 3.10+
- A `MOORCHEH_API_KEY`

## Install

```bash
cd examples/langgraph-memanto
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Configure

Set your Memanto API key in the environment:

```bash
$env:MOORCHEH_API_KEY="your-api-key"
```

## Run

Start the example with a customer ID and support message:

```bash
python support_agent.py --customer-id acme-001 --customer-name "Ava" --message "I still cannot log in"
```

Run it again with the same `customer_id` and a new session. The agent will recall the previous interaction from Memanto and include that context in the greeting and response.

```bash
python support_agent.py --customer-id acme-001 --customer-name "Ava" --message "The password reset link still fails"
```

## How It Works

1. `greet` calls Memanto recall using the customer tag and prepares a personalized greeting.
2. `handle_query` generates a support response using the recalled memory context.
3. `store_memory` persists the interaction summary back into Memanto so it survives future runs.

The important point is that the graph state is ephemeral, but the support history is not. The memory lives in Memanto under the shared agent ID `langgraph-support-agent`.

## Notes

- The example uses deterministic support logic so it runs without another model API key.
- You can adapt the `handle_query` node to call an LLM if you want a more generative support assistant.
