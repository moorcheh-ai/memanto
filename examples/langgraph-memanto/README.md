# LangGraph + Memanto Research Memory

This example shows Memanto as the long-term memory layer for a LangGraph
research assistant. LangGraph state holds only the current session. Memanto
stores preferences, source policy, and tracked research artifacts that can be
recalled by later sessions.

Demo GIF: `assets/langgraph-memanto-demo.gif`

## What This Proves

- Cross-session recall: the `today` session follows preferences saved in the
  `yesterday` session.
- The current LangGraph state for `today` does not contain the old facts.
- The graph has separate `plan`, `recall`, `answer`, `extract_memories`, and
  `persist` nodes.
- The same graph works with real Memanto or a local JSON backend for tests.

## Run Locally

```bash
cd examples/langgraph-memanto
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python langgraph_memanto_research_agent.py --backend local --reset-local
```

Expected behavior:

1. `yesterday` stores durable memories:
   - Dana prefers compact benchmark tables.
   - Vendor blog posts should not be primary sources.
   - AtlasBench 2026 should stay tracked.
2. `today` starts with only this note:
   `No preferred format or source policy was restated today.`
3. The graph still recalls the old constraints from Memanto/local memory and
   answers with the compact table, source policy, and AtlasBench guidance.

## Use Real Memanto

```bash
cp .env.example .env
# add MOORCHEH_API_KEY to .env
python langgraph_memanto_research_agent.py --backend memanto --session full
```

The `MemantoMemory` adapter creates or reuses one Memanto agent namespace:
`langgraph-research-memory`. Running `--session today` later will recall
memories from earlier runs.

## Test

```bash
pytest test_langgraph_memanto_research_agent.py -q
```

The tests prove that the `today` answer uses recalled durable memory while the
current `today` state does not contain the old session facts.
