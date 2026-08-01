# Google ADK SQLite → OKF → Memanto mapping

This adapter targets the JSON-backed `SqliteSessionService` shipped in Google
ADK `2.6.0`. The raw database remains authoritative: the bundle contains a
normalized snapshot and its database SHA-256 so every mapping can be audited or
replayed.

## Scope mapping

| Google ADK storage | Meaning | OKF location | Memanto behavior |
|---|---|---|---|
| `app_states.state` | Durable state shared by all users of an app | `memories/<type>/` | Imported with `scope:app` and `app:*` tags |
| `user_states.state` | Durable state shared by one user's sessions | `memories/<type>/` | Imported with `scope:user` and `user:*` tags |
| `sessions.state` | Durable state local to one session | `memories/<type>/` | Imported with `scope:session` and `session:*` tags |
| `events.event_data` text | Ordered conversation and tool context | `sessions/` | Preserved but excluded from import |
| `events.actions.stateDelta` | State evolution and corrections | `archive/state-history/` | Preserved but excluded from import |
| Full normalized rows | Replay and provenance evidence | `source/google-adk-sqlite-snapshot.json` | Not imported |

ADK's `app:` and `user:` prefixes are removed when state reaches their storage
tables, so scope comes from the table itself. Event deltas retain those
prefixes, which lets the adapter join each historical update back to its
current stored value.

## Type mapping

The first recognized segment of a state key controls the Memanto type.

| State-key segment | OKF / Memanto type |
|---|---|
| `fact`, `profile` | `fact` |
| `preference` | `preference` |
| `goal`, `plan` | `goal` |
| `decision` | `decision` |
| `artifact` | `artifact` |
| `learning`, `lesson` | `learning` |
| `event` | `event` |
| `instruction`, `policy`, `rule` | `instruction` |
| `relationship`, owner/DRI keys | `relationship` |
| `observation` | `observation` |
| `commitment`, deadline keys | `commitment` |
| `error`, failure keys | `error` |
| unknown | `context` |

The original key is always retained in `x_google_adk.state_key`; type inference
does not destroy source semantics. Confidence is adapter policy, not an ADK
score: user scope is `0.95`, app scope `0.90`, and session scope `0.85` unless a
structured value supplies an explicit bounded confidence.

## Field fidelity

| Google ADK concept | OKF representation | Memanto import result |
|---|---|---|
| App/user/session/key identity | Stable hashed concept `id` and canonical `google-adk://` `resource` | `source_ref` keeps the canonical resource |
| Current state value | Markdown body; structured JSON remains readable | Memory `content` |
| Key-derived label | `title` | Memory `title` |
| Scope and identifiers | Tags plus `x_google_adk` | Tags remain filterable; extension data remains in supporting data |
| Earliest/latest persisted delta | `timestamp`, `generated.at`, extension counts | Original time becomes `created_at` where supported |
| Mapping policy | `x_memanto.type`, confidence, source, provenance, status | Deterministic typed import with source `google-adk` |
| Database identity | Snapshot SHA-256 and `google-adk://sqlite/<digest>/...` URI | Traceable without exposing a local path |
| Unknown structured fields | Full snapshot plus OKF extension | No source field is discarded from the owned bundle |

JSON is emitted between YAML frontmatter delimiters. JSON is a strict subset of
YAML, so the output remains valid OKF frontmatter while the adapter itself stays
dependency-free.

## Corrections: current truth versus audit truth

For a state key updated more than once, only the value present in ADK's current
state table is written beneath `memories/`. Every persisted value is written in
timestamp order to a deprecated audit document beneath
`archive/state-history/`. The active concept links to that audit document but
does not repeat stale values in its body.

This prevents an import from reviving the demo's superseded July 31 date,
Maya-as-DRI assignment, or 24-hour TTL. A reviewer still owns and can inspect
the complete correction trail.

## Privacy policy

By default, any nested field whose key clearly denotes a password, token,
secret, cookie, credential, authorization value, API key, or private key is
replaced by `<redacted>`. Delimited and camelCase credential names are both
recognized. No value-derived digest is published, because even an unsalted
truncated digest can expose low-entropy secrets. The manifest reports the number
of redactions.

`--include-sensitive` is an explicit escape hatch for private migrations. It
should not be used for a public OKF bundle or bounty artifact.
