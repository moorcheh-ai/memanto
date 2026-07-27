# Live cloud validation

Validated on 2026-07-27 with a dedicated Memanto agent backed by Moorcheh.
No credentials, personal memories, or private repository data were used.

## Result

- 5 MCP entities imported into Memanto: 4 artifacts and 1 goal.
- 5/5 golden questions returned relevant memories with `memanto recall`.
- 5/5 golden questions produced grounded answers with `memanto answer`.
- 5 memories exported from the live agent back to an OKF bundle.
- 9/9 original MCP JSONL records reconstructed from the live export.
- Source and reconstructed SHA-256 hashes matched:
  `bf97e55e76a5e835df64b7374a5d413877cbab2616852ef59a77df78a8e9ee5f`.
- A credential-value scan of the example and local evidence returned zero
  contaminated files.

The machine-readable summary is in
[`sample/okf/metrics/live-cloud-validation.json`](sample/okf/metrics/live-cloud-validation.json).

## Live-only issue found

The first live run completed agent creation, import, activation, and all ten
recall/answer commands. The final export then correctly rejected an evidence
path outside Memanto's data directory.

The runner now creates a unique staging path under Memanto's data directory,
exports there, copies the result into the requested evidence directory, and
attempts to remove the staging copy on both success and failure. Regression
tests verify that staging paths stay under the guarded directory and that
shareable command output redacts unrelated absolute paths.

This constraint cannot be discovered by the offline fixture alone; the live
run directly improved the reproducibility of the submitted workflow.
