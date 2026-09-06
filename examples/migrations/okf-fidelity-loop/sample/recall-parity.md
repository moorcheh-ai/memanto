# Recall parity across the OKF round trip

Source agent: `okf-fidelity-loop` — target agent: `okf-fidelity-rt`

| Question | Before | After |
| --- | --- | --- |
| Which migration mappers does the CLI ship with? | PASS | PASS |
| Why is Langfuse not in the mappers registry? | PASS | PASS |
| Which folder of an OKF bundle is actually importable? | PASS | PASS |
| How are Memanto-only fields preserved through OKF? | PASS | PASS |
| What is the flag for choosing the target agent on import? | PASS | PASS |
| Where is OKF bundle output allowed to be written? | PASS | PASS |
| When does the auto split mode stack a type into one file? | PASS | PASS |
| What separates documents inside a stacked OKF file? | PASS | PASS |
| What happens when an OKF type has no Memanto equivalent? | PASS | PASS |
| Does CI lint the examples directory? | PASS | PASS |

**Before migration: 10/10 — after migration: 10/10.**

Recall parity held: the round trip cost the agent nothing.
