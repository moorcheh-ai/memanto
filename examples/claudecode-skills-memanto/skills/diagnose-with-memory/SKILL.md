---
name: diagnose-with-memory
description: Disciplined bug diagnosis enhanced with Memanto memory. Recalls past debugging patterns and known failure modes before starting, and stores root-cause learnings after. Use when diagnosing hard bugs or regressions with persistent memory of past investigations.
---

# Diagnose with Memory

An enhanced version of `/diagnose` that recalls past debugging knowledge and stores new findings.

## Step 1 — Recall past debugging context

Before building a feedback loop, retrieve relevant memories:

```bash
memanto-skills recall diagnose --hint "debugging bug investigation failure modes"
```

If memories are returned:
- `error` memories describe **past bugs** — check if this issue resembles a known pattern
- `learning` memories describe **debugging discoveries** — apply relevant techniques immediately
- `decision` memories may describe **architectural choices** that are relevant to this bug's domain
- `instruction` memories may include **debugging conventions** for this codebase

## Step 2 — Run the diagnosis loop

A discipline for hard bugs. Skip phases only when explicitly justified.

### Phase 1 — Build a feedback loop

This is the skill. Build a fast, deterministic, agent-runnable pass/fail signal. Try in order:
1. Failing test at whatever seam reaches the bug
2. Curl / HTTP script against a running dev server
3. CLI invocation with fixture input
4. Headless browser script (Playwright / Puppeteer)
5. Replay a captured trace
6. Throwaway harness
7. Property / fuzz loop
8. Bisection harness
9. Differential loop (old vs new version)

Do not proceed to Phase 2 without a loop you believe in.

### Phase 2 — Reproduce

Confirm the failure mode is the one the user described. Confirm reproducibility.

### Phase 3 — Hypothesise

Generate 3–5 ranked, falsifiable hypotheses. Format: "If X is the cause, then changing Y will make the bug disappear."

Show the ranked list before testing. Cheap checkpoint, big time saver.

### Phase 4 — Instrument

Each probe maps to a specific prediction. Change one variable at a time.
- Tag every debug log: `[DEBUG-xxxx]`
- For perf bugs: establish a baseline measurement first

### Phase 5 — Fix + regression test

Write the regression test **before the fix** — but only if there is a correct seam.

Apply fix → watch test pass → re-run Phase 1 loop.

### Phase 6 — Cleanup + post-mortem

- [ ] Original repro no longer reproduces
- [ ] All `[DEBUG-...]` instrumentation removed
- [ ] Throwaway prototypes deleted
- [ ] Root cause stated in commit message

## Step 3 — Store debugging learnings

After the diagnosis is complete:

```bash
memanto-skills store diagnose "SUMMARY_OF_ROOT_CAUSE_AND_FIX" --type learning
```

Ask the user: "What should I save from this investigation?" Good candidates:
- The root cause and how it manifested
- Any recurring patterns this bug belongs to
- Debugging techniques that worked (or didn't) for this codebase
- Architectural weaknesses discovered
- Any `error` type memories about the specific failure mode
