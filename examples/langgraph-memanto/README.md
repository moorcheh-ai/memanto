# LangGraph + Memanto: Cross-Session Memory Boundary

This example shows Memanto acting as the durable memory layer for a LangGraph support agent. The first graph run stores Riley's preferences in Memanto. A second graph run starts with a fresh LangGraph state and still recalls those facts from Memanto.

![Cross-session recall demo](assets/cross-session-recall.gif)

## Why This Example Is Different

- Memory is outside LangGraph state: the second run receives no previous messages.
- The validator checks the memory boundary: every recalled memory must come from `support-yesterday`, not `support-today`.
- It runs without credentials through a local JSON backend, then can switch to the
  live Memanto SDK with `MEMANTO_LANGGRAPH_BACKEND=memanto`.
- SDK mode activates the configured agent before `remember` and `recall`, matching
  the session contract of `memanto.cli.client.sdk_client.SdkClient`.

## Run Offline

```bash
cd examples/langgraph-memanto
python run_demo.py --backend local --reset-local
python validate_offline.py
```

Expected validation:

```text
offline validation passed
recalled_memories=4
state_boundary=passed
```

## Run With Memanto

```bash
cd examples/langgraph-memanto
cp .env.example .env
export MOORCHEH_API_KEY=your_key
export MEMANTO_LANGGRAPH_BACKEND=memanto
python run_demo.py --backend memanto
```

## Files

```text
examples/langgraph-memanto/
├── README.md
├── .env.example
├── requirements.txt
├── graph.py
├── memory_store.py
├── run_demo.py
├── validate_offline.py
├── make_demo_gif.py
├── assets/cross-session-recall.gif
└── tests/test_memory_boundary.py
```

## Verification

```bash
python validate_offline.py
PYTHONPATH=. python -m pytest tests -q
python -m py_compile graph.py memory_store.py run_demo.py validate_offline.py make_demo_gif.py
```

## Bounty Checklist

- Path: `examples/langgraph-memanto`
- Cross-session recall: `support-today` recalls memories written by `support-yesterday`
- Live SDK path: activates the configured agent before storing or recalling
- Clean single-folder implementation
- 30-second demo media in README
- Share-ready post copy and validation summary: `SOCIAL_SHOWCASE.md`
