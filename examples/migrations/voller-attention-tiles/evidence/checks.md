# Executed checks — 13 September 2026

Source/dependencies pinned to upstream `aa3f6f1f4509dd09702679d96ce28cb0f4ac9fe3`.

- 11 adapter tests and 20 selected upstream OKF/migration tests: **31 passed** (`test_results.txt`).
- Complete upstream `pytest -q` invocation: **exit 0; 970 passed, 24 skipped** (`upstream_test_results.txt`). Counts are from pytest progress markers because the configured double quiet mode omits its numerical summary. All skipped cases require a real Moorcheh API key.
- `pre-commit run --all-files`: **passed** (`precommit_results.txt`), using the prepared virtual environment with `UV_PROJECT_ENVIRONMENT` and `UV_NO_SYNC=1`.
- Ruff lint and format checks: **passed**.
- Explicit mypy on `adapter.py`, `run_demo.py` and `run_live.py`, with `--follow-imports=silent --ignore-missing-imports`: **passed**.
- Fresh public-source CLI preview and native local serializer round trip: **66 source tiles, 67 mapped records, 0 skipped; exact reconstruction** (`validation.json`).

The full upstream suite is separate from the 11 example tests. The earlier selected 20 upstream tests are part of that full suite and should not be counted twice.

These are local software and format checks. No live backend migration, semantic recall score, demo video or prize submission is claimed.
