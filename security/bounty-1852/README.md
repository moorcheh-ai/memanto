# Bounty #1852: identity collisions merge tenants' memory namespaces

**Class:** tenant isolation / cross-account data leak (CWE-706: use of an incorrectly resolved name; CWE-639: authorization bypass through a user-controlled key)
**Severity:** High for AgentCore, Medium for LangGraph
**Affected:** `integrations/agentcore` (`default_agent_id_resolver`), `integrations/langgraph` (`MemantoStore._ensure_client`)

## Summary

Memanto isolates memory per agent: agent `X` reads and writes only the
namespace `memanto_agent_X`, and the server strictly checks the session against
that agent. That isolation holds only if every caller identity maps to its own
agent id. Two integrations break this: each one derives the agent id from the
caller's identity with a function that is **not injective**. Principals the
application treats as distinct therefore receive the *same* agent id. They
recall each other's memories, and in LangGraph they also overwrite them. No
credential theft or server bug is needed; the collision happens in the
integration layer, before any request reaches Memanto.

### 1. AgentCore runtime adapter (High)

```python
readable = f"tenant-{tenant}-user-{user}-agent-{agent}"
sanitized = re.sub(r"[^a-zA-Z0-9_-]+", "_", readable)
```

The adapter README says `user_id` should come from "validated auth (never
client-supplied)". The identity provider guarantees these users are distinct,
and the adapter then merges them:

| Victim `(tenant, user)` | Attacker `(tenant, user)` | Shared agent id |
|---|---|---|
| `acme`, `john.doe@acme.com` | `acme`, `john_doe@acme.com` | `tenant-acme-user-john_doe_acme_com-agent-support` |
| `acme`, `john.doe@acme.com` | `acme`, `john@doe.acme.com` | same as above |
| `acme`, `Мария` | `acme`, `Иван` | `tenant-acme-user-_-agent-support` |
| `a-user-b`, `c` | `a`, `b-user-c` | `tenant-a-user-b-user-c-agent-support` |

The non-Latin row is the worst case. A whole run of characters becomes a
single `_`, so **every** user whose id is written entirely in Cyrillic, CJK,
Arabic, Greek or Hebrew script lands in the same agent. Each one sees the
others' retained conversation turns, which the adapter injects into the prompt
as "Relevant memories". The last row is a cross-*tenant* collision: the
`-user-` / `-agent-` delimiters are never escaped.

### 2. LangGraph `MemantoStore` (Medium)

```python
agent_id = "langgraph_" + "_".join(namespace)
```

`("acme", "bob_x")` and `("acme_bob", "x")` both become `langgraph_acme_bob_x`.
With the common `(org_id, user_id)` namespace layout, the owner of org
`acme_bob` can `get` the `profile` key of user `bob_x` in org `acme` and
silently **overwrite** it with `put`. `put` finds the existing key and calls
`update_memory` on the victim's record.

## Reproduce

Runs offline; no API key or network is needed. The Memanto client is replaced by
an in-memory fake that enforces the same per-agent isolation as the server, so
the only thing under test is the identity mapping.

```bash
pip install -e . -e integrations/agentcore -e integrations/langgraph
python security/bounty-1852/poc_identity_collisions.py
```

On `main` it prints `[LEAK]` for every case and exits `1`:

```
AgentCore default_agent_id_resolver
  [LEAK] emails: '.' vs '_'
         victim   ('acme', 'john.doe@acme.com')    -> tenant-acme-user-john_doe_acme_com-agent-support
         attacker ('acme', 'john_doe@acme.com')    -> tenant-acme-user-john_doe_acme_com-agent-support
  [LEAK] non-Latin names all collapse to '_'
         victim   ('acme', 'Мария')                -> tenant-acme-user-_-agent-support
         attacker ('acme', 'Иван')                 -> tenant-acme-user-_-agent-support
  ...
LangGraph MemantoStore
  [LEAK] ('acme_bob', 'x') reads ('acme', 'bob_x')
  [LEAK] ('acme_bob', 'x') overwrites ('acme', 'bob_x')

VULNERABLE: distinct identities read and overwrite each other's memories
```

With this patch every case prints `ok` and the script exits `0`.

## Fix

**AgentCore.** The resolver is now injective:

- The readable `tenant-…-user-…-agent-…` id is used only when it parses back to
  exactly one triple. That means every part already matches `[A-Za-z0-9_-]+`
  (nothing is rewritten) and `-user-` and `-agent-` each occur exactly once,
  overlapping matches included.
- Every other identity is hashed (SHA-256) from the raw structured parts, the
  same form the adapter already used for long ids. Hashed ids are 64 hex
  characters and never start with `tenant-`, so the two forms cannot collide.
- A part that contains the structural separator `U+001F` is rejected (fail
  closed).
- Ids that were already unambiguous are unchanged, including the README example
  and UUID subjects, so existing users keep their memories. The README
  documents the upgrade, and its custom-resolver example no longer shows the
  same `_`-join bug.

**LangGraph.** Renaming agents would orphan every existing store that uses
underscores (`("memories", "user_123")`). Instead, each new agent records its
exact namespace tuple in its `description` (`langgraph-namespace:[...]`).
`_ensure_client` refuses a namespace whose agent is bound to a *different*
tuple, both for existing agents and for the in-process client pool.
`list_namespaces` now returns the bound tuple, which also fixes the lossy
`split("_")` round-trip. Agents created before this change have no binding and
are still served.
Deployments that would rather fail closed can pass
`MemantoStore(api_key, strict_namespace_binding=True)`, which refuses those
unbound agents instead.

## Tests

- `integrations/agentcore/tests/test_adapter.py`: parametrized collision pairs,
  stability of already-safe ids, hashed-id format, separator rejection, and a
  20,000-case fuzz test that asserts injectivity over delimiter-heavy
  identities.
- `integrations/langgraph/tests/test_store.py`: collision refused through the
  pool and through an existing bound agent, same namespace reused, legacy
  unbound agent still served, and `list_namespaces` uses the binding.

The new tests fail on `main` and pass with the patch. All existing tests in
both integrations pass.
