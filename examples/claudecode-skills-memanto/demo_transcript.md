# Demo Transcript

```text
$ python run_demo.py --backend local --reset

== Session 1: /grill-with-docs ==
MEMANTO_SKILL_CONTEXT:
- No relevant prior engineering memories found.
Stored 3 memories

== Session 2: /tdd ==
MEMANTO_SKILL_CONTEXT:
- [memanto-answer] Apply remembered context: docs/architecture/forms.md records the validation boundary. Prefer server-side validation helpers over duplicating schema checks in React components.
- [artifact] docs/architecture/forms.md records the validation boundary. (grill-with-docs, docs, forms, architecture, review)
  docs/architecture/forms.md records the validation boundary.
- [decision] Prefer server-side validation helpers over duplicating schema checks in React components. (grill-with-docs, docs, forms, architecture, review)
  Prefer server-side validation helpers over duplicating schema checks in React components.

Benchmark: 1/1 repeated instructions avoided (100% reduction)
```

The `/tdd` prompt did not repeat the validation architecture decision. Memanto
recalled it from a prior `/grill-with-docs` run and produced a concise context
block for injection.
