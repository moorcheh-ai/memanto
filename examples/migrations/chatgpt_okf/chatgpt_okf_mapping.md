# ChatGPT → OKF Migration Mapping

## Concept Mapping

| ChatGPT Concept | OKF Equivalent | Notes |
|---|---|---|
| Conversation | memory.type=conversation | Top-level knowledge unit |
| Message pair (Q/A) | memory.content (markdown) | Stored as readable Q&A text |
| Message timestamp | memory.created_at | ISO 8601 format |
| Conversation title | memory.title | Used for human-readable indexing |
| Conversation ID | memory.source_id | Preserves original reference |

## Data Preservation

- **Lossless**: All question/answer pairs extracted and stored as markdown
- **Format**: Plain text + markdown (vendor-neutral, git-friendly)
- **Queries**: Full conversation context preserved for recall validation

## Round-trip Validation

- Before: 3 ChatGPT conversations, 10 turns total
- After: 3 OKF memories with full Q&A content
- Recall test: All 3 sample queries found in exported OKF
