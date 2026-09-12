# memanto migrate okf dry-run (sample-okf)

Recorded with Memanto 0.2.21. No API key. No writes.

```
OKF nodes: 11
Mapped memories: 11  (skipped 0)
Type breakdown: decision: 2, event: 1, fact: 2, goal: 1, observation: 3, preference: 2
```

Session identity is emitted as Memanto `event` (there is no `episode` slot in `VALID_MEMORY_TYPES`). `memanto migrate okf` has no `--report` savings flag; this table is the Path B fidelity evidence.

Reproduce:

```bash
python scripts/build_sample.py
memanto migrate okf ./sample-okf --dry-run
python scripts/validate_qa.py
```
