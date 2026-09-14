---
type: observation
title: Debugging lifetime errors in Rust
description: 'Getting a lifetime error in my parser: `error[E0597]: borrowed value
  does not live long enough`. The borrow is inside a loop and I store references to
  it. What is the pattern here?'
generated:
  by: process:chatgpt
  at: '2025-07-06T01:04:18.677629+00:00'
resource: 6b65a6a4-8b81-48f6-b38a-088ca65ed389
x_memanto:
  id: 68309fdf-d5da-4d1a-9a7d-637ac3a564e3
  confidence: 0.8
  provenance: imported
  source: chatgpt
  status: active
  updated_at: '2026-08-29T14:19:38.352702+00:00'
  type: observation
---

Getting a lifetime error in my parser: `error[E0597]: borrowed value does not live long enough`. The borrow is inside a loop and I store references to it. What is the pattern here?

---
[Supporting data]
- Conversation: Debugging lifetime errors in Rust
- Conversation id: c241330b-01a9-e71f-de8a-774bcf36d58b
- Node id: 6b65a6a4-8b81-48f6-b38a-088ca65ed389
