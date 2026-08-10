# Migration report

- Source messages included: **12**
- Portable memories written: **15**
- Source SHA-256: `6b292468f6e8edc9afc372913803db536b122d683572e5f9d970236d7b4718d4`
- Bundle SHA-256: `fd2375057f4aa717fb21388997a844079f18947cc93e2fbf560e0f30be96b624`
- Estimated source tokens: **1092**
- Estimated portable tokens: **1071**

## Type breakdown

- artifact: 2
- decision: 2
- goal: 4
- instruction: 3
- observation: 4

## Privacy boundary

The adapter exported only visible user/assistant messages. It excluded developer messages, reasoning records, tool calls and outputs, turn context, world state, and compaction payloads. Common secrets, email addresses, and local home/workspace paths are redacted before classification.
