# Revocation Memory Benchmark: mem0

- Mode: `live_framework`
- Dataset: `production-access-revocation-v1`
- Dataset SHA-256: `9a04bce957e81e15f7728ed1f92ae988f85c9b313cae671ebe3bf94b14a7866e`
- Retrieval accuracy: 100.0%
- Stale leak rate: 83.3%
- Ingested tokens: 173
- Retrieved tokens (mean): 120.3
- Write p95: 0.0177 seconds
- Read p95: 0.0052 seconds

| Probe | Accuracy | Stale leak | Retrieved tokens | Latency ms |
|---|---:|---:|---:|---:|
| current-deployment-scope | 100.0% | yes | 116 | 4.01 |
| production-authorization | 100.0% | yes | 123 | 5.29 |
| current-export-retention | 100.0% | yes | 126 | 4.64 |
| current-incident-contact | 100.0% | yes | 116 | 4.65 |
| secret-handling | 100.0% | yes | 123 | 4.47 |
| audit-owner | 100.0% | no | 118 | 4.90 |
