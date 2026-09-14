# OKF ↔ Memanto mapping table

This showcase stores memory in the [Open Knowledge Format (OKF)](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf)
v0.1 layout that Memanto itself writes (`memanto memory export --okf`,
`memanto memory sync --okf`) and reads (`memanto migrate okf`). Nothing here
re-implements Memanto's shipped tooling; the scripts in this directory build
*on top of* it by adding a versioned, diffable, reviewable lifecycle.

## Bundle layout

```
<bundle>/
    memories/
        <type>/<slug>.md     # one concept per file
```

Memanto imports only the `memories/` subtree (`okf_loader.py`); `index.md` and
`log.md` navigation files are skipped. Each memory file is a markdown document
with YAML frontmatter.

## Field mapping

| OKF frontmatter field | Memanto schema | Notes |
| --- | --- | --- |
| `type` | memory type | OKF's free-form `type` is auto-classified by `memanto migrate okf` into Memanto's memory types (instruction, fact, decision, goal, commitment, preference, relationship, context, event, learning, observation, artifact, error) |
| `title` | memory title | Also used to derive the slug / filename |
| `description` | summary | Optional one-line summary |
| `resource` | resource URI | Optional source link |
| `tags` | tags | Optional list |
| `timestamp` | created/updated time | ISO-8601 |
| `x_memanto` | Memanto-only metadata | Namespaced block preserving `confidence`, `provenance`, `status` etc. so Memanto → OKF → Memanto round-trips are lossless |

Unknown frontmatter keys are preserved as "extra" fields by the loader and
survive the round trip - OKF is designed to be lossless.

## Type taxonomy used in this showcase

| Type | Meaning in the demo |
| --- | --- |
| `instruction` | Standing rules the agent must follow (CI, secrets, API compatibility) |
| `fact` | Stable facts about the product, stack, team and metrics |
| `decision` | Architectural/product decisions and their rationale |
| `goal` | Current objectives with measurable targets |
| `commitment` | Promises with deadlines (to Maya, partners, customers) |
| `preference` | Maya's communication and workflow preferences |
| `relationship` | How the agent works with other people (Alex, customers) |
| `context` | Short-lived sprint context |
| `event` | Notable events (first customer, funnel metrics) |
| `learning` | Product signals from customer conversations |
| `artifact` | Pointers to canonical files/docs |

## Provenance convention

The demo uses the `x_memanto.provenance` field to record *who* wrote a memory:

| Value | Meaning |
| --- | --- |
| `agent_session` | Written by the main agent during a normal session |
| `manual` | Written/confirmed by a human |
| `correction` | A preference correction from the user |
| `main_agent` / `nightly_analytics` | Written by a specific agent process |
| `human_review` | Written during human review/reconciliation |

This is what makes the conflict story possible: when two provenances disagree
on the same fact, `okf_diff.py` flags the contradiction instead of letting the
vector store silently collapse it.
