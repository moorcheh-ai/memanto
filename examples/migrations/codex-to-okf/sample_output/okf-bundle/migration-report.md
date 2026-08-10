# Migration report

- Source messages included: **12**
- Portable memories written: **17**
- Source SHA-256: `302513994904938c671c67c51ceec0e561e69b52d38f2ce9c923aefba7e424a2`
- Bundle SHA-256: `cb4ef8e1d689e723db95e4015dddcfa4e33fae572bc5a8f6c1d498107f47cee2`
- Estimated source tokens: **1092**
- Estimated portable tokens: **1090**

## Type breakdown

- artifact: 2
- decision: 2
- fact: 2
- goal: 5
- instruction: 2
- observation: 4

## Privacy boundary

The adapter exported only visible user/assistant messages. It excluded developer messages, reasoning records, tool calls and outputs, turn context, world state, and compaction payloads. Common secrets, email addresses, and local home/workspace paths are redacted before classification.
