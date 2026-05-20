# Claude Code Skills + Memanto Benchmark

This credential-free benchmark compares a two-skill workflow with and
without Memanto memory injection.

| Metric | Value |
| --- | ---: |
| Memories stored after `/grill-with-docs` | 3 |
| Expected architecture rule recalled before `/tdd` | True |
| Baseline repeated instructions needed | 1 |
| Memanto repeated instructions needed | 0 |
| Repeated instructions avoided | 1 |
| Repeated-instruction reduction | 100% |

The benchmark is intentionally tiny and deterministic: `/grill-with-docs`
records one architectural validation rule, then `/tdd` recalls that rule
without the user restating it in the second prompt.
