# LangGraph + Memanto Permanent Brain Example

This example shows a LangGraph customer-support workflow that stores and retrieves
facts in **Memanto** outside of LangGraph state.  

The key behavior: a preference remembered in one local run is recalled in a later
run with fresh LangGraph state by querying the same Memanto namespace.

🎬 30-second demo video: https://www.youtube.com/watch?v=vEtOaoweIG4

## Prerequisites

- Python 3.10+
- Moorcheh API key (`MOORCHEH_API_KEY`)

## Setup

```bash
cd examples/langgraph-memanto
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# edit .env with your MOORCHEH_API_KEY
```

## What it demonstrates

1. Build a two-node LangGraph:
   - `recall_memories`: query Memanto for long-term context.
   - `respond`: generate reply and optionally persist new preferences.
2. Store a preference in Session 1:
   - `remember: My preferred support channel is email.`
3. Start Session 2 with a fresh state object:
   - Ask about the preference again.
4. The agent recalls the preference from Memanto even though no state was carried
   across the local session boundary.

## Run

```bash
python run_demo.py
```

Expected output:

- First run stores memory and echoes the store confirmation.
- Second run retrieves the stored preference from Memanto.
- Final verification prints the same stored memory via direct Memanto recall.

## Files

- `support_graph.py`: LangGraph workflow and Memanto integration helpers.
- `run_demo.py`: end-to-end two-session demo script.
- `requirements.txt`: project dependencies for this example.
- `.env.example`: required environment variables.
