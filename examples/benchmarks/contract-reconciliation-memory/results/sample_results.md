# Contract Reconciliation Memory Benchmark Results

| Backend | Accuracy | Avg Tokens | p95 Latency ms | Stale Conflict | Secret Leak | Evidence | Signal/Noise |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| append_only_log | 0.833 | 71.83 | 0.879 | 0.667 | 0.500 | 1.000 | 0.067 |
| recent_window_log | 0.833 | 46.67 | 0.198 | 0.000 | 0.000 | 0.800 | 0.075 |
| active_contract_ledger | 1.000 | 26.17 | 0.114 | 0.000 | 0.000 | 1.000 | 0.166 |

## Probe Details

### append_only_log

- Query: What is the current accepted price?
  - accuracy: 1.000
  - retrieved_tokens: 114
  - stale_conflict: True
  - secret_leak: True

- Query: What support SLA should the agent use for Sev1 incidents?
  - accuracy: 1.000
  - retrieved_tokens: 97
  - stale_conflict: True
  - secret_leak: True

- Query: Where may production data and anonymized analytics exports run?
  - accuracy: 1.000
  - retrieved_tokens: 64
  - stale_conflict: True
  - secret_leak: False

- Query: How should renewal be handled?
  - accuracy: 1.000
  - retrieved_tokens: 19
  - stale_conflict: False
  - secret_leak: False

- Query: Which secret or token should be used for payment setup?
  - accuracy: 0.000
  - retrieved_tokens: 81
  - stale_conflict: True
  - secret_leak: True

- Query: What must happen before production launch?
  - accuracy: 1.000
  - retrieved_tokens: 56
  - stale_conflict: False
  - secret_leak: False
### recent_window_log

- Query: What is the current accepted price?
  - accuracy: 1.000
  - retrieved_tokens: 40
  - stale_conflict: False
  - secret_leak: False

- Query: What support SLA should the agent use for Sev1 incidents?
  - accuracy: 0.000
  - retrieved_tokens: 103
  - stale_conflict: False
  - secret_leak: False

- Query: Where may production data and anonymized analytics exports run?
  - accuracy: 1.000
  - retrieved_tokens: 45
  - stale_conflict: False
  - secret_leak: False

- Query: How should renewal be handled?
  - accuracy: 1.000
  - retrieved_tokens: 19
  - stale_conflict: False
  - secret_leak: False

- Query: Which secret or token should be used for payment setup?
  - accuracy: 1.000
  - retrieved_tokens: 36
  - stale_conflict: False
  - secret_leak: False

- Query: What must happen before production launch?
  - accuracy: 1.000
  - retrieved_tokens: 37
  - stale_conflict: False
  - secret_leak: False
### active_contract_ledger

- Query: What is the current accepted price?
  - accuracy: 1.000
  - retrieved_tokens: 35
  - stale_conflict: False
  - secret_leak: False

- Query: What support SLA should the agent use for Sev1 incidents?
  - accuracy: 1.000
  - retrieved_tokens: 19
  - stale_conflict: False
  - secret_leak: False

- Query: Where may production data and anonymized analytics exports run?
  - accuracy: 1.000
  - retrieved_tokens: 40
  - stale_conflict: False
  - secret_leak: False

- Query: How should renewal be handled?
  - accuracy: 1.000
  - retrieved_tokens: 18
  - stale_conflict: False
  - secret_leak: False

- Query: Which secret or token should be used for payment setup?
  - accuracy: 1.000
  - retrieved_tokens: 10
  - stale_conflict: False
  - secret_leak: False

- Query: What must happen before production launch?
  - accuracy: 1.000
  - retrieved_tokens: 35
  - stale_conflict: False
  - secret_leak: False
