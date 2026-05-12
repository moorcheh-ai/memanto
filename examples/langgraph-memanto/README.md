# LangGraph + Memanto: Multi-Agent Permanent Memory System

> Bounty submission: [moorcheh-ai/memanto#397](https://github.com/moorcheh-ai/memanto/issues/397)

## What makes this different

| Feature | Others | This PR |
|---------|--------|---------|
| Single agent | yes | yes |
| Multi-agent supervisor | no | yes |
| Human-in-the-loop (HITL) | no | yes |
| Streaming output | no | yes |
| Cross-session recall | yes | yes |
| Per-agent memory namespaces | no | yes |
| x402 payment config | no | yes |
| Full test suite | partial | yes |

## Architecture
## Quick Start

```bash
pip install -r requirements.txt
export MOORCHEH_API_KEY=your-key
python cross_session_demo.py
python streaming_demo.py
python test_suite.py
```

## Files

| File | Description |
|------|-------------|
| agents.py | Supervisor + Researcher + Writer multi-agent graph |
| memanto_tools.py | Pydantic v2 tool wrappers |
| cross_session_demo.py | 3-session cross-session recall proof |
| streaming_demo.py | Real-time streaming + memory |
| test_suite.py | Full unit test suite |

## Key innovations

1. Multi-agent subgraph architecture
2. Human-in-the-loop memory approval
3. Streaming + persistent memory
4. Per-agent namespaces
5. x402 payment config

## License
MIT
