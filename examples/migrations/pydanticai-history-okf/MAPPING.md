# PydanticAI → OKF mapping

The source is the JSON emitted by PydanticAI's
`RunResult.all_messages_json()` or
`ModelMessagesTypeAdapter.dump_json(messages)`. The adapter emits one OKF
document per `ModelRequest` or `ModelResponse`, preserving message and part
boundaries instead of flattening the history into an ambiguous transcript.

| PydanticAI concept | OKF representation | Memanto mapping |
|---|---|---|
| `ModelRequest` | `type: PydanticAI request` | auto-classified unless the contained part has an unambiguous type |
| `ModelResponse` | `type: PydanticAI response` | auto-classified unless it contains only tool calls |
| `SystemPromptPart` | `## System instruction` | `x_memanto.type: instruction` when it is the only part kind |
| `UserPromptPart` | `## User` | auto-classified; confidence `0.95`, provenance `explicit_statement` |
| `TextPart` | `## Assistant` | auto-classified; confidence `0.75`, provenance `observed` |
| `ToolCallPart` | tool name, call ID and JSON arguments | `artifact` when the message contains only tool records |
| `ToolReturnPart` | tool name, call ID, outcome and result | `artifact` when the message contains only tool records |
| `RetryPromptPart` | validation/retry section | `error` |
| thinking or provider-native parts | omitted from the readable body and counted | complete source object remains in the canonical sidecar |
| `run_id` / `conversation_id` | tags, resource URI and source metadata | searchable provenance |
| message timestamp | OKF `timestamp` | Memanto `created_at` |
| model/provider/usage/unknown future fields | canonical source sidecar | preserved without guessing |

## Fidelity contract

For every source message at index `N`:

1. `source/messages/NNNN.json` stores its canonical JSON object.
2. The OKF frontmatter stores the sidecar path and SHA-256.
3. `migration-manifest.json` hashes every bundle file and the complete canonical
   message array.
4. `reconstruct.py` verifies every file hash, rebuilds the array in source
   order, and verifies the complete canonical hash.

The public sample reports 20 source messages → 20 OKF nodes → 20 Memanto mapped
rows, with zero skipped messages. Human-readable omission is reported
separately from data loss: unknown or thinking parts remain in the sidecar.

## Privacy contract

The adapter scans dictionary keys as well as values recursively before writing
anything. It fails closed on likely API keys, GitHub tokens, JWTs, private keys,
email addresses, phone numbers, and non-empty values under sensitive field
names such as `api_key`, `access_token`, or `password`. Matching keys use an
opaque path placeholder in reports and are replaced in redaction mode, so a key
cannot leak through either Markdown or canonical sidecars. Users must then do
one of three explicit things:

- sanitize the source themselves (recommended for public bundles);
- use `--redact`, which marks the migration `lossless: false`; or
- use `--allow-sensitive`, acknowledging that plaintext OKF will retain the
  findings.

Reports never contain the matched value or a hash derived from it. They contain
its category, JSON path, message index, severity, and a stable location ID for
traceability.
