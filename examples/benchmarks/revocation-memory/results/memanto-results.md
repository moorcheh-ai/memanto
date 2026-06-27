# Revocation Memory Benchmark: memanto

- Mode: `live_framework`
- Dataset: `production-access-revocation-v1`
- Dataset SHA-256: `0b232e1baee19458a00bce2aa9bd753990850b374b44b9103b389e40adcb7706`
- Extraction LLM: `none`
- Evaluation judge: `deterministic required/forbidden substring matching`
- Retrieval accuracy: 100.0%
- Stale leak rate: 83.3%
- Ingested tokens: 181
- Retrieved tokens (mean): 214.2
- Write p95: 1.8077 seconds
- Read p95: 1.0672 seconds

| Probe | Accuracy | Stale leak | Retrieved tokens | Latency ms |
|---|---:|---:|---:|---:|
| current-deployment-scope | 100.0% | yes | 216 | 1184.92 |
| production-authorization | 100.0% | yes | 211 | 576.44 |
| current-export-retention | 100.0% | yes | 229 | 641.71 |
| current-incident-contact | 100.0% | yes | 204 | 594.95 |
| secret-handling | 100.0% | yes | 213 | 631.25 |
| audit-owner | 100.0% | no | 212 | 714.01 |
