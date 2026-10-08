# Bounty 1852: bounded credential-URL scheme scanning

## Finding

The conversation-memory normalizer redacts generated candidate text before
applying its 10,000-character content cap. Its unanchored credential-URL
expression could restart the greedy scheme scan at every letter in a long
run, including text with no URL and a run followed by an incomplete URL.
The repeated scans made this step quadratic in that input length.

This reproduction supplies the extraction candidate. It does not establish
that a caller can force a deployed model to emit the payload, and it does not
demonstrate a hosted availability attack.

## Change

Require the scheme search to begin at the boundary of its character run.
Leading digits, dots, plus signs, and hyphens are consumed into the existing
first replacement group and reinserted unchanged, preserving the earlier
substitution behavior. The case-insensitive character classes retain Python's
Unicode behavior. Credential replacement order and the PEM repair are unchanged.

## Execution

[Focused public-fork run 37204067448](https://github.com/woahwhattheheck/memanto/actions/runs/37204067448),
[job 111441490051](https://github.com/woahwhattheheck/memanto/actions/runs/37204067448/job/111441490051)
completed successfully with Python 3.12.14 and pytest 8.4.2.

- Baseline: `4e8a1855cb1ada9a7a545db82fab249ad5295137`.
- Executed candidate: `ec8ab5a6b342ac394ec18043208ba86252504ab3`.
- Executed source blob: `19862da6daa06e5512f94d7bbc4c8b88e6926dc1`.
- Executed regression blob: `0646fd71a153997fe0c073944a04ab28b67db6e2`.
- Baseline module SHA-256:
  `178e06129231aee85fadd76edd436dbdbf50a6e008d5ad3ce0488046be3d21f7`.
- Candidate module SHA-256:
  `34fd17156c64526502e9eeed1daf0b952583e1073525ab6a98c42d5bacaeaff5`.

The [measurement script](https://github.com/woahwhattheheck/memanto/blob/ec8ab5a6b342ac394ec18043208ba86252504ab3/.github/scripts/memanto-url-scan.py)
loads the full baseline module from Git and imports the installed candidate
package without import stubs. It warms each version once, then times one full
`_normalize_candidates` call per input size and shape with
`time.perf_counter`. Each invocation has an eight-second guard. These are
single-call observations, not medians or fleet-wide estimates.

| Input | Characters | Before (seconds) | After (seconds) | Observed ratio |
| --- | ---: | ---: | ---: | ---: |
| ASCII letter run | 2000 | 0.025428777 | 0.000326812 | 77.81x |
| ASCII letter run | 4000 | 0.100848124 | 0.000984132 | 102.47x |
| ASCII letter run | 8000 | 0.365480010 | 0.001184519 | 308.55x |
| ASCII letter run | 16000 | 1.653152735 | 0.002288737 | 722.30x |
| Letter run + malformed ://host | 2007 | 0.027875322 | 0.000317995 | 87.66x |
| Letter run + malformed ://host | 4007 | 0.110562709 | 0.000663733 | 166.58x |
| Letter run + malformed ://host | 8007 | 0.440342913 | 0.001201761 | 366.41x |
| Letter run + malformed ://host | 16007 | 1.759382033 | 0.002279771 | 771.74x |

All eight normalized outputs were identical. The largest malformed-URL case
improved by 771.74x in this run; the largest plain-letter case improved by
722.30x. The measured function includes the other redactors, truncation, title
handling, and deduplication preparation.

The maintained tests completed with **8 passed in 0.59 seconds**, without
failures or skips: six URL boundary cases, one bounded-work extraction
regression, and the existing credential-redaction helper control. The boundary
cases cover mixed-case schemes, leading non-letter scheme characters, all four
additional Unicode letters accepted by Python's case-insensitive `[a-z]`
(`İ`, `ı`, `ſ`, `K`), foreign Unicode/underscore boundaries, malformed
userinfo, and multiple URLs. The extraction regression supplies 120,007
characters through the maintained `FakeClient` answer boundary and executes
the real extraction, JSON parsing, redaction, and normalization under a
five-second timeout.

A source-pinned `git grep` found only two Python references to
`URL_CREDENTIAL_PATTERN`: its definition and its existing substitution in
the same module. No other internal Python consumer uses its capture groups.

Execution retained `pytest.ini` and `tests/conftest.py`. An audit hook blocked
network operations during product execution; no blocked events were recorded.
The [focused workflow](https://github.com/woahwhattheheck/memanto/blob/ec8ab5a6b342ac394ec18043208ba86252504ab3/.github/workflows/memanto-1852-composition.yml)
and measurement script remain on the isolated validation branch. The original
security PR receives only the product change, required regressions, and this
evidence; no new pipeline or full-suite result is asserted.
