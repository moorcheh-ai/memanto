# Demo Transcript

Session A uses `/grill-with-docs` to settle architecture:

```text
decision: use a repository-local service layer for billing changes
preference: keep React toolbars dense and keyboard-friendly
instruction: run focused unit tests before broad integration tests
```

Session B starts `/tdd` with a different prompt:

```text
Relevant Memanto engineering memory for this skill run:
- [decision] use a repository-local service layer for billing changes
- [preference] keep React toolbars dense and keyboard-friendly
- [instruction] run focused unit tests before broad integration tests
Apply these constraints unless the user explicitly overrides them.
```

This removes the repeated instruction step between skills while keeping the
memory records explicit, typed, and reviewable.
