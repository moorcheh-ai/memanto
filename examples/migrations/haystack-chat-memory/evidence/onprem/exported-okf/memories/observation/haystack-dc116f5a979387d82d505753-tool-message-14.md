---
type: observation
title: 'Haystack dc116f5a979387d82d505753: tool message 14'
description: 'Haystack session message 14, role: tool.'
tags:
- haystack
- chat-history
- role-tool
generated:
  by: process:haystack
  at: '2026-09-11T19:17:28.368979+00:00'
resource: haystack-chat:dc116f5a979387d82d505753
x_memanto:
  id: b6eaabae-50a3-4759-9324-72d906264675
  confidence: 0.8
  provenance: imported
  source: haystack
  status: active
  updated_at: '2026-09-11T19:17:28.368979+00:00'
  type: observation
---

Haystack session message 14, role: tool.



Source session: "procurement-demo"
Source position: 14

<!-- haystack-source-json -->
```json
{
  "message": {
    "content": [
      {
        "tool_call_result": {
          "error": true,
          "origin": {
            "arguments": {
              "id": "PO-42"
            },
            "extra": null,
            "id": "call-42",
            "tool_name": "lookup_purchase_order"
          },
          "result": "Temporary lookup failure"
        }
      }
    ],
    "meta": {
      "chat_message_id": "14"
    },
    "name": null,
    "role": "tool"
  },
  "position": 14,
  "session_id": "procurement-demo"
}
```
<!-- /haystack-source-json -->

---
[Supporting data]
- OKF source: memories/000014-dc116f5a979387d82d505753.md
- OKF resource: haystack-chat:dc116f5a979387d82d505753
