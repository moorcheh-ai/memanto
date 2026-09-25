# Memanto + LangGraph Integrations

This directory contains several out-of-the-box examples demonstrating how to integrate Memanto's persistent memory capabilities into LangGraph agents.

All examples share the core Memanto tools defined in core/memanto_tools.py (except memanto_base_store which implements a native LangGraph BaseStore).

## Directory Setup

`bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your Memanto and LLM API keys
`

## Using OrcaRouter as your LLM gateway

Every example routes its LangGraph agent through a **named** OpenAI-compatible
provider. By default they use OpenRouter (or OpenAI), but setting
`ORCAROUTER_API_KEY` in `.env` switches the whole fleet to
[OrcaRouter](https://www.orcarouter.ai) — a smart model-routing gateway at
`https://api.orcarouter.ai/v1`:

```bash
# .env
ORCAROUTER_API_KEY=sk-orca-...
# Optional: pick a specific gateway model (default is the smart-routing `orcarouter/auto`)
# ORCAROUTER_MODEL=orcarouter/auto
```

When OrcaRouter is configured, the agent uses its smart-routing model
`orcarouter/auto` — OrcaRouter picks the best upstream model for each request.
It also runs gateway-level, zero-trust security for AI agents on the same
endpoint — screening every prompt/response and governing every tool call on a
default-deny basis, with no application code changes.

## Running the Examples

Because the examples share the core tools module, you should run them as Python modules from this root directory:

`bash
python -m basic_integration.demo
python -m cross_session_recall.main
python -m custom_memory_saver.run_demo
python -m research_pipeline.run_full_pipeline

# For the advanced BaseStore implementation (PR 571):
python -m memanto_base_store.run_full_demo
# Or run its Streamlit UI:
streamlit run memanto_base_store/app.py
`

## Available Examples

* **[`memanto_base_store/`](./memanto_base_store/README.md)**: (NEW) A robust customer-support agent using a native `MemantoStore(BaseStore)` implementation for cross-session recall. Includes a Streamlit UI, contradiction resolution logic, and a **detailed architectural README**.
* **basic_integration/**: A minimal, drop-in example of using Memanto tools within a simple LangGraph agent.
* **cross_session_recall/**: An agent designed to remember facts and preferences across different conversation sessions.
* **research_pipeline/**: A multi-agent setup where one agent researches and saves facts to Memanto, and another synthesizes them.
* **custom_memory_saver/**: An advanced implementation showing how to integrate Memanto directly at the LangGraph CheckpointSaver level.
