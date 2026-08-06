# Round-trip validation report

- Overall: **PASS**
- Source -> OKF exact record hashes: **8/8**
- OKF -> Memanto field mappings: **8/8**
- Golden recall top-3 parity: **6/6**
- Whole-bundle canonical hash match: **True**
- Embeddings: intentionally omitted derived data

| Question | CrewAI rank | Portable OKF rank | Parity |
|---|---:|---:|:---:|
| Which database was selected for concurrent writers and point-in-time recovery? | 1 | 1 | PASS |
| What is the analytics email privacy rule? | 1 | 1 | PASS |
| What caused incident AUR-218 duplicate invoices? | 1 | 1 | PASS |
| What idempotency remediation prevents duplicate invoices? | 2 | 1 | PASS |
| What is the Aurora EU pilot deadline and checkout p95 goal? | 1 | 1 | PASS |
| Who owns Aurora checkout and who approves security? | 2 | 1 | PASS |
