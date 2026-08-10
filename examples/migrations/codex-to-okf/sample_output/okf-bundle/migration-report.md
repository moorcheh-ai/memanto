# Migration report

- Source messages included: **12**
- Portable memories written: **15**
- Source SHA-256: `54ffa06cbca1612868fabb6b7a915605e8aa821c8eb65b51ded97f00baa1ec55`
- Bundle SHA-256: `e6b5f24202f48742438ebff66a377241f12eb0c77727ddb3de27907d6c4d0e97`
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
