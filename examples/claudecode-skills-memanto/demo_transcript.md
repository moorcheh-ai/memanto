# Demo Transcript

```text
$ python run_demo.py --backend local --reset

== Session 1: /grill-with-docs ==
MEMANTO_SKILL_CONTEXT:
- No relevant prior engineering memories found.
Stored 3 memories

== Session 2: /tdd ==
MEMANTO_SKILL_CONTEXT:
- [decision] Prefer server-side validation helpers over duplicating schema checks in React components. (grill-with-docs, docs, review, architecture)
  Prefer server-side validation helpers over duplicating schema checks in React components.
- [preference] Keep PRs small enough that each skill handoff has one obvious owner. (grill-with-docs, docs, review, architecture)
  Keep PRs small enough that each skill handoff has one obvious owner.
```

The `/tdd` prompt did not repeat the validation architecture decision. Memanto
recalled it from a prior `/grill-with-docs` run and produced a concise context
block for injection.
