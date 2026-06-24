# Revocation Memory Benchmark: fixture

- Mode: `smoke_fixture`
- Dataset: `production-access-revocation-v1`
- Dataset SHA-256: `9a04bce957e81e15f7728ed1f92ae988f85c9b313cae671ebe3bf94b14a7866e`
- Extraction LLM: `none`
- Evaluation judge: `deterministic required/forbidden substring matching`
- Retrieval accuracy: 100.0%
- Stale leak rate: 0.0%
- Ingested tokens: 173
- Retrieved tokens (mean): 128.0
- Write p95: 0.0000 seconds
- Read p95: 0.0000 seconds

| Probe | Accuracy | Stale leak | Retrieved tokens | Latency ms |
|---|---:|---:|---:|---:|
| current-deployment-scope | 100.0% | no | 128 | 0.00 |
| production-authorization | 100.0% | no | 128 | 0.00 |
| current-export-retention | 100.0% | no | 128 | 0.00 |
| current-incident-contact | 100.0% | no | 128 | 0.00 |
| secret-handling | 100.0% | no | 128 | 0.00 |
| audit-owner | 100.0% | no | 128 | 0.00 |
