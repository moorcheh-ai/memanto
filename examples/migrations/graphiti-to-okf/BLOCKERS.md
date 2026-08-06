# Blockers — overnight session, 2026-08-06

These are the things that stopped the live pipeline. Nothing below was
mocked, stubbed, or filled with invented numbers.

## B1. No API keys in the environment

Checked (presence only, never values):

| Variable | Present |
| --- | --- |
| `MOORCHEH_API_KEY` | no |
| `OPENAI_API_KEY` | no |
| `ANTHROPIC_API_KEY` | no |
| `GEMINI_API_KEY` | no |
| `MEM0_API_KEY` | no |

Impact:

- Phase 1 Graphiti ingest needs an LLM (openai / anthropic / gemini) — blocked.
- Phase 2 real `memanto migrate` / Phase 4 OKF export need `MOORCHEH_API_KEY` — blocked.
- Phase 3 LLM-as-judge needs `ANTHROPIC_API_KEY` — blocked.
- Phase 4 Mem0 populate needs `MEM0_API_KEY` — blocked.

**What to do in the morning:** copy `.env.example` → `.env`, fill the keys,
re-run `scripts/run_all.ps1` (or `.sh`). The adapter code, unit tests, and
one-command runner are already in place.

## B2. No Docker daemon

`docker` is not on PATH. Neo4j via `docker compose` (the preferred backend)
cannot start on this machine tonight.

## B3. Native Neo4j / JDK install failed or hung

- `winget install EclipseAdoptium.Temurin.21.JDK` → *No applicable installer found*
  (exit `-1978335216`).
- `winget install Microsoft.OpenJDK.21` was still running with no output after
  ~10 minutes and produced no usable `java` on PATH.

Impact: cannot stand up Neo4j without Docker or a JDK tonight.
Fallback available: set `GRAPHITI_BACKEND=kuzu` in `.env` (zero-Docker,
deprecated upstream but functional). Still needs an LLM key (see B1).

## B4. No `~/.memanto` config / no pre-existing agent

`Test-Path $HOME\.memanto` → False. Even with a Moorcheh key, the first run
will need `memanto` interactive setup or `MOORCHEH_API_KEY` exported before
`run_all` can `agent create` / `migrate`.

## What is NOT blocked (done tonight)

- Full adapter (`graphiti_okf/mapping.py`, `okf_writer.py`, `provider_json.py`)
- Populate / export / validate / Mem0 scripts
- `run_all.sh` + `run_all.ps1`
- Unit tests: **7 passed**, ruff clean
- Mapping rationale, golden Q&A set, judge rubric
- Honest packaging docs (this file, `DECISIONS.md`, `README.md`, `SUMMARY.md`)
