# 30-second demo script

```bash
cd examples/langgraph-memanto
cp .env.example .env
# Add MOORCHEH_API_KEY to .env, then:
python run_seed_session.py
python run_recall_session.py
```

Expected story:

1. The seed run stores a customer preference in Memanto from inside a LangGraph node.
2. The recall run starts a separate session for the same customer.
3. The reply includes the remembered preference before drafting the response.
