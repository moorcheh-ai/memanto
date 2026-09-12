# Memanto OKF dry-run evidence

Command:

```bash
uv run memanto migrate okf \
  examples/migrations/claude-code/sample_output/okf \
  --dry-run
```

Result from Memanto's shipped importer:

| Measure | Result |
| --- | ---: |
| OKF nodes | 3 |
| Mapped memories | 3 |
| Skipped | 0 |
| `context` | 1 |
| `fact` | 1 |
| `preference` | 1 |

The command performed no writes. Machine-local run-directory and preview paths
are intentionally omitted from this committed record.
