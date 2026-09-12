# Savings report applicability

`memanto migrate okf --help` states that OKF is a local file bundle with **no
savings report**. Provider savings compare a hosted source's token, latency,
and storage characteristics; Claude Code's local Markdown and JSONL state has
no equivalent provider billing baseline.

Reporting fabricated provider savings would be misleading. This Path B
showcase therefore supplies the auditable evidence that applies:

| Evidence | Result |
| --- | ---: |
| Raw source records selected | 5 |
| Portable memories produced | 3 |
| Records skipped | 0 |
| Invalid JSONL lines | 0 |
| Path redactions | 2 |
| Memanto dry-run mappings | 3 |
| Memanto dry-run skips | 0 |
| Source golden recall | 5/5 |
| OKF golden recall | 5/5 |
| Recall parity delta | 0.0 points |

For a live keyed run, `validation/validate_live_recall.py` measures the same
golden questions against Memanto's semantic-recall backend after import.
