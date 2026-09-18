# Grok Build TUI → OKF (Memanto Path B)

Grok Build TUI already stores agent memory on disk: `chat_history.jsonl`, `summary.json`, `goal/plan.md`, and `~/.grok/memory/MEMORY.md`. Those files are trapped in a vendor layout. This adapter turns them into an [OKF v0.2](https://docs.memanto.ai/integrations/okf) bundle that `memanto migrate okf` can import.

This is a **new source** (not Mem0/Letta/Supermemory/ChatGPT zip). It uses **real Grok session files**, not hand-written fake memories. Secrets are stripped before any markdown is written.

## Mapping

| Grok source | OKF / Memanto type |
| --- | --- |
| `MEMORY.md` → Preferências | `preference` |
| `MEMORY.md` → Mapa de trabalho table | `fact` |
| `MEMORY.md` → Padrões que voltam | `observation` |
| `summary.json` | `event` (session episode; Memanto has no `episode` type) |
| `goal/state.json` objective (redacted) | `goal` |
| `goal/plan.md` Deviations | `decision` |
| `<user_query>` lines in `chat_history.jsonl` | `observation` |

Unmapped JSONL fields (tool traces, system prompts, compaction dumps) are skipped on purpose so the bundle stays human-readable.

## Requirements

Python 3.10+. No third-party packages.

Optional: a [Moorcheh](https://moorcheh.ai/) key if you want to run `memanto migrate okf` against a live agent.

## Reproduce (single command)

From this directory:

```bash
python scripts/run_showcase.py
```

That converts the committed fixture, runs unittest, and scores the golden Q&A set against the generated wiki. If `memanto` is on PATH it also runs `memanto migrate okf ./sample-okf --dry-run`.

Manual steps:

```bash
python grok_to_okf.py --session ./fixtures/mini-session --memory ./fixtures/MEMORY.md --out ./sample-okf --generated-at 2026-09-12T00:51:03Z
python -m unittest tests/test_grok_to_okf.py
python scripts/validate_qa.py
```

Against a live Grok home (your machine):

```bash
python grok_to_okf.py --session "$HOME/.grok/sessions/<id>" --memory "$HOME/.grok/memory/MEMORY.md" --out ./my-okf
memanto migrate okf ./my-okf --dry-run
```

Windows PowerShell:

```powershell
python grok_to_okf.py --session $env:USERPROFILE\.grok\sessions\<id> --memory $env:USERPROFILE\.grok\memory\MEMORY.md --out .\my-okf
```

## Fidelity checks in this folder

- `tests/test_grok_to_okf.py` drives the **real CLI** (`main([...])`), not a reimplementation. It asserts email/token redaction, compaction-meta skip, and type mapping.
- `sample-okf/` is generated from `fixtures/` by the same CLI (see `scripts/build_sample.py`).
- `mapping.md` is the source-concept table required by bounty #1609 Path B.

## What this is not

It does not reimplement `memanto migrate`. It **feeds** `memanto migrate okf` with a valid bundle.
