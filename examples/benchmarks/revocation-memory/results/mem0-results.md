# Revocation Memory Benchmark: mem0

- Mode: `live_framework`
- Dataset: `production-access-revocation-v1`
- Dataset SHA-256: `0b232e1baee19458a00bce2aa9bd753990850b374b44b9103b389e40adcb7706`
- Extraction LLM: `none`
- Evaluation judge: `deterministic required/forbidden substring matching`
- Retrieval accuracy: 100.0%
- Stale leak rate: 83.3%
- Ingested tokens: 181
- Retrieved tokens (mean): 122.8
- Write p95: 0.0306 seconds
- Read p95: 0.0057 seconds

| Probe | Accuracy | Stale leak | Retrieved tokens | Latency ms |
|---|---:|---:|---:|---:|
| current-deployment-scope | 100.0% | yes | 116 | 5.78 |
| production-authorization | 100.0% | yes | 123 | 3.76 |
| current-export-retention | 100.0% | yes | 133 | 3.26 |
| current-incident-contact | 100.0% | yes | 116 | 5.28 |
| secret-handling | 100.0% | yes | 123 | 4.83 |
| audit-owner | 100.0% | no | 126 | 4.03 |
