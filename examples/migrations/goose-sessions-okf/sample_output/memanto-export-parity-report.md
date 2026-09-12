# Goose OKF round-trip validation

- OKF entries loaded: 4
- Memanto rows mapped: 4
- Passed: True

## Type counts

- error: 1
- event: 1
- fact: 1
- preference: 1

## Recall parity checks

- PASS: Which agent generated the migrated sessions? — expected `goose`
- PASS: How must reconciliation keys behave? — expected `deterministic, across machines`
- PASS: What customer data must audit output protect? — expected `full email address`
- PASS: What check is required before completion? — expected `python -m unittest -v`
