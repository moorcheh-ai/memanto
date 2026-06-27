# Revocation Memory Benchmark: fixture

- Mode: `smoke_fixture`
- Dataset: `production-access-revocation-v1`
- Dataset SHA-256: `0b232e1baee19458a00bce2aa9bd753990850b374b44b9103b389e40adcb7706`
- Extraction LLM: `none`
- Evaluation judge: `deterministic required/forbidden substring matching`
- Retrieval accuracy: 100.0%
- Stale leak rate: 0.0%
- Ingested tokens: 181
- Retrieved tokens (mean): 136.0
- Write p95: 0.0000 seconds
- Read p95: 0.0000 seconds

| Probe | Accuracy | Stale leak | Retrieved tokens | Latency ms |
|---|---:|---:|---:|---:|
| current-deployment-scope | 100.0% | no | 136 | 0.00 |
| production-authorization | 100.0% | no | 136 | 0.00 |
| current-export-retention | 100.0% | no | 136 | 0.00 |
| current-incident-contact | 100.0% | no | 136 | 0.00 |
| secret-handling | 100.0% | no | 136 | 0.00 |
| audit-owner | 100.0% | no | 136 | 0.00 |
