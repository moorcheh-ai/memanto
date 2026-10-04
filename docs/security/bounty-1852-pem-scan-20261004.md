# Bounty 1852: bounded private-key redaction scanning

## Finding

Conversation-memory extraction redacts the generated candidate before applying its
10,000-character content limit. The former private-key expression repeatedly
rescanned the remaining text after each unterminated PEM prefix. Repeating those
prefixes therefore increased CPU work quadratically, even though the saved output
was capped.

This reproduction controls the returned extraction candidate. It does not
demonstrate that an external caller can force a deployed model to emit the
payload, and it makes no hosted availability or additional award claim.

## Change

Replace the PEM expression with two bounded passes over disjoint runs of the
header alphabet. Each run is searched a constant number of times. The scan
preserves the prior greedy BEGIN/END header behavior, including uppercase keys
written on one line, and leaves incomplete blocks unchanged. Other credential
redactors and the existing content/provenance handling are unchanged.

## Execution

[Focused public-fork run 37203426965](https://github.com/woahwhattheheck/memanto/actions/runs/37203426965),
[job 111439580308](https://github.com/woahwhattheheck/memanto/actions/runs/37203426965/job/111439580308)
completed successfully with Python 3.12.14 and pytest 8.4.2.

- Baseline: `8934ad1a7bbdf01c75d82feba5092e8ee23eadcc`.
- Executed candidate: `926f5e3c8719b81d41d86cbcb6a64a4e1622b0b1`.
- Executed source blob: `d4902205f466a2112986968d2ef90c7e446941dc`.
- Executed regression blob: `26044cd594f47b59889d631ba5490848b6ff3282`.
- Baseline module SHA-256:
  `c93fdbc3b497f711f2bc4898809c3c64c3ec35f16dc7c61ca8941071abc18b82`.
- Candidate module SHA-256:
  `178e06129231aee85fadd76edd436dbdbf50a6e008d5ad3ce0488046be3d21f7`.

The [measurement script](https://github.com/woahwhattheheck/memanto/blob/926f5e3c8719b81d41d86cbcb6a64a4e1622b0b1/.github/scripts/memanto-pem-scan.py)
loads the full baseline module from Git and imports the installed candidate
package without import stubs. It warms each version once, then measures one
complete `_normalize_candidates` call per size and shape using
`time.perf_counter`, with an eight-second guard per invocation. These are
single-call observations, not medians or fleet-wide performance estimates.

| Input | Characters | Before (seconds) | After (seconds) | Observed ratio |
| --- | ---: | ---: | ---: | ---: |
| Unclosed PEM lines | 7000 | 0.017964509 | 0.002217248 | 8.10x |
| Unclosed PEM lines | 14000 | 0.063937687 | 0.004277624 | 14.95x |
| Unclosed PEM lines | 28000 | 0.256380234 | 0.008248755 | 31.08x |
| Unclosed PEM lines | 56000 | 1.022105067 | 0.016681606 | 61.27x |
| Malformed uppercase header run | 2775 | 0.001951372 | 0.000897996 | 2.17x |
| Malformed uppercase header run | 5525 | 0.005116811 | 0.001723537 | 2.97x |
| Malformed uppercase header run | 11025 | 0.015861965 | 0.003338561 | 4.75x |
| Malformed uppercase header run | 22025 | 0.082113311 | 0.006434189 | 12.76x |

All eight before/after normalized outputs were identical. For the largest
unclosed-line input, the observed improvement was 61.27x; the remaining runtime
includes all other normalization and credential-redaction work.

The maintained tests completed with **8 passed in 0.77 seconds**, without
failures or skips: six PEM boundary cases, one extraction regression with
16,000 unclosed prefixes and an incomplete footer (448,009 input characters),
and the existing credential-redaction helper control. The extraction regression
uses the existing `FakeClient` at the external answer-generation boundary and
the actual extraction, JSON parsing, and normalization code. Its five-second
timeout bounds the demonstrated failure mode; it does not assert a machine-
independent speedup.

Execution retained the repository's `pytest.ini` and `tests/conftest.py`.
An audit hook blocked network operations during product execution; no blocked
events were recorded. The reused [focused workflow](https://github.com/woahwhattheheck/memanto/blob/926f5e3c8719b81d41d86cbcb6a64a4e1622b0b1/.github/workflows/memanto-1852-composition.yml)
and measurement script remain confined to the isolated validation branch.
This continuation contains only product source, the required regressions, and
this evidence; it does not add an upstream pipeline or claim a full-suite run.
