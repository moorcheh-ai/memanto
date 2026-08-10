# Migration report

- Source messages included: **12**
- Portable memories written: **16**
- Source SHA-256: `c036d91beddbfd8a33cd5f01001e13ad8cfa98edd5914c1aae47ab4dae888e64`
- Bundle SHA-256: `016f7d32617aea0cc739a73985fea300fb75750c5590a90d76c217d6291d6478`
- Estimated source tokens: **1092**
- Estimated portable tokens: **1090**

## Type breakdown

- artifact: 2
- decision: 2
- fact: 1
- goal: 4
- instruction: 3
- observation: 4

## Privacy boundary

The adapter exported only visible user/assistant messages. It excluded developer messages, reasoning records, tool calls and outputs, turn context, world state, and compaction payloads. Common secrets, email addresses, and local home/workspace paths are redacted before classification.
