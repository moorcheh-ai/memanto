---
type: observation
title: 'Haystack 3725fe77fe0ee2f74277c1a3: user message 1'
description: 'Haystack session message 1, role: user.'
tags:
- haystack
- chat-history
- role-user
generated:
  by: process:haystack
  at: '2026-09-11T19:17:28.368979+00:00'
resource: haystack-chat:3725fe77fe0ee2f74277c1a3
x_memanto:
  id: 41466fa2-639d-4c52-b139-0cfc955b3638
  confidence: 0.8
  provenance: imported
  source: haystack
  status: active
  updated_at: '2026-09-11T19:17:28.368979+00:00'
  type: observation
---

Haystack session message 1, role: user.

> Set currency = USD

Source session: "procurement-demo"
Source position: 1

<!-- haystack-source-json -->
```json
{
  "message": {
    "content": [
      {
        "text": "Set currency = USD"
      }
    ],
    "meta": {
      "chat_message_id": "1"
    },
    "name": null,
    "role": "user"
  },
  "position": 1,
  "session_id": "procurement-demo"
}
```
<!-- /haystack-source-json -->

---
[Supporting data]
- OKF source: memories/000001-3725fe77fe0ee2f74277c1a3.md
- OKF resource: haystack-chat:3725fe77fe0ee2f74277c1a3
