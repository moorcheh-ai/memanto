# Migration summary

| Stage | Count |
| --- | ---: |
| Codex JSONL records | 4 |
| Eligible user/assistant messages | 4 |
| Exported OKF conversation memories | 4 |
| User messages | 2 |
| Assistant messages | 2 |
| Memanto `context` memories in CLI dry run | 4 |
| CLI dry-run skipped memories | 0 |
| Privacy redactions needed in public subset | 0 |
| Golden recall questions | 3 |
| Source recall | 3/3 |
| OKF recall | 3/3 |
| Exact recall parity | 3/3 |

The public subset was selected from a genuine Codex session after the privacy
filter. Internal instructions, tools, reasoning, account identifiers, email
addresses, phone numbers, and Bridge transport metadata are absent.

Memanto's official OKF dry run loaded all four nodes and deterministically
mapped all four to the `context` memory type without writing any live data.
