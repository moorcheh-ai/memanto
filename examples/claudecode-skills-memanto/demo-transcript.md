# Demo Transcript

## Session 1: `/grill-with-docs`

User:

```text
/grill-with-docs plan this release branch and make sure the public PR is clean
```

Assistant summary captured by the `Stop` hook:

```text
Decision: docs/ is local-only except tracked showcase docs.
Preference: verify with make verify before PR updates.
Never include local planning docs in public branches.
```

The hook stores three typed memories:

```json
{"type":"decision","content":"Decision: docs/ is local-only except tracked showcase docs."}
{"type":"preference","content":"Preference: verify with make verify before PR updates."}
{"type":"instruction","content":"Never include local planning docs in public branches."}
```

## Session 2: `/tdd`

User:

```text
/tdd prepare the public branch and PR
```

Claude Code runs the `UserPromptExpansion` hook before expanding the slash
command. The hook injects:

```text
Memanto engineering memory relevant to this Claude Code skill:
- [instruction 0.94] Never include local planning docs in public branches.
- [decision 0.88] Decision: docs/ is local-only except tracked showcase docs.
- [preference 0.80] Preference: verify with make verify before PR updates.
Apply these as constraints unless the current user prompt overrides them.
```

The user did not repeat the docs-hygiene rule, but the `/tdd` skill receives it
anyway.
