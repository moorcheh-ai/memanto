# Revocation Memory Benchmark: mem0

- Mode: `live_framework`
- Dataset: `production-access-revocation-v1`
- Dataset SHA-256: `9a04bce957e81e15f7728ed1f92ae988f85c9b313cae671ebe3bf94b14a7866e`
- Extraction LLM: `none`
- Evaluation judge: `deterministic required/forbidden substring matching`
- Retrieval accuracy: 100.0%
- Stale leak rate: 83.3%
- Ingested tokens: 173
- Retrieved tokens (mean): 120.3
- Write p95: 0.0238 seconds
- Read p95: 0.0092 seconds

| Probe | Accuracy | Stale leak | Retrieved tokens | Latency ms |
|---|---:|---:|---:|---:|
| current-deployment-scope | 100.0% | yes | 116 | 9.59 |
| production-authorization | 100.0% | yes | 123 | 7.67 |
| current-export-retention | 100.0% | yes | 126 | 7.12 |
| current-incident-contact | 100.0% | yes | 116 | 8.06 |
| secret-handling | 100.0% | yes | 123 | 7.07 |
| audit-owner | 100.0% | no | 118 | 4.86 |
