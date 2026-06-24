---
name: memanto-companion
description: Inspect and manage the cross-session engineering memory that Memanto maintains for your Claude Code skills. Use when the user asks what Memanto remembers, wants to see their engineering profile, manually recall context for a skill, or store a decision. The automatic lifecycle hooks handle capture/injection on their own — this skill is the manual control surface.
---

# Memanto Companion

Cross-session engineering memory for Claude Code skills runs automatically via
lifecycle hooks (`SessionStart`, `UserPromptExpansion`, `Stop`). This skill is the
**manual control surface** for when the user wants to inspect or steer it.

All operations go through the `memanto-skills` CLI. Requires `MOORCHEH_API_KEY`
in the environment.

## When the user wants to SEE what is remembered

Run:

```bash
memanto-skills profile
```

Then summarise the returned engineering profile for the user in plain language,
grouped by decisions, rules, and preferences.

## When the user wants context for a specific skill

If they ask "what do you remember about testing / TDD?" or want to preview what
would be injected before a skill, run:

```bash
memanto-skills recall <skill> --hint "<the current task>"
```

`<skill>` is a mattpocock skill name such as `tdd`, `grill-with-docs`,
`diagnose`, or `handoff`. Read the returned `<engineering-profile>` block and
honour it — these are decisions from past sessions.

## When the user states a durable decision to remember

If the user explicitly says "remember that we …" or makes an architectural
decision they want persisted immediately (rather than waiting for the automatic
`Stop` hook), distill and store it:

```bash
memanto-skills store <skill> "<a concise summary of what was decided>"
```

Memanto's backend LLM extracts the typed memories and persists them. Report
back which memories were stored.

## When the user wants to verify the setup

```bash
memanto-skills doctor
```

This checks the API key, agent id, and live connectivity. If it fails, the
likely cause is a missing `MOORCHEH_API_KEY` — point them to
https://console.moorcheh.ai/api-keys.

## Important

- Never invent memories. Only report what the CLI returns.
- Treat `instruction` memories as hard rules and `decision` memories as settled
  choices; do not re-litigate them unless the user asks.
- The hooks already inject context automatically — only run `recall` manually
  when the user explicitly wants to inspect or preview it.
