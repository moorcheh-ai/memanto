# Demo Transcript

```text
$ python3 validate.py
credential-free validation passed

$ python3 productivity_benchmark.py
{
  "sessions": [
    {
      "skill": "/grill-with-docs",
      "stored_memories": [
        "Keep retry scheduling in billing/retry.py.",
        "Use fake clock fixtures for retry tests.",
        "Never sleep in retry tests.",
        "Run `pytest tests/billing/test_retry.py -q` after retry changes."
      ],
      "injected_context": ""
    },
    {
      "skill": "/tdd",
      "injected_context": "<memanto-engineering-memory>..."
    },
    {
      "skill": "/handoff",
      "injected_context": "<memanto-engineering-memory>..."
    }
  ],
  "manual_reprompting": {
    "instructions_without_memory": 8,
    "instructions_with_memory": 0,
    "reduction_percent": 100.0
  }
}
```

The second and third sessions do not receive the first transcript directly.
They receive a compact memory block recalled through the bridge, which is the
same boundary used by the live SDK backend.
