# Memanto OKF Dry Run

Command:

```bash
memanto migrate okf sample_output/okf-bundle --dry-run
```

Sanitized result:

```text
OKF nodes: 1
Mapped memories: 1 (skipped 0)
Type breakdown: decision: 1
Dry run - no writes performed.
```

The actual command was also exercised by `run.sh`. Memanto wrote its local
mapped preview outside the repository; no cloud write or API key was involved.

