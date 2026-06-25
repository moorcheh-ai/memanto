# Revocation Memory Benchmark: memanto

- Mode: `live_framework`
- Dataset: `production-access-revocation-v1`
- Dataset SHA-256: `9a04bce957e81e15f7728ed1f92ae988f85c9b313cae671ebe3bf94b14a7866e`
- Extraction LLM: `none`
- Evaluation judge: `deterministic required/forbidden substring matching`
- Retrieval accuracy: 100.0%
- Stale leak rate: 83.3%
- Ingested tokens: 173
- Retrieved tokens (mean): 213.3
- Write p95: 3.6898 seconds
- Read p95: 1.2787 seconds

| Probe | Accuracy | Stale leak | Retrieved tokens | Latency ms |
|---|---:|---:|---:|---:|
| current-deployment-scope | 100.0% | yes | 216 | 1410.67 |
| production-authorization | 100.0% | yes | 211 | 872.84 |
| current-export-retention | 100.0% | yes | 221 | 877.38 |
| current-incident-contact | 100.0% | yes | 204 | 855.14 |
| secret-handling | 100.0% | yes | 205 | 882.94 |
| audit-owner | 100.0% | no | 223 | 635.28 |
