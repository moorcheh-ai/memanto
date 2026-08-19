---
type: context
title: Implementing async Rust with Tokio
description: I am working on a Rust library for async file I/O using Tokio. The read_to_string
  calls are blocking — should I use spawn_blocking or tokio::fs?
timestamp: '2025-06-28 17:56:59.261382+00:00'
resource: 23b8c1e9-3924-56de-3eb1-3b9046685257
x_memanto:
  confidence: 0.8
  provenance: imported
  source: chatgpt
  type: context
---

I am working on a Rust library for async file I/O using Tokio. The read_to_string calls are blocking — should I use spawn_blocking or tokio::fs?

---
[Supporting data]
- Conversation: Implementing async Rust with Tokio
- Conversation id: 972a8469-1641-9f82-8b9d-2434e465e150
- Node id: 23b8c1e9-3924-56de-3eb1-3b9046685257
