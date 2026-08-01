# Field mapping and fidelity contract

This adapter turns an official ChatGPT `conversations.json` export into plain
Markdown nodes in an OKF bundle. It does not infer permanent user facts from
a transcript. Each exported assistant response is treated as a time-stamped
`event`, with the ancestor user message retained as context.

| ChatGPT export field | OKF destination | Why it is retained |
| --- | --- | --- |
| Conversation `id` | `x_memanto.conversation_id` | Stable source grouping and audit trail. |
| Message `id` | `x_memanto.node_id` and `source_id` | Idempotence and duplicate detection. |
| Assistant message `create_time` | `timestamp` | Temporal recall and ordering. |
| Conversation `title` | `title` and document context | Human-readable bundle navigation. |
| Direct ancestor user text | `## Conversation context` | The prompt that gives the answer its meaning. |
| Assistant text | `## Assistant response` | The original response payload. |
| Converter/redaction state | `x_memanto` and `manifest.json` | Makes privacy treatment explicit and reviewable. |

## Fidelity boundaries

- The original export remains the source of truth. This converter produces a
  portable representation, not a forensic backup of every ChatGPT metadata
  field or attachment.
- System, tool, and empty messages are skipped because they do not have a
  stable, human-readable text payload in the public export shape.
- The converter traverses each response's graph ancestry. It will not attach
  a user prompt from another branch merely because it has a nearby timestamp.
- `manifest.json` checks that each generated document came from the exact
  source-derived record used at conversion time. The document checksum catches
  post-generation edits.
- Redaction protects artifacts that are deliberately shared. It necessarily
  changes output text, so use the original local export—not the redacted
  bundle—when an exact archive is required.

## Round-trip evidence to collect for a submission

1. Save a local hash of the original `conversations.json`; do not publish it.
2. Run the converter with redaction on and preserve `report.json` plus
   `manifest.json`.
3. Run `memanto migrate okf <bundle> --dry-run` and save its mapped preview.
4. Import into a dedicated, non-production test agent and export it with
   `memanto memory export --okf`.
5. Compare a small manually-reviewed set of question/answer pairs against the
   source conversation and the imported agent. Distinguish exact retrieval,
   paraphrase, and disagreement instead of inventing a single score.
