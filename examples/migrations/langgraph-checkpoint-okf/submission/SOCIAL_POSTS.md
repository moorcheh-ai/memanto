# Social Post Drafts

## X

I built a LangGraph checkpoint -> OKF migration path for Memanto.

It runs a real LangGraph app, writes SQLite checkpoints, exports durable memory
to readable markdown, then validates source-to-OKF recall parity.

Memory should be portable.

@moorcheh_ai

## LinkedIn

Agents are accumulating valuable state in framework-specific checkpoint stores.
That is useful until you need to inspect it, version it, or migrate it.

I built a reproducible LangGraph checkpoint -> Open Knowledge Format migration
showcase for Memanto. It runs a deterministic LangGraph app, captures real
SQLite checkpoints, converts durable memory channels into OKF markdown, and
checks recall parity against the source checkpoint.

The interesting bit: the exported bundle is not a black box. It is a normal
directory of markdown files with frontmatter, provenance, and traceability back
to the original LangGraph checkpoint.

Memory should be something your agents can carry, and something humans can read.

Tag: Moorcheh AI
