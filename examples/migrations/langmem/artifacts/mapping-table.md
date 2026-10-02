# LangMem -> Memanto / OKF field mapping

| LangMem field | Memanto / OKF field | Notes |
| --- | --- | --- |
| `value.content` | memory body + derived `title` | verbatim, never lossy |
| `namespace[1]` (user id) | tag `user=<id>`, `x_memanto.source=langmem` | scope preserved |
| `key` (uuid) | `source_ref` / OKF `resource` `langmem:<key>` | back-reference |
| `created_at` | OKF `timestamp` | temporal recall fidelity |
| *(inferred)* | memory `type` -> `x_memanto.type` | deterministic classifier |
| *(constant)* | `provenance=imported`, `confidence=0.75` | migration marker |

## Per-memory resolution

| # | Inferred type | Title |
| :---: | --- | --- |
| 1 | preference | Alex prefers TypeScript for new frontend work and dislikes untyped JavaScript. |
| 2 | fact | Alex is a senior backend engineer on the Payments team at Northwind, working... |
| 3 | preference | Alex uses dark mode in all editors and tools. |
| 4 | fact | The ledger service is written in Go and backed by Postgres. |
| 5 | preference | Alex runs pytest for Python projects and Vitest for all TypeScript repos. |
| 6 | preference | Alex never deploys on Fridays, regardless of how small the change is. |
| 7 | decision | Decision: the ledger service stores all monetary amounts as decimals, never f... |
| 8 | goal | Alex wants to learn Rust and eventually rewrite the settlement worker in it. |
| 9 | goal | Alex's goal: ship a single-currency (USD) double-entry ledger core to staging... |
| 10 | relationship | Priya moved from the ledger service to the Fraud team; Alex is now the sole e... |
